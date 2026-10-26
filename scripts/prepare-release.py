#!/usr/bin/env python3
"""Bind reviewed evidence to a successful Actions ISO and prepare release assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil

validate = runpy.run_path(str(Path(__file__).with_name('release-gate.py')))['validate']
ISO_NAME = 'gniri-x86_64.iso'
PART_SIZE = 1024 ** 3  # GitHub release assets must be smaller than 2 GiB.


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare_release(artifacts, output, record, run, repository, part_size=PART_SIZE):
    digest, revision = record['payload_digest'], record['source_revision']
    validate(record, digest, revision)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid GitHub repository')
    if (str(run.get('id')) != str(record['candidate_run_id'])
            or str(run.get('run_attempt')) != str(record['candidate_run_attempt'])
            or run.get('repository', {}).get('full_name') != repository
            or run.get('head_repository', {}).get('full_name') != repository
            or run.get('head_branch') != 'main'
            or run.get('event') not in ('push', 'schedule', 'workflow_dispatch')
            or run.get('path') not in ('.github/workflows/build.yml', '.github/workflows/iso.yml')
            or run.get('conclusion') != 'success'):
        raise ValueError('Expected the exact successful, trusted main-branch candidate run')
    for name in (ISO_NAME, 'SHA256SUMS', 'build.json', 'validation.json'):
        path = artifacts / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f'Missing regular candidate artifact: {name}')
    metadata = json.loads((artifacts / 'build.json').read_text())
    template = json.loads((artifacts / 'validation.json').read_text())
    image = f'ghcr.io/{repository.split("/")[0].lower()}/gniri'
    expected_checksum = f'{record["iso_sha256"]}  {ISO_NAME}'
    if (metadata.get('payload_reference') != f'{image}@{digest}'
            or metadata.get('source_revision') != revision
            or metadata.get('installer_source_revision') != run.get('head_sha')
            or not re.fullmatch(r'[a-f0-9]{40}', str(run.get('head_sha', '')))
            or metadata.get('update_reference') != f'{image}:stable'
            or metadata.get('iso_checksum') != expected_checksum
            or (artifacts / 'SHA256SUMS').read_text().strip() != expected_checksum):
        raise ValueError('ISO provenance does not match the reviewed candidate')
    for field in ('payload_digest', 'source_revision', 'iso_sha256',
                  'candidate_run_id', 'candidate_run_attempt'):
        if str(template.get(field)) != str(record[field]):
            raise ValueError(f'Candidate template differs from reviewed evidence: {field}')
    iso = artifacts / ISO_NAME
    if iso.stat().st_size == 0 or checksum(iso) != record['iso_sha256']:
        raise ValueError('Downloaded ISO differs from the tested ISO checksum')
    if part_size <= 0 or part_size > PART_SIZE:
        raise ValueError('Invalid release part size')
    output.mkdir(parents=True, exist_ok=False)
    split = iso.stat().st_size > part_size
    if split:
        with iso.open('rb') as source:
            for index in range((iso.stat().st_size + part_size - 1) // part_size):
                with (output / f'{ISO_NAME}.part-{index + 1:04d}').open('wb') as target:
                    remaining = part_size
                    while remaining:
                        data = source.read(min(8 * 1024 ** 2, remaining))
                        if not data:
                            break
                        target.write(data)
                        remaining -= len(data)
    else:
        shutil.copyfile(iso, output / ISO_NAME)
    (output / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'validation.json').write_text(json.dumps(record, indent=2) + '\n')
    run_id, attempt = record['candidate_run_id'], record['candidate_run_attempt']
    reassemble = f'cat {ISO_NAME}.part-* > {ISO_NAME}\n' if split else ''
    notes = (f'# Gniri x86_64\n\nPayload: `{image}@{digest}`\n\n'
             f'Source revision: `{revision}`\n\n'
             f'[Candidate build](https://github.com/{repository}/actions/runs/{run_id}/attempts/{attempt}). '
             'The ISO is the reviewed artifact, not a rebuild. See `validation.json` for evidence.\n\n'
             'Download every release asset into one directory. Obtain `trust/cosign.pub` from an '
             'independently trusted checkout of this repository, not from an unverified download. '
             'Verify the signed manifest before reassembling and checking the ISO:\n\n```sh\n'
             'cosign verify-blob --key trust/cosign.pub --bundle SHA256SUMS.bundle SHA256SUMS\n'
             f'{reassemble}sha256sum --check SHA256SUMS\n```\n\n'
             'Numbered parts keep large ISOs below GitHub\'s per-asset size limit. '
             'Do not write an individual part to installation media.\n')
    (output / 'release-notes.md').write_text(notes)
    sums = {ISO_NAME: record['iso_sha256']}
    for path in output.iterdir():
        sums[path.name] = checksum(path)
    (output / 'SHA256SUMS').write_text(''.join(f'{value}  {name}\n' for name, value in sorted(sums.items())))
    return f'gniri-{run_id}-{attempt}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    print(prepare_release(args.artifacts, args.output, json.loads(args.evidence.read_text()),
                          json.loads(args.run.read_text()), args.repository))


if __name__ == '__main__':
    main()
