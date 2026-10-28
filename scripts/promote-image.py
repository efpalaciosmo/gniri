#!/usr/bin/env python3
"""Validate a reviewed candidate, then promote only in the protected stable job."""
import argparse
import json
import os
from pathlib import Path
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GATE = runpy.run_path(str(ROOT / 'scripts/release-gate.py'))['validate']
FEDORA_VERSION = runpy.run_path(str(ROOT / 'scripts/build-image.py'))['fedora_version']


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def validate_run(record, run, repository):
    GATE(record, record['payload_digest'], record['source_revision'])
    if (str(run.get('id')) != str(record['candidate_run_id'])
            or str(run.get('run_attempt')) != str(record['candidate_run_attempt'])
            or run.get('repository', {}).get('full_name') != repository
            or run.get('head_repository', {}).get('full_name') != repository
            or run.get('head_branch') != 'main'
            or run.get('head_sha') != record['source_revision']
            or run.get('event') not in ('push', 'schedule', 'workflow_dispatch')
            or run.get('path') != '.github/workflows/build.yml'
            or run.get('conclusion') != 'success'):
        raise ValueError('Evidence must identify the exact successful main-branch build run')


def validate_environment(environment, branches):
    review = [rule for rule in environment.get('protection_rules', [])
              if rule.get('type') == 'required_reviewers' and rule.get('reviewers')]
    if (environment.get('name') != 'stable' or not review
            or environment.get('deployment_branch_policy') != {
                'protected_branches': False, 'custom_branch_policies': True}
            or branches.get('total_count') != 1
            or len(branches.get('branch_policies', [])) != 1
            or branches['branch_policies'][0].get('name') != 'main'
            or branches['branch_policies'][0].get('type') != 'branch'):
        raise ValueError('stable must require human review and allow only branch main')


def validate_candidate(metadata, labels, record, image, previous_version):
    version = metadata.get('fedora_version', '')
    if (not re.fullmatch(r'[1-9][0-9]*', str(version))
            or labels.get('org.opencontainers.image.version') != str(version)
            or metadata.get('source_revision') != record['source_revision']
            or labels.get('org.opencontainers.image.revision') != record['source_revision']
            or metadata.get('image_reference') != image + ':stable'
            or metadata.get('channel') != 'quay.io/fedora/fedora-bootc:latest'
            or not re.fullmatch(r'quay.io/fedora/fedora-bootc:latest@sha256:[a-f0-9]{64}',
                                metadata.get('base_image', ''))):
        raise ValueError('Candidate provenance, version or stable update target is inconsistent')
    if int(version) < int(previous_version):
        raise ValueError(f'Refusing stable Fedora downgrade: {previous_version} -> {version}')
    return str(version)


def image_file(reference, path):
    return command('podman', 'run', '--rm', '--network=none', '--read-only',
                   '--user=65534:65534', '--cap-drop=all', '--security-opt=no-new-privileges',
                   '--entrypoint=cat', reference, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'promote'))
    parser.add_argument('--repository', required=True)
    parser.add_argument('--digest', required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--environment', type=Path, required=True)
    parser.add_argument('--branches', type=Path, required=True)
    parser.add_argument('--expected-stable')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('Expected GitHub OWNER/REPOSITORY')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', args.digest):
        parser.error('Expected an immutable candidate digest')
    if args.action == 'promote' and (
            os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_REF') != 'refs/heads/main'
            or os.environ.get('GNIRI_STABLE_REVIEWED') != '1'
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', args.expected_stable or '')):
        raise ValueError('Promotion is restricted to the reviewed stable workflow job')
    record = json.loads((ROOT / 'release-evidence' / (args.digest[7:] + '.json')).read_text())
    if record.get('payload_digest') != args.digest:
        raise ValueError('Evidence filename and payload identity differ')
    validate_run(record, json.loads(args.run.read_text()), args.repository)
    validate_environment(json.loads(args.environment.read_text()), json.loads(args.branches.read_text()))
    image = 'ghcr.io/' + args.repository.lower()
    candidate, stable = image + '@' + args.digest, image + ':stable'
    baseline = json.loads(command('skopeo', 'inspect', 'docker://' + stable))['Digest']
    if args.expected_stable and baseline != args.expected_stable:
        raise ValueError('stable changed while awaiting review; validate and review again')
    for reference in (candidate, image + '@' + baseline):
        subprocess.run(['cosign', 'verify', '--new-bundle-format=false', '--key',
                        str(ROOT / 'trust/cosign.pub'), reference], check=True)
    previous = FEDORA_VERSION(image_file(image + '@' + baseline, '/usr/lib/os-release'))
    metadata = json.loads(image_file(candidate, '/usr/share/gniri/build.json'))
    if FEDORA_VERSION(image_file(candidate, '/usr/lib/os-release')) != str(metadata.get('fedora_version')):
        raise ValueError('Candidate Fedora provenance differs from its actual os-release')
    labels = json.loads(command('skopeo', 'inspect', 'docker://' + candidate))['Labels']
    version = validate_candidate(metadata, labels, record, image, previous)
    if args.action == 'promote':
        if json.loads(command('skopeo', 'inspect', 'docker://' + stable))['Digest'] != baseline:
            raise ValueError('stable changed during validation; review again')
        subprocess.run(['skopeo', 'copy', '--all', '--preserve-digests',
                        'docker://' + candidate, 'docker://' + stable], check=True)
        if json.loads(command('skopeo', 'inspect', 'docker://' + stable))['Digest'] != args.digest:
            raise RuntimeError('stable does not resolve to the reviewed candidate')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('baseline=' + baseline + '\n')
    print(f'{args.action}: {candidate}; Fedora {previous} -> {version}; update channel {stable}')


if __name__ == '__main__':
    main()
