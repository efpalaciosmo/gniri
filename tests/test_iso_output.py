import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import runpy

ROOT = Path(__file__).resolve().parents[1]


class IsoOutputTests(unittest.TestCase):
    """Only fake artifact bytes: no Podman, sudo, image build or disk installation."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / 'fresh build'
        self.output = self.directory / 'published output'
        self.source.mkdir()
        self.output.mkdir()

    def publish(self):
        return subprocess.run(['python3', str(ROOT / 'scripts/publish-iso.py'),
                               str(self.source), str(self.output)],
                              text=True, capture_output=True)

    def make_artifact(self, name='nested/image-builder-name.iso', content=b'new ISO'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_publishes_nested_iso_with_project_name_and_architecture(self):
        source = self.make_artifact()
        source.chmod(0o600)
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        artifact = self.output / 'gniri-x86_64.iso'
        self.assertEqual(artifact.read_bytes(), b'new ISO')
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o644)
        self.assertIn(str(artifact.resolve()), result.stdout)
        self.assertFalse(source.exists())
        checksum = self.output / 'SHA256SUMS'
        self.assertEqual(checksum.read_text(),
                         f'{hashlib.sha256(b"new ISO").hexdigest()}  gniri-x86_64.iso\n')
        subprocess.run(['sha256sum', '--check', 'SHA256SUMS'], cwd=self.output,
                       check=True, capture_output=True)

    def test_missing_iso_is_an_explicit_error_not_an_old_artifact(self):
        previous = self.output / 'gniri-x86_64.iso'
        previous.write_bytes(b'previous ISO')
        (self.output / 'SHA256SUMS').write_text('previous checksum\n')
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('found 0', result.stderr)
        self.assertIn('output/iso-build.log', result.stderr)
        self.assertEqual(previous.read_bytes(), b'previous ISO')
        self.assertEqual((self.output / 'SHA256SUMS').read_text(), 'previous checksum\n')

    def test_empty_iso_is_rejected(self):
        self.make_artifact(content=b'')
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('empty', result.stderr)
        self.assertFalse((self.output / 'gniri-x86_64.iso').exists())

    def test_multiple_new_isos_are_rejected_not_arbitrarily_overwritten(self):
        self.make_artifact('first.iso')
        self.make_artifact('second.iso')
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('found 2', result.stderr)
        self.assertFalse((self.output / 'gniri-x86_64.iso').exists())

    def test_success_replaces_only_the_managed_artifact(self):
        (self.output / 'gniri-x86_64.iso').write_bytes(b'previous ISO')
        unrelated = self.output / 'older-manual-backup.iso'
        unrelated.write_bytes(b'user backup')
        self.make_artifact()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.output / 'gniri-x86_64.iso').read_bytes(), b'new ISO')
        self.assertEqual(unrelated.read_bytes(), b'user backup')
        self.assertEqual(list(self.output.glob('.SHA256SUMS.*')), [])

    def test_symlink_is_not_published_as_a_fresh_artifact(self):
        outside = self.directory / 'old.iso'
        outside.write_bytes(b'old ISO')
        (self.source / 'link.iso').symlink_to(outside)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_bytes(), b'old ISO')

    def test_metadata_is_bound_to_the_new_iso_checksum(self):
        self.make_artifact()
        metadata = self.directory / 'inputs.json'
        metadata.write_text(json.dumps({'payload_image_id': 'tested-image', 'validation': 'UNTESTED'}))
        publish = runpy.run_path(str(ROOT / 'scripts/publish-iso.py'))['publish_iso']
        publish(self.source, self.output, metadata)
        record = json.loads((self.output / 'build.json').read_text())
        self.assertEqual(record['iso_checksum'], (self.output / 'SHA256SUMS').read_text().strip())
        self.assertEqual(record['payload_image_id'], 'tested-image')
        self.assertEqual(record['validation'], 'UNTESTED')

    def test_invalid_metadata_does_not_replace_an_existing_iso(self):
        self.make_artifact()
        previous = self.output / 'gniri-x86_64.iso'
        previous.write_bytes(b'previous ISO')
        metadata = self.directory / 'inputs.json'
        metadata.write_text('{broken')
        publish = runpy.run_path(str(ROOT / 'scripts/publish-iso.py'))['publish_iso']
        with self.assertRaises(ValueError):
            publish(self.source, self.output, metadata)
        self.assertEqual(previous.read_bytes(), b'previous ISO')

    def test_builder_logs_and_uses_a_fresh_directory(self):
        script = (ROOT / 'scripts/build-iso.sh').read_text()
        self.assertIn('set -euo pipefail', script)
        self.assertIn('mktemp -d "$PWD/output/iso-build.XXXXXX"', script)
        self.assertIn('-v "$build_dir:/output"', script)
        self.assertIn('| tee output/iso-build.log', script)
        self.assertIn('python3 scripts/publish-iso.py "$build_dir" output/iso', script)

    def test_ci_uploads_the_canonical_artifact(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        self.assertIn('output/iso/gniri-x86_64.iso', workflow)
        self.assertIn('output/iso/SHA256SUMS', workflow)
        self.assertIn('sha256sum --check SHA256SUMS', workflow)
        self.assertNotIn('find output/iso', workflow)
