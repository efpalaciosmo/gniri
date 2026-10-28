from pathlib import Path
import os
import runpy
import stat
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = runpy.run_path(str(ROOT / 'build/install-system-files.py'))['install_system_files']


class SystemOverlayTests(unittest.TestCase):
    def test_private_checkout_cannot_make_system_paths_private(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            target.mkdir()
            # Reproduce a clone created with umask 077, including its ancestors.
            old_umask = os.umask(0o077)
            try:
                for name in ('etc/niri/config.kdl', 'usr/bin/gniri-stage-update',
                             'usr/share/polkit-1/rules.d/10-gniri-rpm-ostree.rules'):
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('image default\n')
                INSTALL(source, target)
            finally:
                os.umask(old_umask)
            for path in target.rglob('*'):
                mode = stat.S_IMODE(path.stat().st_mode)
                expected = 0o755 if path.is_dir() or path.parent == target / 'usr/bin' else 0o644
                self.assertEqual(mode, expected, str(path))
            self.assertEqual((target / 'etc/niri/config.kdl').read_text(), 'image default\n')

    def test_shared_directory_permissions_and_local_accounts_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            (source / 'etc/gdm').mkdir(parents=True)
            (source / 'etc/gdm/custom.conf').write_text('[daemon]\n')
            (target / 'etc').mkdir(parents=True)
            (target / 'etc').chmod(0o750)
            account = target / 'etc/passwd'
            account.write_text('existing:x:1000:1000::/var/home/existing:/bin/bash\n')
            INSTALL(source, target)
            INSTALL(source, target)
            self.assertEqual(stat.S_IMODE((target / 'etc').stat().st_mode), 0o750)
            self.assertEqual(account.read_text(), 'existing:x:1000:1000::/var/home/existing:/bin/bash\n')

    def test_symlinks_cannot_redirect_an_overlay_write(self):
        for link_in_source in (True, False):
            with self.subTest(link_in_source=link_in_source), tempfile.TemporaryDirectory() as directory:
                source, target = Path(directory) / 'source', Path(directory) / 'target'
                source.mkdir()
                target.mkdir()
                outside = Path(directory) / 'outside'
                outside.write_text('preserve')
                if link_in_source:
                    (source / 'file').symlink_to(outside)
                else:
                    (source / 'file').write_text('new')
                    (target / 'file').symlink_to(outside)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    INSTALL(source, target)
                self.assertEqual(outside.read_text(), 'preserve')
