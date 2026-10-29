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


class IsoWorkflowResolutionTests(unittest.TestCase):
    def resolve(self, channel='stable', digest='', **variables):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        step = workflow.split('      - name: Resolve installer payload\n', 1)[1]
        step = step.split('      - name:', 1)[0].split('        run: |\n', 1)[1]
        script = '\n'.join(line[10:] for line in step.splitlines())
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            log = directory / 'commands.jsonl'
            output = directory / 'output'
            client = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['COMMAND_LOG'], 'a') as stream:
    stream.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
if name == 'skopeo':
    print(os.environ['MOCK_DIGEST'])
if name == 'cosign':
    sys.exit(int(os.environ.get('VERIFY_EXIT', '0')))
'''
            for name in ('skopeo', 'cosign'):
                path = directory / name
                path.write_text(client)
                path.chmod(0o755)
            sudo = directory / 'sudo'
            sudo.write_text('#!/usr/bin/env bash\nexec "$@"\n')
            sudo.chmod(0o755)
            env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'],
                       OWNER='Example', CHANNEL=channel, DIGEST=digest, MOCK_DIGEST=DIGEST,
                       COMMAND_LOG=str(log), GITHUB_OUTPUT=str(output))
            env.update(variables)
            result = subprocess.run(['/usr/bin/bash', '-c', script], cwd=ROOT,
                                    env=env, text=True, capture_output=True)
            commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, commands, output.read_text() if output.exists() else ''

    def test_channel_is_resolved_once_and_the_same_digest_is_verified(self):
        for channel in ('stable', 'latest'):
            with self.subTest(channel=channel):
                result, calls, output = self.resolve(channel=channel)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual([call[0] for call in calls], ['skopeo', 'cosign'])
                self.assertEqual(calls[0][-1], f'docker://ghcr.io/example/gniri:{channel}')
                self.assertEqual(calls[1][-1], f'ghcr.io/example/gniri@{DIGEST}')
                self.assertIn(f'payload=ghcr.io/example/gniri@{DIGEST}\n', output)
                self.assertIn(f'target=ghcr.io/example/gniri:{channel}\n', output)

    def test_explicit_digest_does_not_resolve_a_mutable_tag(self):
        result, calls, output = self.resolve(channel='latest', digest=DIGEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in calls], ['cosign'])
        self.assertIn(f'payload=ghcr.io/example/gniri@{DIGEST}\n', output)

    def test_invalid_inputs_or_failed_signatures_do_not_emit_build_references(self):
        for variables in ({'channel': 'other'}, {'digest': 'latest'},
                          {'digest': DIGEST + '\ninjected=value'},
                          {'MOCK_DIGEST': 'not-a-digest'}, {'VERIFY_EXIT': '9'}):
            with self.subTest(variables=variables):
                result, _, output = self.resolve(**variables)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, '')


class DeliveryWorkflowTests(unittest.TestCase):
    def test_candidate_build_is_separate_from_protected_promotion(self):
        workflows = ROOT / '.github/workflows'
        self.assertEqual(sorted(p.name for p in workflows.iterdir() if p.suffix in {'.yml', '.yaml'}),
                         ['build.yml', 'iso.yml', 'promote.yml'])
        workflow = (workflows / 'build.yml').read_text()
        jobs = workflow.split('\njobs:\n', 1)[1]
        self.assertEqual(re.findall(r'^  ([\w-]+):$', jobs, re.MULTILINE), ['build'])
        self.assertNotIn('workflow_call:', workflow)
        self.assertNotIn('workflow_run:', workflow)
        self.assertNotIn('inputs.', workflow)
        self.assertNotIn('build-iso.sh', workflow)
        self.assertNotIn('release-gate.py', workflow)
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('packages: write', jobs)
        self.assertIn('name: Publish signed image to GHCR', jobs)
        promotion = (workflows / 'promote.yml').read_text()
        self.assertIn('environment: stable', promotion)
        self.assertIn('needs: validate', promotion)
        self.assertIn("if: github.ref == 'refs/heads/main'", promotion)
        self.assertIn('scripts/promote-image.py validate', promotion)
        self.assertIn('scripts/promote-image.py promote', promotion)
        self.assertNotIn('push:', promotion)
        self.assertNotIn('schedule:', promotion)

    def test_regular_builds_publish_latest_after_signature_and_policy_checks(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        build = workflow
        self.assertIn('--revision "$GITHUB_SHA" --fresh', build)
        self.assertIn('--report output/inventory/image-size.json', build)
        self.assertIn('"docker://$IMAGE@$digest" "docker://$IMAGE:latest"', build)
        self.assertLess(build.index('cosign sign --yes'), build.index('"docker://$IMAGE:latest"'))
        self.assertLess(build.index('bash scripts/check-registry-policy.sh'),
                        build.index('"docker://$IMAGE:latest"'))
        self.assertIn('test "$actual" = "$digest"', build)

    def test_image_workflow_cannot_publish_github_releases_or_deployments(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('environment:', workflow)
        self.assertNotIn('gh release', workflow)
        self.assertNotIn('stage-github-release.sh', workflow)
        self.assertNotIn('prepare-release.py', workflow)

    def test_iso_workflow_is_manual_read_only_and_uploads_verified_artifacts(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('default: stable', workflow)
        self.assertIn('packages: read', workflow)
        for forbidden in ('push:', 'pull_request:', 'schedule:', 'workflow_run:',
                          'contents: write', 'packages: write', 'COSIGN_PRIVATE_KEY',
                          'cosign sign', 'gh release', 'promote-image.py', 'build-image.py'):
            self.assertNotIn(forbidden, workflow)
        self.assertIn('cosign verify --new-bundle-format=false --key trust/cosign.pub', workflow)
        self.assertLess(workflow.index('cosign verify'), workflow.index('bash scripts/build-iso.sh'))
        self.assertIn('bash scripts/build-iso.sh "$PAYLOAD_REF" "$TARGET_REF" \'\' 1', workflow)
        self.assertIn('sudo make check-installer', workflow)
        self.assertLess(workflow.index('sha256sum --check'), workflow.index('name: Upload installer ISO'))
        for filename in ('gniri-x86_64.iso', 'SHA256SUMS', 'build.json'):
            self.assertIn(f'output/iso/{filename}', workflow)
        self.assertIn('compression-level: 0', workflow)
        self.assertIn('if-no-files-found: error', workflow)
        self.assertIn('if: always()', workflow)
        self.assertIn('path: output/iso-build.log', workflow)

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
