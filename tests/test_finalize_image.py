from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FINALIZE = runpy.run_path(str(ROOT / 'build/finalize-image.py'))
clean_systemd_runtime = FINALIZE['clean_systemd_runtime']


class ImageRuntimeCleanupTests(unittest.TestCase):
    def test_unit_load_marker_and_empty_parent_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'run/systemd'
            runtime.mkdir(parents=True)
            marker = runtime / 'systemd-units-load'
            marker.touch(mode=0o444)
            clean_systemd_runtime(root)
            self.assertEqual(list((root / 'run').iterdir()), [])
            clean_systemd_runtime(root)

    def test_missing_or_empty_systemd_directory_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean_systemd_runtime(root)
            runtime = root / 'run/systemd'
            runtime.mkdir(parents=True)
            clean_systemd_runtime(root)
            self.assertFalse(runtime.exists())

    def test_unknown_runtime_content_is_preserved_for_fatal_lint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'run/systemd'
            runtime.mkdir(parents=True)
            (runtime / 'systemd-units-load').touch()
            unknown = runtime / 'unexpected'
            unknown.write_text('preserve for lint')
            resolver = runtime / 'resolve'
            resolver.mkdir()
            stub = resolver / 'stub-resolv.conf'
            stub.write_text('container runtime DNS')
            clean_systemd_runtime(root)
            self.assertFalse((runtime / 'systemd-units-load').exists())
            self.assertEqual(unknown.read_text(), 'preserve for lint')
            self.assertEqual(stub.read_text(), 'container runtime DNS')

    def test_unexpected_marker_directory_is_rejected_not_recursively_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'run/systemd/systemd-units-load'
            marker.mkdir(parents=True)
            unknown = marker / 'unexpected'
            unknown.write_text('preserve')
            with self.assertRaises(IsADirectoryError):
                clean_systemd_runtime(root)
            self.assertEqual(unknown.read_text(), 'preserve')

    def test_finalizer_still_refuses_to_run_outside_build_container(self):
        with patch.object(Path, 'exists', return_value=False), \
                patch('os.walk') as walk, \
                self.assertRaisesRegex(SystemExit, 'inside the Gniri build container'):
            FINALIZE['main']()
        walk.assert_not_called()

    def test_finalization_precedes_strict_bootc_lint(self):
        containerfile = (ROOT / 'Containerfile').read_text()
        self.assertLess(containerfile.index('python3 /run/gniri-build/finalize-image.py'),
                        containerfile.index('bootc container lint --fatal-warnings'))
