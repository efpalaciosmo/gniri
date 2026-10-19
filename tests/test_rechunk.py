import hashlib
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPARE = runpy.run_path(str(ROOT / 'scripts/compare-oci.py'))['compare']
COMPARE_TREES = runpy.run_path(str(ROOT / 'tests/rechunk-smoke.py'))['compare_trees']


def layout(root, contents, compression='gzip'):
    blobs = root / 'blobs/sha256'
    blobs.mkdir(parents=True)

    def blob(data, media):
        digest = hashlib.sha256(data).hexdigest()
        (blobs / digest).write_bytes(data)
        return {'digest': 'sha256:' + digest, 'size': len(data), 'mediaType': media}

    layers = [blob(data, 'application/vnd.oci.image.layer.v1.tar+' + compression)
              for data in contents]
    manifest = blob(json.dumps({'layers': layers}).encode(),
                    'application/vnd.oci.image.manifest.v1+json')
    (root / 'index.json').write_text(json.dumps({'manifests': [manifest]}))
    return layers


class OciComparisonTests(unittest.TestCase):
    def test_counts_only_new_blobs_for_update_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout(root / 'before', [b'common', b'old'])
            layout(root / 'after', [b'common', b'new-content'])
            result = COMPARE(root / 'before', root / 'after')
            self.assertEqual(result['shared_layers'], 1)
            self.assertEqual(result['new_layer_bytes'], len(b'new-content'))
            self.assertEqual(result['before']['bytes'], 9)
            self.assertEqual(result['after']['bytes'], 17)

    def test_rejects_comparison_with_different_compression(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout(root / 'before', [b'one'], 'gzip')
            layout(root / 'after', [b'two'], 'zstd')
            with self.assertRaisesRegex(AssertionError, 'same layer compression'):
                COMPARE(root / 'before', root / 'after')


class RechunkContentTests(unittest.TestCase):
    def trees(self, root, directory, old_hardlink=False, new_hardlink=True):
        source, target = root / 'source', root / 'target'
        for tree, linked in ((source, old_hardlink), (target, new_hardlink)):
            (tree / directory).mkdir(parents=True)
            first, second = tree / directory / 'a', tree / directory / 'b'
            first.write_text('same content')
            if linked:
                os.link(first, second)
            else:
                second.write_text('same content')
        return source, target

    def test_accepts_usr_deduplication_and_read_only_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, target = self.trees(Path(temporary), 'usr')
            target.chmod(0o555)
            try:
                self.assertEqual(COMPARE_TREES(source, target), 4)
            finally:
                target.chmod(0o755)

    def test_rejects_new_hardlinks_in_mutable_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, target = self.trees(Path(temporary), 'etc')
            with self.assertRaisesRegex(AssertionError, 'outside immutable /usr'):
                COMPARE_TREES(source, target)

    def test_accepts_splitting_old_aliases_without_changing_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, target = self.trees(Path(temporary), 'etc', True, False)
            self.assertEqual(COMPARE_TREES(source, target), 4)

    def test_rejects_an_incomplete_layer_instead_of_reporting_a_smaller_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout(root / 'before', [b'one'])
            layer = layout(root / 'after', [b'two'])[0]
            (root / 'after/blobs/sha256' / layer['digest'].split(':')[1]).write_bytes(b'')
            with self.assertRaisesRegex(AssertionError, 'Incomplete OCI blob'):
                COMPARE(root / 'before', root / 'after')
