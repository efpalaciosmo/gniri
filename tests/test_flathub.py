import base64
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'system_files/usr/bin/gniri-flathub-user'
configure_flathub = runpy.run_path(str(HELPER))['configure_flathub']


class FlathubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.descriptor = Path(self.temp.name) / 'flathub.flatpakrepo'
        self.key = b'bundled public signing keys'
        self.descriptor.write_text(
            '[Flatpak Repo]\nUrl=https://dl.flathub.org/repo/\nGPGKey='
            + base64.b64encode(self.key).decode() + '\n')

    def test_existing_remote_keys_are_imported_on_every_run(self):
        with patch('subprocess.run') as run, patch(
                'subprocess.check_output',
                return_value='other\thttps://example.com/repo/\n'
                             'flathub\thttps://dl.flathub.org/repo/\n') as remotes:
            for _ in range(2):
                configure_flathub(self.descriptor)
        self.assertEqual(run.call_count, 4)
        remotes.assert_called_with(
            ['flatpak', 'remotes', '--user', '--show-disabled', '--columns=name,url'],
            text=True)
        for add, refresh in (run.call_args_list[:2], run.call_args_list[2:]):
            self.assertEqual(add.args[0], [
                'flatpak', 'remote-add', '--user', '--if-not-exists',
                'flathub', str(self.descriptor)])
            self.assertEqual(refresh.args[0], [
                'flatpak', 'remote-modify', '--user', '--gpg-verify',
                '--gpg-import=-', 'flathub'])
            self.assertEqual(refresh.kwargs, {'input': self.key, 'check': True})

    def test_official_url_aliases_allow_key_repair(self):
        for url in ('https://flathub.org/repo/', 'https://dl.flathub.org/repo'):
            with self.subTest(url=url), patch('subprocess.run') as run, patch(
                    'subprocess.check_output', return_value=f'flathub\t{url}\n'):
                configure_flathub(self.descriptor)
                self.assertEqual(run.call_count, 2)

    def test_custom_remote_is_not_modified(self):
        for url in ('https://example.com/repo/',
                    'https://dl.flathub.org/repo-untrusted',
                    'http://dl.flathub.org/repo/', 'file:///srv/flathub'):
            with self.subTest(url=url), patch('subprocess.run') as run, patch(
                    'subprocess.check_output', return_value=f'flathub\t{url}\n'), patch(
                    'sys.stderr'):
                configure_flathub(self.descriptor)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][1], 'remote-add')

    def test_invalid_descriptor_fails_before_changing_remotes(self):
        for text in ('[Flatpak Repo]\nUrl=https://example.com/repo\nGPGKey=YWJj\n',
                     '[Flatpak Repo]\nUrl=https://dl.flathub.org/repo/\nGPGKey=!!!\n',
                     '[Flatpak Repo]\nUrl=https://dl.flathub.org/repo/\nGPGKey=\n'):
            with self.subTest(text=text), patch('subprocess.run') as run:
                self.descriptor.write_text(text)
                with self.assertRaises(ValueError):
                    configure_flathub(self.descriptor)
                run.assert_not_called()

    def test_import_failure_is_not_reported_as_success(self):
        failure = subprocess.CalledProcessError(1, ['flatpak', 'remote-modify'])
        with patch('subprocess.run', side_effect=[None, failure]), patch(
                'subprocess.check_output',
                return_value='flathub\thttps://dl.flathub.org/repo/\n'):
            with self.assertRaises(subprocess.CalledProcessError):
                configure_flathub(self.descriptor)

    def test_missing_remote_is_not_reported_as_success(self):
        with patch('subprocess.run'), patch('subprocess.check_output', return_value=''):
            with self.assertRaises(RuntimeError):
                configure_flathub(self.descriptor)
