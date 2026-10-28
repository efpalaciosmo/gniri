import copy
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROMOTE = runpy.run_path(str(ROOT / 'scripts/promote-image.py'))
GATE = runpy.run_path(str(ROOT / 'scripts/release-gate.py'))
DIGEST = 'sha256:' + 'a' * 64
REVISION = 'b' * 40
IMAGE = 'ghcr.io/example/gniri'


class PromotionTests(unittest.TestCase):
    def record(self):
        return {'payload_digest': DIGEST, 'source_revision': REVISION,
                'candidate_run_id': '123', 'candidate_run_attempt': '1', 'iso_sha256': 'c' * 64,
                'checks': {name: {'result': 'pass', 'evidence': 'https://example.com/' + name}
                           for name in GATE['CHECKS']}}

    def metadata(self, version):
        return {'fedora_version': version, 'source_revision': REVISION,
                'image_reference': IMAGE + ':stable', 'channel': 'quay.io/fedora/fedora-bootc:latest',
                'base_image': 'quay.io/fedora/fedora-bootc:latest@' + DIGEST}

    def labels(self, version):
        return {'org.opencontainers.image.version': version,
                'org.opencontainers.image.revision': REVISION}

    def test_latest_stable_fedora_can_advance_without_a_fixed_major_version(self):
        for previous, candidate in (('44', '44'), ('44', '45'), ('45', '46')):
            self.assertEqual(PROMOTE['validate_candidate'](self.metadata(candidate), self.labels(candidate),
                             self.record(), IMAGE, previous), candidate)
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            PROMOTE['validate_candidate'](self.metadata('44'), self.labels('44'), self.record(), IMAGE, '45')

    def test_missing_or_mismatched_candidate_provenance_is_rejected(self):
        for key, value in (('fedora_version', 'rawhide'), ('fedora_version', ''),
                           ('source_revision', 'd' * 40), ('image_reference', 'localhost/gniri:development'),
                           ('base_image', 'quay.io/fedora/fedora-bootc:44'),
                           ('channel', 'quay.io/fedora/fedora-bootc:rawhide')):
            metadata = {**self.metadata('45'), key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                PROMOTE['validate_candidate'](metadata, self.labels('45'), self.record(), IMAGE, '44')
        with self.assertRaises(ValueError):
            PROMOTE['validate_candidate'](self.metadata('45'), self.labels('44'), self.record(), IMAGE, '44')

    def test_exact_successful_build_and_completed_rebase_evidence_are_required(self):
        run = {'id': 123, 'run_attempt': 1, 'repository': {'full_name': 'example/gniri'},
               'head_repository': {'full_name': 'example/gniri'}, 'head_branch': 'main',
               'head_sha': REVISION, 'event': 'push', 'path': '.github/workflows/build.yml',
               'conclusion': 'success'}
        PROMOTE['validate_run'](self.record(), run, 'example/gniri')
        for key, value in (('id', 124), ('run_attempt', 2), ('head_sha', 'd' * 40),
                           ('head_branch', 'feature'), ('conclusion', 'failure'), ('event', 'pull_request'),
                           ('head_repository', {'full_name': 'attacker/gniri'})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                PROMOTE['validate_run'](self.record(), {**run, key: value}, 'example/gniri')
        record = self.record()
        record['checks']['rebase-accounts']['result'] = 'untested'
        with self.assertRaises(ValueError):
            PROMOTE['validate_run'](record, run, 'example/gniri')

    def test_missing_review_or_broader_deployment_branches_cannot_promote(self):
        environment = {'name': 'stable', 'protection_rules': [
            {'type': 'required_reviewers', 'reviewers': [{'type': 'User'}]}],
            'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}}
        branches = {'total_count': 1, 'branch_policies': [{'name': 'main', 'type': 'branch'}]}
        PROMOTE['validate_environment'](environment, branches)
        for field, value in (('protection_rules', []), ('name', 'production'),
                             ('deployment_branch_policy', {'protected_branches': True})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                PROMOTE['validate_environment']({**environment, field: value}, branches)
        changed = copy.deepcopy(branches)
        changed['branch_policies'].append({'name': '*', 'type': 'branch'})
        changed['total_count'] = 2
        with self.assertRaises(ValueError):
            PROMOTE['validate_environment'](environment, changed)
