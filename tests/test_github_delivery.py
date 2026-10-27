import copy
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = runpy.run_path(str(ROOT / 'scripts/prepare-release.py'))
GATE = runpy.run_path(str(ROOT / 'scripts/release-gate.py'))
REPOSITORY = 'example/gniri'
DIGEST = 'sha256:' + 'a' * 64
REVISION = 'b' * 40
ISO_NAME = 'gniri-x86_64.iso'


class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.artifacts = self.directory / 'download'
        self.artifacts.mkdir()
        self.output = self.directory / 'release'
        self.content = b'The exact tested ISO, not a fresh build.'
        self.sha256 = hashlib.sha256(self.content).hexdigest()
        self.record = {
            'payload_digest': DIGEST, 'source_revision': REVISION, 'iso_sha256': self.sha256,
            'candidate_run_id': '123', 'candidate_run_attempt': '2',
            'checks': {name: {'result': 'pass', 'evidence': f'https://example.com/{name}'}
                       for name in GATE['CHECKS']},
        }
        self.run = {
            'id': 123, 'run_attempt': 2, 'repository': {'full_name': REPOSITORY},
            'head_repository': {'full_name': REPOSITORY}, 'head_branch': 'main',
            'head_sha': REVISION, 'event': 'push', 'path': '.github/workflows/build.yml',
            'conclusion': 'success',
        }
        self.metadata = {
            'payload_reference': f'ghcr.io/example/gniri@{DIGEST}',
            'source_revision': REVISION, 'installer_source_revision': REVISION,
            'update_reference': 'ghcr.io/example/gniri:stable',
            'iso_checksum': f'{self.sha256}  {ISO_NAME}',
        }
        (self.artifacts / ISO_NAME).write_bytes(self.content)
        (self.artifacts / 'SHA256SUMS').write_text(self.metadata['iso_checksum'] + '\n')
        self.write_json('build.json', self.metadata)
        template = copy.deepcopy(self.record)
        for check in template['checks'].values():
            check.update(result='untested', evidence='')
        self.write_json('validation.json', template)

    def write_json(self, name, record):
        (self.artifacts / name).write_text(json.dumps(record))

    def prepare(self, **kwargs):
        return RELEASE['prepare_release'](self.artifacts, self.output, self.record,
                                          self.run, REPOSITORY, **kwargs)

    def test_small_iso_is_preserved_with_reviewed_evidence_and_checksums(self):
        self.assertEqual(self.prepare(), 'gniri-123-2')
        self.assertEqual((self.output / ISO_NAME).read_bytes(), self.content)
        self.assertEqual(json.loads((self.output / 'validation.json').read_text()), self.record)
        subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=self.output,
                       check=True, capture_output=True)
        notes = (self.output / 'release-notes.md').read_text()
        self.assertIn('cosign verify-blob', notes)
        self.assertNotIn('cat gniri', notes)

    def test_large_iso_parts_reassemble_to_the_tested_bytes(self):
        self.prepare(part_size=10)
        parts = sorted(self.output.glob(ISO_NAME + '.part-*'))
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(0 < part.stat().st_size <= 10 for part in parts))
        self.assertEqual(b''.join(part.read_bytes() for part in parts), self.content)
        self.assertFalse((self.output / ISO_NAME).exists())
        (self.output / ISO_NAME).write_bytes(b''.join(part.read_bytes() for part in parts))
        subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=self.output,
                       check=True, capture_output=True)
        notes = (self.output / 'release-notes.md').read_text()
        self.assertIn(f'cat {ISO_NAME}.part-* > {ISO_NAME}', notes)
        self.assertLess(notes.index('cosign verify-blob'), notes.index('cat gniri'))

    def test_changed_iso_is_rejected_before_staging(self):
        (self.artifacts / ISO_NAME).write_bytes(b'Another ISO')
        with self.assertRaisesRegex(ValueError, 'tested ISO checksum'):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_untrusted_failed_or_different_actions_runs_are_rejected(self):
        invalid = [('id', 124), ('run_attempt', 3), ('head_branch', 'testing'),
                   ('event', 'pull_request'), ('event', 'pull_request_target'),
                   ('event', 'workflow_run'), ('path', '.github/workflows/check.yml'),
                   ('conclusion', 'failure'), ('conclusion', None), ('head_sha', 'c' * 40),
                   ('repository', {'full_name': 'attacker/gniri'}),
                   ('head_repository', {'full_name': 'attacker/gniri'})]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                original = self.run
                self.run = {**original, field: value}
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.output.exists())
                self.run = original

    def test_other_payload_sources_installers_targets_or_checksums_are_rejected(self):
        for field, value in [('payload_reference', f'ghcr.io/other/gniri@{DIGEST}'),
                             ('source_revision', 'c' * 40),
                             ('installer_source_revision', 'c' * 40),
                             ('update_reference', 'ghcr.io/example/gniri:latest'),
                             ('iso_checksum', '0' * 64 + '  ' + ISO_NAME)]:
            with self.subTest(field=field):
                self.write_json('build.json', {**self.metadata, field: value})
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertFalse(self.output.exists())

    def test_missing_or_changed_template_identity_is_rejected(self):
        self.write_json('validation.json', {**self.record, 'candidate_run_attempt': '1'})
        with self.assertRaisesRegex(ValueError, 'template differs'):
            self.prepare()
        (self.artifacts / 'validation.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing regular candidate artifact'):
            self.prepare()

    def test_unperformed_checks_and_symlink_artifacts_are_rejected(self):
        self.record['checks']['hardware']['result'] = 'untested'
        with self.assertRaisesRegex(ValueError, 'Missing passing result'):
            self.prepare()
        self.record['checks']['hardware']['result'] = 'pass'
        (self.artifacts / ISO_NAME).unlink()
        external = self.directory / 'external.iso'
        external.write_bytes(self.content)
        (self.artifacts / ISO_NAME).symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'Missing regular candidate artifact'):
            self.prepare()

    def test_existing_output_and_oversized_part_limits_are_not_accepted(self):
        for part_size in (0, -1, 2 * 1024 ** 3):
            with self.assertRaises(ValueError):
                self.prepare(part_size=part_size)
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_manual_iso_runs_can_use_a_different_reviewed_installer_revision(self):
        self.run.update(path='.github/workflows/iso.yml', event='workflow_dispatch', head_sha='c' * 40)
        self.metadata['installer_source_revision'] = 'c' * 40
        self.write_json('build.json', self.metadata)
        self.prepare()

    def test_generated_template_records_identity_but_never_claims_tests_passed(self):
        template = self.directory / 'template.json'
        subprocess.run(['python3', str(ROOT / 'scripts/release-gate.py'), 'template',
                        '--digest', DIGEST, '--revision', REVISION, '--run-id', '123',
                        '--run-attempt', '2', '--iso-sha256', self.sha256, '--output', str(template)],
                       check=True)
        record = json.loads(template.read_text())
        for field in ('payload_digest', 'source_revision', 'candidate_run_id',
                      'candidate_run_attempt', 'iso_sha256'):
            self.assertEqual(record[field], self.record[field])
        self.assertTrue(all(check['result'] == 'untested' for check in record['checks'].values()))
        with self.assertRaises(ValueError):
            GATE['validate'](record, DIGEST, REVISION)


@unittest.skipUnless(shutil.which('jq'), 'Draft-release shell checks require jq (installed in CI)')
class DraftReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / 'commands.jsonl'
        self.assets = self.directory / 'assets'
        self.assets.mkdir()
        (self.assets / 'SHA256SUMS.bundle').write_text('fake bundle')
        (self.assets / 'release-notes.md').write_text('release notes')
        client = self.directory / 'gh'
        client.write_text('''#!/usr/bin/env python3
import json
import os
import sys
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[2] == 'view':
    state = os.environ.get('RELEASE_STATE', 'missing')
    if state == 'missing':
        sys.exit(1)
    print(json.dumps({'isDraft': state != 'published',
                      'targetCommitish': 'c' * 40 if state == 'other-source' else 'b' * 40}))
elif sys.argv[2] == 'upload':
    sys.exit(int(os.environ.get('UPLOAD_EXIT', '0')))
''')
        client.chmod(0o755)

    def stage(self, **variables):
        env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                   GITHUB_ACTIONS='true', GITHUB_REPOSITORY=REPOSITORY,
                   COMMAND_LOG=str(self.log), **variables)
        result = subprocess.run(['bash', str(ROOT / 'scripts/stage-github-release.sh'),
                                 'gniri-123-2', REVISION, str(self.assets)],
                                env=env, text=True, capture_output=True)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, commands

    def test_new_release_is_only_a_draft_and_upload_follows_creation(self):
        result, commands = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([command[1] for command in commands], ['view', 'create', 'upload'])
        self.assertIn('--draft', commands[1])
        self.assertIn(REVISION, commands[1])

    def test_retry_can_replace_assets_only_in_the_same_revision_draft(self):
        result, commands = self.stage(RELEASE_STATE='draft')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([command[1] for command in commands], ['view', 'upload'])
        self.assertIn('--clobber', commands[-1])

    def test_published_release_and_other_revision_draft_are_never_overwritten(self):
        for state in ('published', 'other-source'):
            with self.subTest(state=state):
                self.log.unlink(missing_ok=True)
                result, commands = self.stage(RELEASE_STATE=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(commands), 1)

    def test_failed_asset_upload_is_not_reported_as_success(self):
        result, _ = self.stage(UPLOAD_EXIT='9')
        self.assertEqual(result.returncode, 9)


class DeliveryWorkflowTests(unittest.TestCase):
    def test_manual_iso_requires_an_explicit_digest_without_a_stable_fallback(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        dispatch = workflow.split('  workflow_dispatch:', 1)[1].split('\npermissions:', 1)[0]
        self.assertIn('required: true', dispatch)
        self.assertNotIn('skopeo inspect', workflow)
        self.assertLess(workflow.index('name: Validate candidate digest'), workflow.index('uses: actions/checkout'))
        self.assertIn('digest="$PAYLOAD_DIGEST"', workflow)

    def test_iso_input_precheck_rejects_missing_or_invalid_digests_with_recovery(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        step = workflow.split('      - name: Validate candidate digest\n', 1)[1].split('      - ', 1)[0]
        script = '\n'.join(line[10:] for line in step.split('        run: |\n', 1)[1].splitlines())
        for digest in ('', 'stable', 'sha256:abc', 'sha256:' + 'A' * 64, DIGEST + '\n', DIGEST):
            with self.subTest(digest=digest):
                result = subprocess.run(['bash', '-e', '-c', script], text=True, capture_output=True,
                                        env=dict(os.environ, PAYLOAD_DIGEST=digest))
                if digest == DIGEST:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('::error::', result.stdout)
                    self.assertIn('Run that workflow first', result.stdout)

    def test_iso_is_connected_by_digest_only_after_a_trusted_build(self):
        build = (ROOT / '.github/workflows/build.yml').read_text()
        iso = (ROOT / '.github/workflows/iso.yml').read_text()
        self.assertIn('digest: ${{ steps.publish.outputs.digest }}', build)
        self.assertIn('needs: build', build)
        self.assertIn('uses: ./.github/workflows/iso.yml', build)
        self.assertIn('payload_digest: ${{ needs.build.outputs.digest }}', build)
        self.assertIn("github.event_name != 'pull_request' && github.ref == 'refs/heads/main'", build)
        self.assertIn('workflow_call:', iso)
        self.assertIn('name: gniri-installer-x86_64-${{ github.run_attempt }}', iso)
        self.assertIn('"DOCKER_CONFIG=$HOME/.docker"', iso)
        self.assertNotIn('workflow_run:', iso)

    def test_only_protected_promotion_publishes_a_release_without_rebuilding(self):
        workflow = (ROOT / '.github/workflows/promote.yml').read_text()
        self.assertIn('environment: stable', workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn('actions: read', workflow)
        self.assertIn('contents: write', workflow)
        self.assertIn('gh run download', workflow)
        self.assertIn('prepare-release.py', workflow)
        self.assertIn('cosign sign-blob', workflow)
        self.assertLess(workflow.index('prepare-release.py'), workflow.index('stage-github-release.sh'))
        self.assertLess(workflow.index('stage-github-release.sh'), workflow.index('skopeo copy'))
        self.assertLess(workflow.index('skopeo copy'), workflow.index('gh release edit'))
        self.assertNotIn('build-iso.sh', workflow)
        self.assertNotIn('make build', workflow)

    def test_actions_are_pinned_and_dependency_bots_do_not_overlap(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            for action in re.findall(r'uses:\s+(\S+)', path.read_text()):
                if not action.startswith('./'):
                    self.assertRegex(action, r'^[^@]+@[a-f0-9]{40}$')
        dependabot = (ROOT / '.github/dependabot.yml').read_text()
        self.assertIn('package-ecosystem: github-actions', dependabot)
        self.assertIn('interval: weekly', dependabot)
        renovate = json.loads((ROOT / 'renovate.json').read_text())
        self.assertNotIn('github-actions', renovate['enabledManagers'])
