from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_installer_and_payload_use_the_same_pinned_45_base(self):
        bases = []
        for file in ('Containerfile', 'installer/Containerfile'):
            text = (ROOT / file).read_text()
            base = re.search(r'^FROM (.+)$', text, re.MULTILINE).group(1)
            self.assertRegex(base, r'^quay\.io/fedora/fedora-bootc:45@sha256:[a-f0-9]{64}$')
            bases.append(base)
        self.assertEqual(*bases)

    def test_release_branding_uses_the_actual_base_version(self):
        configure = (ROOT / 'build/configure-image.py').read_text()
        self.assertIn('VERSION_ID=', configure)
        self.assertIn('Gniri (Fedora {version})', configure)
        self.assertNotIn('Gniri (Fedora 44)', configure)
