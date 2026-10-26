#!/usr/bin/env python3
"""Exercise OSTree's real policy precheck offline, not a mocked command.

Run in the published candidate container with --network=none. This only tests
the global-default regression; live signature and booted-host tests are separate.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    if not Path('/run/.containerenv').exists():
        raise SystemExit('Run only in a disposable candidate container without networking.')
    reference = Path('/usr/share/gniri/image-reference').read_text().strip()
    if not reference.startswith('ghcr.io/'):
        raise SystemExit('This test requires the published-image policy configuration.')
    strict = json.loads(Path('/usr/share/gniri/bootc-policy.json').read_text())
    with tempfile.TemporaryDirectory(prefix='gniri-policy-', dir='/var/tmp') as temporary:
        root = Path(temporary)
        repo = root / 'repo'
        subprocess.run(['ostree', f'--repo={repo}', 'init', '--mode=bare-user'], check=True)
        for insecure in (True, False):
            policy = {**strict, 'default': [{'type': 'insecureAcceptAnything'}]} if insecure else strict
            path = root / 'policy.json'
            path.write_text(json.dumps(policy))
            result = subprocess.run(['ostree', 'container', 'image', 'pull', '--auth-anonymous',
                                     str(repo), f'ostree-image-signed:docker://{reference}'],
                                    env=dict(os.environ, CONTAINERS_POLICY_JSON=str(path)),
                                    text=True, capture_output=True, timeout=30)
            error = result.stdout + result.stderr
            assert result.returncode != 0, 'This test must not have registry networking'
            precheck_failed = 'default of `insecureAcceptAnything`' in error
            assert precheck_failed == insecure, error
            if not insecure:
                assert any(token in error.lower() for token in
                           ('network is unreachable', 'could not resolve', 'no such host',
                            'network is down', 'network unreachable',
                            'temporary failure in name resolution')), error
            print(f'PASS real policy precheck insecure_default={insecure}', flush=True)


if __name__ == '__main__':
    main()
