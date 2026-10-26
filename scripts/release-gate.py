#!/usr/bin/env python3
"""Require reviewed, artifact-specific evidence before stable promotion."""
import argparse
import json
from pathlib import Path
import re

CHECKS = ('offline-install', 'installer-regressions', 'gnome-login', 'niri-login',
          'secure-boot-install', 'secure-boot-update-rollback', 'selinux-composefs',
          'signed-update', 'unsigned-rejection', 'wrong-key-rejection',
          'lock-suspend', 'hardware', 'data-persistence', 'backup-restore')


def validate(record, digest, revision):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Invalid immutable payload digest')
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Expected a clean, full Git source revision')
    if record.get('payload_digest') != digest or record.get('source_revision') != revision:
        raise ValueError('Evidence belongs to a different image or source revision')
    if not re.fullmatch(r'[a-f0-9]{64}', record.get('iso_sha256', '')):
        raise ValueError('Record the tested ISO SHA-256')
    for field in ('candidate_run_id', 'candidate_run_attempt'):
        if not re.fullmatch(r'[1-9][0-9]*', str(record.get(field, ''))):
            raise ValueError(f'Record the exact GitHub Actions {field}')
    for name in CHECKS:
        check = record.get('checks', {}).get(name, {})
        if check.get('result') != 'pass' or not str(check.get('evidence', '')).startswith('https://'):
            raise ValueError(f'Missing passing result and durable evidence URL: {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('template', 'validate'))
    parser.add_argument('--digest', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', default='')
    parser.add_argument('--run-attempt', default='')
    parser.add_argument('--iso-sha256', default='')
    args = parser.parse_args()
    if args.action == 'template':
        record = {'payload_digest': args.digest, 'source_revision': args.revision,
                  'iso_sha256': args.iso_sha256, 'candidate_run_id': args.run_id,
                  'candidate_run_attempt': args.run_attempt,
                  'checks': {name: {'result': 'untested', 'evidence': ''} for name in CHECKS}}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(record, indent=2) + '\n')
    else:
        validate(json.loads(args.output.read_text()), args.digest, args.revision)
        print('Evidence complete. Human approval and artifact identity checks are still required.')


if __name__ == '__main__':
    main()
