import importlib.util
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fix_anaconda', ROOT / 'installer/fix-anaconda.py')
fixes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixes)


class InstallerInitramfsTests(unittest.TestCase):
    def test_buildstamp_is_in_runtime_and_initramfs(self):
        script = (ROOT / 'installer/prepare.sh').read_text()
        self.assertIn('cat > /.buildstamp <<EOF', script)
        self.assertIn('Product=Gniri\nVersion=45\nIsFinal=False\n', script)
        self.assertIn('--include /.buildstamp /.buildstamp', script)
        self.assertLess(script.index('cat > /.buildstamp'), script.index('DRACUT_NO_XATTR=1'))

    def test_edd_is_requested_only_on_bios_in_both_hooks(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            options = directory / 'parse-anaconda-options.sh'
            modules = directory / 'anaconda-modprobe.sh'
            options.write_text('modprobe -q edd\n')
            modules.write_text('MODULE_LIST=""\n    MODULE_LIST+=" edd iscsi_ibft "\n')
            fixes.fix_edd(directory)
            for uefi in (False, True):
                firmware = directory / 'efi'
                if uefi:
                    firmware.mkdir()
                for path in (options, modules):
                    # Replace only the firmware probe, not the tested branch.
                    text = path.read_text().replace('/sys/firmware/efi', str(firmware))
                    text = 'modprobe() { echo "$*"; }\n' + text
                    if path == modules:
                        text += '\nfor module in $MODULE_LIST; do modprobe "$module"; done\n'
                    result = subprocess.run(['bash', '-eu', '-c', text],
                                            text=True, capture_output=True, check=True)
                    self.assertEqual('edd' in result.stdout, not uefi)
                    if path == modules:
                        self.assertIn('iscsi_ibft', result.stdout)

    def test_upstream_hook_changes_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'parse-anaconda-options.sh').write_text('# changed upstream\n')
            with self.assertRaisesRegex(RuntimeError, 'Anaconda changed'):
                fixes.fix_edd(directory)


class BootcMountTests(unittest.TestCase):
    def test_fedora45_keeps_upstream_cleanup_and_fixes_parent_order(self):
        source = ('class DeployBootcTask:\n    def _clean_physroot(self):\n        pass\n'
                  'class PrepareBootcMountTargetsTask:\n    def run(self):\n' + fixes.BOOT_ORDER_OLD)
        cleanup = ast.parse(source).body[0].body[0]
        digest = hashlib.sha256(ast.dump(cleanup).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'installation.py'
            path.write_text(source)
            with patch.object(fixes, 'CLEANUP_45_SHA256', digest):
                fixes.fix_bootc_mounts(path)
            self.assertIn(fixes.BOOT_ORDER_NEW, path.read_text())
            self.assertEqual(ast.dump(ast.parse(path.read_text()).body[0].body[0]), ast.dump(cleanup))

    def test_unknown_fedora45_cleanup_is_rejected_without_editing(self):
        source = 'class DeployBootcTask:\n    def _clean_physroot(self):\n        pass\n'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'installation.py'
            path.write_text(source)
            with self.assertRaisesRegex(RuntimeError, 'Anaconda changed'):
                fixes.fix_bootc_mounts(path)
            self.assertEqual(path.read_text(), source)

    def clean(self, mounts):
        source = 'def clean(self):\n        user_mount_points = MOUNTS\n' + fixes.CLEAN_NEW
        commands = Mock()
        namespace = dict(os=os, MOUNTS=mounts, safe_exec_program=commands)
        exec(source, namespace)
        with patch('os.listdir', return_value=['boot', 'home', 'var', 'proc', 'root']), \
                patch('os.path.ismount', return_value=True):
            namespace['clean'](SimpleNamespace(_physroot='/target'))
        return commands.call_args_list

    def test_separate_home_var_and_efi_are_never_unmounted_or_removed(self):
        calls = self.clean({'/': 'root', '/home': 'home', '/var': 'var', '/boot/efi': 'efi'})
        arguments = [call.args[1][-1] for call in calls]
        self.assertNotIn('/target/home', arguments)
        self.assertNotIn('/target/var', arguments)
        self.assertNotIn('/target/boot', arguments)
        self.assertIn('/target/proc', arguments)

    def test_installer_scratch_home_is_cleaned_without_a_home_mount(self):
        calls = self.clean({'/': 'root', '/boot': 'boot'})
        self.assertIn(unittest.mock.call('rm', ['-rf', '/target/home']), calls)

    def test_home_is_bound_into_deployment_after_var_before_users(self):
        namespace = {}
        source = 'def prepare(self, mount_points):\n' + fixes.MOUNTS_NEW
        exec(source, namespace)
        target = Mock()
        namespace['prepare'](target, {'/': 1, '/var': 2, '/home': 3, '/boot': 4, '/boot/efi': 5})
        self.assertEqual(target.mock_calls, [
            unittest.mock.call._fill_var_subdirectories(),
            unittest.mock.call._handle_boot_if_not_mount_point(),
            unittest.mock.call._setup_internal_bindmount('/home', recurse=False),
            unittest.mock.call._setup_internal_bindmount('/boot/efi', recurse=False),
        ])

    def test_fedora44_source_is_patched_and_still_compiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'installation.py'
            path.write_text('class DeployBootcTask:\n    def clean(self):\n' + fixes.CLEAN_OLD +
                            '\nclass PrepareBootcMountTargetsTask:\n    def run(self):\n' + fixes.MOUNTS_OLD)
            fixes.fix_bootc_mounts(path)
            self.assertIn(fixes.CLEAN_NEW, path.read_text())
            self.assertIn(fixes.MOUNTS_NEW, path.read_text())
            with self.assertRaisesRegex(RuntimeError, 'Anaconda changed'):
                fixes.fix_bootc_mounts(path)
