import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('finalize_target', ROOT / 'installer/finalize-target.py')
finalize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalize)


class RootMountTests(unittest.TestCase):
    def test_readback_preserves_repeated_console_and_storage_arguments(self):
        before = ['root=UUID=root', 'rw', 'rootflags=subvol=root', 'console=tty0',
                  'console=ttyS0,115200', 'rd.luks.uuid=luks-test', 'ostree=/ostree/boot.0/test']
        after = [arg.replace('rootflags=subvol=root', 'rootflags=subvol=root,compress=zstd:1')
                 .replace('/ostree/boot.0/', '/ostree/boot.1/') for arg in before]
        finalize.verify_arguments(before, after, 'subvol=root,compress=zstd:1')
        for broken in (after[:-2] + after[-1:],
                       [arg for arg in after if not arg.startswith('rootflags=')],
                       after + ['rootflags=subvol=wrong'],
                       [arg.replace('compress=zstd:1', 'compress=zstd:3') for arg in after]):
            with self.subTest(arguments=broken), self.assertRaises(RuntimeError):
                finalize.verify_arguments(before, broken, 'subvol=root,compress=zstd:1')

    def test_btrfs_compression_and_subvolume_are_preserved(self):
        text = ('# anaconda\nUUID=root / btrfs subvol=root,compress=zstd:1,ro 0 0\n'
                'UUID=boot /boot ext4 defaults 1 2\nUUID=home /home btrfs subvol=home 0 0\n')
        result, flags = finalize.plan_root_mount(text, 'subvol=/root')
        self.assertEqual(flags, 'subvol=root,compress=zstd:1')
        self.assertNotIn('UUID=root / ', result)
        self.assertIn('UUID=boot /boot ext4 defaults 1 2\n', result)
        self.assertIn('UUID=home /home btrfs subvol=home 0 0\n', result)

    def test_filesystem_options_are_not_discarded(self):
        _, flags = finalize.plan_root_mount('UUID=root / ext4 defaults,errors=remount-ro,noatime 1 1\n', '')
        self.assertEqual(flags, 'errors=remount-ro,noatime')

    def test_fstab_only_options_do_not_become_kernel_mount_options(self):
        _, flags = finalize.plan_root_mount('UUID=root / xfs defaults,rw,nofail,x-systemd.device-timeout=5s 0 0\n', '')
        self.assertEqual(flags, '')

    def test_no_root_entry_is_idempotent(self):
        text = 'UUID=home /home btrfs subvol=home 0 0\n'
        self.assertEqual(finalize.plan_root_mount(text, ''), (text, None))

    def test_ambiguous_and_virtual_roots_are_rejected(self):
        for text in ('UUID=a / xfs defaults 0 0\nUUID=b / ext4 defaults 0 0\n',
                     'overlay / overlay ro 0 0\n', 'UUID=a /\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                finalize.plan_root_mount(text, '')

    def test_failed_kernel_update_never_changes_fstab(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fstab'
            original = 'UUID=root / btrfs subvol=root 0 0\n'
            path.write_text(original)
            callback = Mock(side_effect=RuntimeError('cannot update boot configuration'))
            with self.assertRaises(RuntimeError):
                finalize.migrate_fstab(path, '', callback)
            self.assertEqual(path.read_text(), original)

    def test_success_keeps_backup_and_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fstab'
            original = 'UUID=root / btrfs subvol=root 0 0\n'
            path.write_text(original)
            callback = Mock()
            self.assertTrue(finalize.migrate_fstab(path, '', callback))
            self.assertFalse(finalize.migrate_fstab(path, '', callback))
            callback.assert_called_once_with('subvol=root')
            self.assertEqual(path.with_name('fstab.gniri-before-rootflags').read_text(), original)

    def test_installer_runs_finalizer_after_configuration_without_hiding_failure(self):
        recipe = (ROOT / 'installer/prepare.sh').read_text()
        self.assertIn('%post --nochroot --erroronfail\n', recipe)
        self.assertIn('/usr/bin/python3 /usr/libexec/gniri-installer-finalize.py', recipe)
        self.assertNotIn('systemctl mask systemd-remount-fs', recipe)
