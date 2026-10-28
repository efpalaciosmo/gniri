from pathlib import Path
import os
import runpy
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
normalize_boot = runpy.run_path(str(ROOT / 'build/normalize-boot.py'))['normalize_boot']


class BootMetadataTests(unittest.TestCase):
    def test_symbols_move_to_matching_kernel_and_repeat_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'boot').mkdir()
            modules = root / 'usr/lib/modules/7.2.12-test'
            modules.mkdir(parents=True)
            (root / 'boot/symvers-7.2.12-test.xz').write_bytes(b'kernel symbols')
            normalize_boot(root)
            self.assertEqual(list((root / 'boot').iterdir()), [])
            self.assertEqual((modules / 'symvers.xz').read_bytes(), b'kernel symbols')
            normalize_boot(root)

    def test_unmatched_metadata_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'boot').mkdir()
            source = root / 'boot/symvers-unknown.xz'
            source.write_bytes(b'unknown')
            with self.assertRaises(ValueError):
                normalize_boot(root)
            self.assertTrue(source.exists())

    def test_conflicting_symbols_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'boot').mkdir()
            modules = root / 'usr/lib/modules/test'
            modules.mkdir(parents=True)
            (root / 'boot/symvers-test.xz').write_bytes(b'new')
            (modules / 'symvers.xz').write_bytes(b'old')
            with self.assertRaises(ValueError):
                normalize_boot(root)
            self.assertEqual((modules / 'symvers.xz').read_bytes(), b'old')


class LogicalHomeTests(unittest.TestCase):
    def check_home(self, child=False, interactive=True):
        with tempfile.TemporaryDirectory() as directory:
            physical = Path(directory) / 'var/home/user'
            physical.mkdir(parents=True)
            logical = Path(directory) / 'home'
            logical.symlink_to(physical, target_is_directory=True)
            cwd = physical / 'project' if child else physical
            cwd.mkdir(exist_ok=True)
            script = ROOT / 'system_files/etc/profile.d/gniri-home.sh'
            result = subprocess.run(
                ['bash', '--noprofile', '--norc', *(['-i'] if interactive else []),
                 '-c', 'source "$1"; printf "%s" "$PWD"', 'bash', str(script)],
                cwd=cwd, env=dict(os.environ, HOME=str(logical), PWD=str(cwd)),
                text=True, capture_output=True, check=True)
            return result.stdout, str(logical if interactive and not child else cwd)

    def test_interactive_home_uses_logical_path(self):
        self.assertEqual(*self.check_home())

    def test_project_directory_is_preserved(self):
        self.assertEqual(*self.check_home(child=True))

    def test_noninteractive_working_directory_is_preserved(self):
        self.assertEqual(*self.check_home(interactive=False))
