#!/usr/bin/env python3
"""Bootstrap GitHub promotion settings using an authenticated administrator's CLI."""
import argparse
import json
import re
import subprocess


def api(endpoint, method='GET', payload=None, optional=False):
    command = ['gh', 'api', '--method', method, endpoint]
    if payload is not None:
        command += ['--input', '-']
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True)
    if result.returncode:
        if optional and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(f'GitHub API request failed: {method} {endpoint}\n{result.stderr.strip()}')
    return json.loads(result.stdout) if result.stdout.strip() else None


def branch_policies(endpoint):
    policies = []
    page = 1
    while True:
        response = api(f'{endpoint}/deployment-branch-policies?per_page=100&page={page}')
        policies.extend(response['branch_policies'])
        if len(policies) >= response['total_count']:
            return policies
        page += 1


def configure(repository, reviewer, make_public=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Expected OWNER/REPOSITORY')
    if not re.fullmatch(r'[A-Za-z0-9-]+', reviewer):
        raise ValueError('Expected a GitHub reviewer login')
    repo = api(f'repos/{repository}')
    if not repo.get('permissions', {}).get('admin'):
        raise ValueError('Authenticate gh with repository administration access')
    if repo.get('default_branch') != 'main':
        raise ValueError('Gniri requires main as its default branch')
    if repo.get('private') and not make_public:
        raise ValueError('Review repository history, then explicitly allow --make-public; no settings changed')
    user = api(f'users/{reviewer}')
    permission = api(f'repos/{repository}/collaborators/{reviewer}/permission')
    if permission.get('permission') not in ('read', 'triage', 'write', 'maintain', 'admin'):
        raise ValueError('Reviewer must already have read access to the repository')
    result = subprocess.run(['gh', 'secret', 'list', '--repo', repository, '--json', 'name'],
                            check=True, text=True, capture_output=True)
    secrets = {item['name'] for item in json.loads(result.stdout)}
    missing = {'COSIGN_PRIVATE_KEY', 'COSIGN_PASSWORD'} - secrets
    if missing:
        raise ValueError(f'Configure existing signing material first: {sorted(missing)}; no keys were generated or rotated')
    if repo.get('private'):
        subprocess.run(['gh', 'repo', 'edit', repository, '--visibility', 'public',
                        '--accept-visibility-change-consequences'], check=True)
        if api(f'repos/{repository}').get('private'):
            raise ValueError('GitHub did not confirm public repository visibility')
    endpoint = f'repos/{repository}/environments/stable'
    existing = api(endpoint, optional=True)
    policies = branch_policies(endpoint) if existing else []
    if any(policy.get('name') != 'main' or policy.get('type') != 'branch' for policy in policies):
        raise ValueError('Unexpected existing deployment policies; refusing to delete or replace them')
    api(endpoint, 'PUT', {
        # A solo maintainer must be able to approve their own manually started run.
        # Required review is retained: no workflow automatically approves a job.
        'prevent_self_review': False,
        'reviewers': [{'type': 'User', 'id': user['id']}],
        'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
    })
    if not policies:
        api(f'{endpoint}/deployment-branch-policies', 'POST', {'name': 'main', 'type': 'branch'})
    environment = api(endpoint)
    required = [rule for rule in environment.get('protection_rules', [])
                if rule.get('type') == 'required_reviewers']
    reviewers = [item for rule in required for item in rule.get('reviewers', [])]
    if (not required or any(rule.get('prevent_self_review') is not False for rule in required)
            or len(reviewers) != 1 or reviewers[0].get('type') != 'User'
            or reviewers[0].get('reviewer', {}).get('id') != user['id']
            or environment.get('deployment_branch_policy') != {
                'protected_branches': False, 'custom_branch_policies': True}):
        raise ValueError('Required reviewer/branch protection was not confirmed by GitHub')
    policies = branch_policies(endpoint)
    if len(policies) != 1 or policies[0].get('name') != 'main' or policies[0].get('type') != 'branch':
        raise ValueError('Expected exactly one deployment policy: branch main')
    print(f'Configured and verified: {repository} is public; stable requires {reviewer}, branch main only.')
    print('Existing signing secrets were preserved. Approval remains a human action.')
    owner = repository.split('/')[0]
    print('GHCR visibility is separate and has no documented update API. If anonymous pulls fail, '
          f'make the package public once at https://github.com/users/{owner}/packages/container/gniri/settings')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--reviewer', required=True)
    parser.add_argument('--make-public', action='store_true',
                        help='Explicitly authorize publishing repository contents and history after reviewing them')
    args = parser.parse_args()
    try:
        configure(args.repository, args.reviewer, args.make_public)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
