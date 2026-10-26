from pathlib import Path
import configparser
import importlib.util
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('buildstamp', ROOT / 'installer/write-buildstamp.py')
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)


class ReleaseTests(unittest.TestCase):
    def test_installer_maturity_tracks_base_instead_of_a_fixed_testing_label(self):
        for maturity, final in (('stable', True), ('development', False), ('beta', False),
                                ('unknown', False), (None, False)):
            with self.subTest(maturity=maturity):
                release = {'VERSION_ID': '45'}
                if maturity is not None:
                    release['RELEASE_TYPE'] = maturity
                parser = configparser.ConfigParser()
                parser.read_string(metadata.buildstamp(release, 0))
                self.assertEqual(parser.getboolean('Main', 'IsFinal'), final)
                self.assertEqual(parser['Main']['Product'], 'Gniri')
                self.assertEqual(parser['Main']['Version'], '45')
                self.assertEqual(parser['Main']['UUID'], '197001010000.x86_64')

    def test_buildstamp_follows_numbered_fedora_releases_but_not_rawhide(self):
        for version in ('44', '45', '46'):
            self.assertIn(f'Version={version}', metadata.buildstamp({'VERSION_ID': version}, 0))
        for version in ('rawhide', 'development', ''):
            with self.assertRaises(ValueError):
                metadata.buildstamp({'VERSION_ID': version}, 0)

    def test_installer_uses_the_payloads_resolved_stable_base(self):
        for file in ('Containerfile', 'installer/Containerfile'):
            text = (ROOT / file).read_text()
            base = re.search(r'^FROM (.+)$', text, re.MULTILINE).group(1)
            self.assertEqual(base, '${BASE_IMAGE}')
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        self.assertIn('org.opencontainers.image.base.name', script)
        self.assertIn('--build-arg "BASE_IMAGE=$base"', script)

    def test_release_branding_uses_the_actual_base_version(self):
        configure = (ROOT / 'build/configure-image.py').read_text()
        self.assertIn('VERSION_ID=', configure)
        self.assertIn('Gniri (Fedora {version})', configure)
        self.assertNotIn('Gniri (Fedora 44)', configure)
