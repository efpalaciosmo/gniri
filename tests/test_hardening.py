import copy
import contextlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
POLICIES = runpy.run_path(str(ROOT / 'build/signature-policy.py'))
BASE = runpy.run_path(str(ROOT / 'scripts/build-image.py'))
GATE = runpy.run_path(str(ROOT / 'scripts/release-gate.py'))
UPDATES = runpy.run_path(str(ROOT / 'system_files/usr/bin/gniri-stage-update'))
REPOSITORY = 'ghcr.io/example/gniri'
DIGEST = 'sha256:' + 'a' * 64
REVISION = 'b' * 40


class SignaturePolicyTests(unittest.TestCase):
    def test_strict_bootc_policy_does_not_break_general_container_defaults(self):
        for default in ('reject', 'insecureAcceptAnything'):
            original = {'default': [{'type': default}], 'transports': {'dir': {'': [{'type': 'reject'}]}}}
            unchanged = copy.deepcopy(original)
            general, bootc = POLICIES['signature_policies'](original, REPOSITORY)
            self.assertEqual(original, unchanged)
            self.assertEqual(general['default'], original['default'])
            self.assertEqual(general['transports']['dir'], original['transports']['dir'])
            self.assertEqual(bootc['default'], [{'type': 'reject'}])
            self.assertEqual(set(bootc['transports']['docker']), {REPOSITORY})
            self.assertEqual(bootc['transports']['docker'][REPOSITORY][0]['type'], 'sigstoreSigned')

    def test_helper_uses_immutable_strict_policy_not_callers_environment(self):
        policy = POLICIES['signature_policies']({}, REPOSITORY)[1]
        with patch.object(Path, 'read_text', return_value=json.dumps(policy)), \
                patch.dict('os.environ', {'CONTAINERS_POLICY_JSON': '/untrusted/policy'}):
            env = UPDATES['policy_environment'](REPOSITORY + ':stable')
        self.assertEqual(env['CONTAINERS_POLICY_JSON'], '/usr/share/gniri/bootc-policy.json')
        for broken in ({'default': [{'type': 'insecureAcceptAnything'}]}, {'transports': {'docker': {}}}):
            invalid = {**policy, **broken}
            with patch.object(Path, 'read_text', return_value=json.dumps(invalid)), \
                    self.assertRaises((ValueError, KeyError)):
                UPDATES['policy_environment'](REPOSITORY + ':stable')

    def test_local_iso_script_verifies_before_pulling_published_payload(self):
        text = (ROOT / 'scripts/build-iso.sh').read_text()
        self.assertLess(text.index('cosign verify'), text.index('podman pull "$payload"'))


class StableBaseTests(unittest.TestCase):
    def manifest(self, architecture='amd64', digest=DIGEST):
        return {'manifests': [{'platform': {'os': 'linux', 'architecture': architecture}, 'digest': digest}]}

    def test_stable_channel_is_resolved_to_a_single_platform_digest(self):
        self.assertEqual(BASE['stable_base'](self.manifest()),
                         f'quay.io/fedora/fedora-bootc:latest@{DIGEST}')

    def test_base_release_must_be_a_numbered_stable_fedora(self):
        for version in ('44', '45', '46'):
            release = f'ID=fedora\nVERSION_ID={version}\nRELEASE_TYPE="stable"\n'
            self.assertEqual(BASE['fedora_version'](release), version)
        for release in ('ID=fedora\nVERSION_ID=rawhide\nRELEASE_TYPE=development\n',
                        'ID=ubuntu\nVERSION_ID=45\nRELEASE_TYPE=stable\n',
                        'ID=fedora\nVERSION_ID=45\nRELEASE_TYPE=prerelease\n'):
            with self.assertRaises(ValueError):
                BASE['fedora_version'](release)

    def test_unknown_ambiguous_or_malformed_platforms_fail_closed(self):
        for manifest in (self.manifest('arm64'), self.manifest(digest='latest'),
                         {'manifests': self.manifest()['manifests'] * 2}):
            with self.assertRaises(ValueError):
                BASE['stable_base'](manifest)

    def test_fresh_build_passes_immutable_base_and_retains_requested_network(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.chdir(temporary), \
                patch.object(sys, 'argv', ['build-image.py', 'localhost/gniri:test', '--reference',
                                          'localhost/gniri:development', '--network', 'host', '--fresh']), \
                patch('subprocess.check_output', side_effect=[json.dumps(self.manifest()),
                      'ID=fedora\nVERSION_ID=45\nRELEASE_TYPE=stable\n']), \
                patch('subprocess.run') as run:
            BASE['main']()
            command = run.call_args.args[0]
            self.assertIn('--no-cache', command)
            self.assertIn('--network=host', command)
            self.assertIn(f'BASE_IMAGE=quay.io/fedora/fedora-bootc:latest@{DIGEST}', command)
            self.assertIn('FEDORA_VERSION=45', command)
            self.assertFalse(Path('output').exists(), 'Rootful CI must not create root-owned output here')

    def test_failed_channel_resolution_never_starts_a_build(self):
        with patch.object(sys, 'argv', ['build-image.py', 'image', '--reference', 'reference']), \
                patch('subprocess.check_output', side_effect=subprocess.CalledProcessError(1, ['podman'])), \
                patch('subprocess.run') as run, self.assertRaises(subprocess.CalledProcessError):
            BASE['main']()
        run.assert_not_called()


class PromotionGateTests(unittest.TestCase):
    def evidence(self):
        return {'payload_digest': DIGEST, 'source_revision': REVISION, 'iso_sha256': 'c' * 64,
                'candidate_run_id': '123', 'candidate_run_attempt': '1',
                'checks': {name: {'result': 'pass', 'evidence': f'https://example.com/logs/{name}'}
                           for name in GATE['CHECKS']}}

    def test_complete_evidence_is_accepted_for_exact_candidate(self):
        GATE['validate'](self.evidence(), DIGEST, REVISION)

    def test_other_images_sources_missing_iso_or_unperformed_tests_are_rejected(self):
        for field, value in (('payload_digest', 'sha256:' + 'd' * 64),
                             ('source_revision', 'e' * 40), ('iso_sha256', ''),
                             ('candidate_run_id', ''), ('candidate_run_id', '../123'),
                             ('candidate_run_attempt', '0')):
            record = self.evidence()
            record[field] = value
            with self.assertRaises(ValueError):
                GATE['validate'](record, DIGEST, REVISION)
        for name in GATE['CHECKS']:
            for field, value in (('result', 'untested'), ('evidence', '')):
                record = self.evidence()
                record['checks'][name][field] = value
                with self.assertRaises(ValueError):
                    GATE['validate'](record, DIGEST, REVISION)


class UpdateStateTests(unittest.TestCase):
    def test_invalid_previous_status_does_not_prevent_recording_a_new_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'status.json'
            for previous in ('{broken', '[]', 'null'):
                path.write_text(previous)
                UPDATES['save_state'](path, 'success', 'new')
                state = json.loads(path.read_text())
                self.assertEqual(state['outcome'], 'success')
                self.assertIn('previous_state_error', state)

    def run_main(self, root, status, paused=False, failure=False):
        reference = root / 'image-reference'
        reference.write_text(REPOSITORY + ':stable\n')
        policy = root / 'policy.json'
        policy.write_text(json.dumps(POLICIES['signature_policies']({}, REPOSITORY)[1]))
        build = root / 'build.json'
        build.write_text(json.dumps({'fedora_version': '44'}))
        pause = root / 'paused'
        if paused:
            pause.touch()
        main = UPDATES['main']
        with patch.dict(main.__globals__, {'REFERENCE_FILE': reference, 'BUILD_FILE': build, 'POLICY': str(policy),
                                          'PAUSE': pause, 'STATE': root / 'status.json'}), \
                patch.object(sys, 'argv', ['gniri-stage-update']), \
                patch('os.geteuid', return_value=0), \
                patch('subprocess.check_output', side_effect=lambda command, **kwargs:
                      json.dumps({'Labels': {'org.opencontainers.image.version': '45'}})
                      if command[0] == 'skopeo' else json.dumps(status)) as inspect, \
                patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, ['bootc']) if failure else None) as run:
            result = main()
        return result, json.loads((root / 'status.json').read_text()), inspect, run

    def test_pause_does_not_contact_bootc_and_exits_successfully_without_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, state, inspect, run = self.run_main(Path(temporary), {}, paused=True)
            self.assertEqual(result, 0)
            self.assertEqual(state['outcome'], 'skipped')
            inspect.assert_not_called()
            run.assert_not_called()

    def test_real_entrypoint_records_success_and_staged_digest_with_strict_environment(self):
        image = {'image': REPOSITORY + ':stable', 'transport': 'registry', 'signature': 'containerPolicy'}
        status = {'spec': {'image': image}, 'status': {
            'booted': {'image': {'image': image}}, 'staged': {'image': {'imageDigest': DIGEST}}}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, state, _, run = self.run_main(root, status)
            self.assertEqual(result, 0)
            self.assertEqual(state['staged_digest'], DIGEST)
            self.assertIn('last_success', state)
            self.assertEqual(run.call_args.kwargs['env']['CONTAINERS_POLICY_JSON'], str(root / 'policy.json'))

    def test_failed_bootc_command_is_reported_as_retryable_not_as_success(self):
        image = {'image': REPOSITORY + ':stable', 'transport': 'registry', 'signature': 'containerPolicy'}
        status = {'spec': {'image': image}, 'status': {'booted': {'image': {'image': image}}}}
        with tempfile.TemporaryDirectory() as temporary:
            result, state, _, _ = self.run_main(Path(temporary), status, failure=True)
            self.assertEqual(result, 1)
            self.assertEqual(state['outcome'], 'failed')
            self.assertNotIn('last_success', state)

    def test_failures_and_skips_preserve_last_success_without_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'updates/status.json'
            UPDATES['save_state'](path, 'success', 'staged', 'first')
            for outcome in ('failed', 'skipped'):
                UPDATES['save_state'](path, outcome, 'reason', 'later')
                state = json.loads(path.read_text())
                self.assertEqual(state['last_success'], 'first')
                self.assertEqual(state['outcome'], outcome)
                self.assertEqual(state['last_attempt'], 'later')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_state_write_keeps_previous_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'status.json'
            UPDATES['save_state'](path, 'success', 'old')
            before = path.read_bytes()
            with patch('os.replace', side_effect=OSError('disk full')), self.assertRaises(OSError):
                UPDATES['save_state'](path, 'failed', 'new')
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_scheduled_retry_is_bounded_and_safety_skips_are_not_failures(self):
        unit = (ROOT / 'system_files/usr/lib/systemd/system/bootc-fetch-apply-updates.service.d/10-gniri.conf').read_text()
        for value in ('StartLimitIntervalSec=2h', 'StartLimitBurst=4', 'Restart=on-failure', 'RestartSec=15min'):
            self.assertIn(value, unit)
        self.assertTrue(issubclass(UPDATES['UpdateSkipped'], Exception))
