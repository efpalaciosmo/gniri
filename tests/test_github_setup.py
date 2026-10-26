import json
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SETUP = runpy.run_path(str(ROOT / 'scripts/setup-github.py'))
REPOSITORY = 'example/gniri'
ENDPOINT = f'repos/{REPOSITORY}/environments/stable'


class GitHubSetupTests(unittest.TestCase):
    def setUp(self):
        self.private = True
        self.exists = False
        self.confirm_reviewer = True
        self.policies = []
        self.calls = []
        self.commands = []

    def api(self, endpoint, method='GET', payload=None, optional=False):
        self.calls.append((endpoint, method, payload))
        if endpoint == f'repos/{REPOSITORY}':
            return {'private': self.private, 'permissions': {'admin': True}, 'default_branch': 'main'}
        if endpoint == 'users/example':
            return {'id': 42, 'login': 'example'}
        if endpoint.endswith('/collaborators/example/permission'):
            return {'permission': 'admin'}
        if endpoint == ENDPOINT:
            if method == 'PUT':
                self.exists = True
            if not self.exists:
                self.assertTrue(optional)
                return None
            return {
                'protection_rules': [{'type': 'required_reviewers', 'prevent_self_review': False,
                                      'reviewers': [{'type': 'User', 'reviewer': {'id': 42}}]}]
                if self.confirm_reviewer else [],
                'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
            }
        if endpoint == ENDPOINT + '/deployment-branch-policies' and method == 'POST':
            self.policies.append({**payload, 'id': 123})
            return self.policies[-1]
        if endpoint.startswith(ENDPOINT + '/deployment-branch-policies?'):
            return {'branch_policies': self.policies, 'total_count': len(self.policies)}
        self.fail(f'Unexpected API call: {endpoint}, {method}')

    def run_command(self, command, **kwargs):
        self.commands.append(command)
        if command[:3] == ['gh', 'secret', 'list']:
            return subprocess.CompletedProcess(command, 0, json.dumps([
                {'name': 'COSIGN_PRIVATE_KEY'}, {'name': 'COSIGN_PASSWORD'}]))
        if command[:3] == ['gh', 'repo', 'edit']:
            self.private = False
            return subprocess.CompletedProcess(command, 0)
        self.fail(f'Unexpected CLI command: {command}')

    def configure(self, **kwargs):
        with patch.dict(SETUP['configure'].__globals__, {'api': self.api}), \
                patch('subprocess.run', side_effect=self.run_command), patch('builtins.print'):
            SETUP['configure'](REPOSITORY, 'example', **kwargs)

    def test_visibility_change_requires_explicit_authorization(self):
        with self.assertRaisesRegex(ValueError, '--make-public'):
            self.configure()
        self.assertTrue(self.private)
        self.assertFalse(self.commands)
        self.assertTrue(all(method == 'GET' for _, method, _ in self.calls))

    def test_public_repository_and_reviewer_are_configured_without_rotating_keys(self):
        self.configure(make_public=True)
        self.assertFalse(self.private)
        self.assertEqual(self.policies, [{'name': 'main', 'type': 'branch', 'id': 123}])
        payload = next(payload for endpoint, method, payload in self.calls if method == 'PUT')
        self.assertEqual(payload['reviewers'], [{'type': 'User', 'id': 42}])
        self.assertFalse(payload['prevent_self_review'])
        self.assertTrue(all(command[:3] in (['gh', 'repo', 'edit'], ['gh', 'secret', 'list'])
                            for command in self.commands))

    def test_rerun_preserves_the_existing_main_policy_without_duplicate_creation(self):
        self.private = False
        self.exists = True
        self.policies = [{'id': 123, 'name': 'main', 'type': 'branch'}]
        self.configure()
        self.assertFalse(any(method == 'POST' for _, method, _ in self.calls))
        self.assertFalse(any(command[:3] == ['gh', 'repo', 'edit'] for command in self.commands))

    def test_existing_unexpected_rules_are_not_deleted_or_replaced(self):
        self.private = False
        self.exists = True
        self.policies = [{'id': 123, 'name': '*', 'type': 'branch'}]
        with self.assertRaisesRegex(ValueError, 'Unexpected existing'):
            self.configure()
        self.assertTrue(all(method == 'GET' for _, method, _ in self.calls))

    def test_setup_fails_when_github_does_not_confirm_required_reviewers(self):
        self.confirm_reviewer = False
        with self.assertRaisesRegex(ValueError, 'not confirmed'):
            self.configure(make_public=True)

    def test_missing_signing_secrets_stop_before_publishing_or_configuring(self):
        def missing(command, **kwargs):
            self.assertEqual(command[:3], ['gh', 'secret', 'list'])
            return subprocess.CompletedProcess(command, 0, '[]')

        with patch.dict(SETUP['configure'].__globals__, {'api': self.api}), \
                patch('subprocess.run', side_effect=missing):
            with self.assertRaisesRegex(ValueError, 'no keys were generated or rotated'):
                SETUP['configure'](REPOSITORY, 'example', make_public=True)
        self.assertTrue(self.private)
        self.assertTrue(all(method == 'GET' for _, method, _ in self.calls))
