#!/usr/bin/env python3
"""Resolve Fedora's stable channel once, then build from an immutable base."""
import argparse
import json
import re
import subprocess

CHANNEL = 'quay.io/fedora/fedora-bootc:latest'


def stable_base(manifest):
    matches = [entry for entry in manifest['manifests']
               if entry.get('platform', {}).get('architecture') == 'amd64'
               and entry['platform'].get('os') == 'linux']
    if len(matches) != 1 or not re.fullmatch(r'sha256:[a-f0-9]{64}', matches[0]['digest']):
        raise ValueError('Expected exactly one Linux x86_64 Fedora stable manifest')
    return f"{CHANNEL}@{matches[0]['digest']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--reference', required=True)
    parser.add_argument('--source', default='')
    parser.add_argument('--revision', default='unknown')
    parser.add_argument('--network', default='')
    parser.add_argument('--fresh', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(subprocess.check_output(['podman', 'manifest', 'inspect', CHANNEL]))
    base = stable_base(manifest)
    print(f'Fedora stable base: {base}', flush=True)
    command = ['podman', 'build', '--platform=linux/amd64', '--layers']
    if args.fresh:
        command.append('--no-cache')
    if args.network:
        command.append(f'--network={args.network}')
    for name, value in (('BASE_IMAGE', base), ('IMAGE_REF', args.reference),
                        ('SOURCE_URL', args.source), ('SOURCE_REVISION', args.revision)):
        command.extend(['--build-arg', f'{name}={value}'])
    subprocess.run([*command, '-t', args.image, '.'], check=True)


if __name__ == '__main__':
    main()
