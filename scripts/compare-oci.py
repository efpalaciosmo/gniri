#!/usr/bin/env python3
"""Compare referenced layer sizes and cache reuse in two OCI directory layouts."""
import argparse
import json
from pathlib import Path


def layers(directory):
    def blob_path(descriptor):
        algorithm, digest = descriptor['digest'].split(':')
        assert algorithm == 'sha256' and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
        path = directory / 'blobs/sha256' / digest
        assert path.stat().st_size == descriptor['size'], f'Incomplete OCI blob: {path}'
        return path

    index = json.loads((directory / 'index.json').read_text())
    assert len(index['manifests']) == 1, 'Expected a single-platform OCI image'
    manifest = json.loads(blob_path(index['manifests'][0]).read_text())
    for layer in manifest['layers']:
        blob_path(layer)
    return {item['digest']: item for item in manifest['layers']}


def compare(before, after):
    first, second = layers(before), layers(after)
    types = {item['mediaType'] for item in [*first.values(), *second.values()]}
    assert len(types) == 1, f'Use the same layer compression for both exports: {types}'
    before_bytes = sum(item['size'] for item in first.values())
    after_bytes = sum(item['size'] for item in second.values())
    return {'layer_media_type': next(iter(types)),
            'before': {'layers': len(first), 'bytes': before_bytes},
            'after': {'layers': len(second), 'bytes': after_bytes},
            'size_change_percent': round(100 * (after_bytes / before_bytes - 1), 2),
            'shared_layers': len(first.keys() & second.keys()),
            'new_layer_bytes': sum(item['size'] for digest, item in second.items() if digest not in first)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.before, args.after), indent=2))
