from pathlib import Path
import runpy
import unittest

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check-rebase.py'))['validate']


class RebasePreflightTests(unittest.TestCase):
    def test_existing_local_account_and_shell_can_advance_to_new_stable(self):
        CHECK({'fedora_version': '45', 'shell_available': True, 'gdm_available': True}, '44', True)

    def test_vendor_account_missing_shell_old_release_and_missing_gdm_block_preflight(self):
        valid = {'fedora_version': '45', 'shell_available': True, 'gdm_available': True}
        cases = [(valid, False), ({**valid, 'shell_available': False}, True),
                 ({**valid, 'gdm_available': False}, True), ({**valid, 'fedora_version': '43'}, True),
                 ({**valid, 'fedora_version': 'rawhide'}, True)]
        for data, local in cases:
            with self.subTest(data=data, local=local), self.assertRaises(ValueError):
                CHECK(data, '44', local)
