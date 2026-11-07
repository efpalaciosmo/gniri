import os
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = runpy.run_path(str(ROOT / 'scripts/registry.py'))


class RegistryRepositoryTests(unittest.TestCase):
    def test_default_uses_lowercase_github_owner_not_repository_name(self):
        with patch.dict(os.environ, {'QUAY_NAMESPACE': ''}):
            self.assertEqual(REGISTRY['image_repository']('Example/renamed-source'),
                             'quay.io/example/gniri')

    def test_namespace_override_is_shared_by_promotion_and_release_tools(self):
        with patch.dict(os.environ, {'QUAY_NAMESPACE': 'quay-organization'}):
            for script, name in (('registry.py', 'image_repository'),
                                 ('promote-image.py', 'IMAGE_REPOSITORY'),
                                 ('prepare-release.py', 'image_repository')):
                with self.subTest(script=script):
                    resolver = runpy.run_path(str(ROOT / 'scripts' / script))[name]
                    self.assertEqual(resolver('OtherOwner/source'), 'quay.io/quay-organization/gniri')

    def test_malformed_namespaces_and_github_repositories_are_rejected(self):
        for namespace in ('UpperCase', '../other', 'owner/image', 'owner+robot',
                          'owner:tag', 'owner\ninjected=value', '$(command)', 'quay.io'):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                REGISTRY['image_repository']('example/source', namespace)
        for repository in ('owner', 'owner/source/extra', '../source', 'owner/source\ninjected=value'):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                REGISTRY['image_repository'](repository, 'example')

    def test_cli_uses_the_same_namespace_and_fails_without_output_for_invalid_input(self):
        for namespace in ('quay-organization', 'invalid/namespace'):
            with self.subTest(namespace=namespace):
                result = subprocess.run(['python3', str(ROOT / 'scripts/registry.py'), 'Example/source'],
                                        env=dict(os.environ, QUAY_NAMESPACE=namespace),
                                        text=True, capture_output=True)
                if namespace == 'quay-organization':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, 'quay.io/quay-organization/gniri\n')
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')

    def test_workflows_use_quay_robot_credentials_instead_of_github_package_tokens(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            with self.subTest(workflow=path.name):
                text = path.read_text()
                self.assertIn('QUAY_NAMESPACE: ${{ vars.QUAY_NAMESPACE }}', text)
                self.assertIn('REGISTRY_USERNAME: ${{ secrets.QUAY_USERNAME }}', text)
                self.assertIn('REGISTRY_TOKEN: ${{ secrets.QUAY_TOKEN }}', text)
                self.assertNotIn('packages:', text)
                self.assertNotIn('GITHUB_ACTOR', text)
                logins = [line.strip() for line in text.splitlines() if ' login ' in line]
                self.assertEqual(len(logins), 4 if path.name == 'promote.yml' else 2)
                for login in logins:
                    self.assertIn('login quay.io -u "$REGISTRY_USERNAME" --password-stdin', login)
                    self.assertIn('"$REGISTRY_TOKEN"', login)
