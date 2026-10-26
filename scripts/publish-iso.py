#!/usr/bin/env python3
"""Publish exactly one newly built ISO, not an artifact left by an earlier run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile


def publish_iso(source, destination, metadata=None):
    record = json.loads(metadata.read_text()) if metadata is not None else None
    if metadata is not None and not isinstance(record, dict):
        raise ValueError('ISO input metadata must be a JSON object')
    candidates = sorted(path for path in source.rglob('*.iso')
                        if path.is_file() and not path.is_symlink())
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one new ISO in {source}, found {len(candidates)}. '
                         'See output/iso-build.log; the previous ISO was not replaced.')
    artifact = candidates[0]
    if artifact.stat().st_size == 0:
        raise ValueError(f'The generated ISO is empty: {artifact}')

    digest = hashlib.sha256()
    with artifact.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)

    destination.mkdir(parents=True, exist_ok=True)
    # Gniri currently supports only an x86_64 host image, not ARM host ISOs.
    output = destination / 'gniri-x86_64.iso'
    descriptor, checksum_name = tempfile.mkstemp(prefix='.SHA256SUMS.', dir=destination)
    checksum = Path(checksum_name)
    manifest = None
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(f'{digest.hexdigest()}  {output.name}\n')
        checksum.chmod(0o644)
        artifact.chmod(0o644)
        if record is not None:
            record['iso_checksum'] = f'{digest.hexdigest()}  {output.name}'
            descriptor, name = tempfile.mkstemp(prefix='.build.', dir=destination)
            manifest = Path(name)
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(record, stream, indent=2)
                stream.write('\n')
            manifest.chmod(0o644)
        # Staging and publication both live under output/ on the same filesystem.
        # Replace the old artifact only after validating and hashing the new one.
        artifact.replace(output)
        checksum.replace(destination / 'SHA256SUMS')
        if manifest is not None:
            manifest.replace(destination / 'build.json')
    finally:
        checksum.unlink(missing_ok=True)
        if manifest is not None:
            manifest.unlink(missing_ok=True)
    print(f'ISO ready: {output.resolve()}')
    print(f'SHA-256: {digest.hexdigest()}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--metadata', type=Path)
    arguments = parser.parse_args()
    try:
        publish_iso(arguments.source, arguments.destination, arguments.metadata)
    except (OSError, ValueError) as error:
        parser.exit(1, f'ISO publication failed: {error}\n')
