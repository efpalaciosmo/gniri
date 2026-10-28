import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'ghcr.io/example/gniri'
DIGEST = 'sha256:' + 'a' * 64


class RegistryPolicyTests(unittest.TestCase):
    """Exercise CI orchestration without sudo, a registry, or real credentials."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / 'commands.jsonl'
        client = self.directory / 'client'
        client.write_text('''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([name, *args]) + '\\n')
if name == 'podman':
    if args[0] == 'login':
        assert args[1] == 'ghcr.io'
        assert args[args.index('--username') + 1] == 'ci-actor'
        assert '--password-stdin' in args
        assert sys.stdin.read() == os.environ['REGISTRY_TOKEN']
        if os.environ.get('FAIL_LOGIN') == '1':
            sys.exit(7)
        auth = Path(args[args.index('--authfile') + 1])
        assert auth.parent.stat().st_mode & 0o777 == 0o700
        auth.write_text(json.dumps({'auths': {'ghcr.io': {'auth': 'test-only'}}}))
    elif args[0] == 'build':
        assert 'LABEL gniri.policy-test=' in sys.stdin.read()
    elif args[0] == 'push':
        Path(args[args.index('--digestfile') + 1]).write_text('sha256:' + 'b' * 64)
    elif args[0] == 'run':
        mounts = [args[i + 1] for i, arg in enumerate(args) if arg == '-v']
        auth_mounts = [mount for mount in mounts if ':/run/registry-auth.json:' in mount]
        assert len(auth_mounts) == 1
        source, destination, mode = auth_mounts[0].split(':')
        assert mode == 'ro'
        assert 'ghcr.io' in json.loads(Path(source).read_text())['auths']
        assert '--rm' in args
        assert args[-3].startswith('ghcr.io/example/gniri@sha256:')
        sys.exit(int(os.environ.get('SMOKE_EXIT', '0')))
    else:
        sys.exit(99)
elif name == 'openssl':
    print('test-only-password')
elif name != 'cosign':
    sys.exit(99)
''')
        client.chmod(0o755)
        for name in ('podman', 'cosign', 'openssl'):
            (self.directory / name).symlink_to(client)
        sudo = self.directory / 'sudo'
        sudo.write_text('#!/usr/bin/env bash\nset -euo pipefail\nexec "$@"\n')
        sudo.chmod(0o755)

    def run_recipe(self, **variables):
        env = dict(os.environ, PATH=str(self.directory) + os.pathsep + os.environ['PATH'],
                   TMPDIR=str(self.directory), COMMAND_LOG=str(self.log), GITHUB_ACTIONS='true',
                   GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1', GITHUB_ACTOR='ci-actor',
                   REGISTRY_TOKEN='test-only-token', **variables)
        result = subprocess.run(['bash', str(ROOT / 'scripts/check-registry-policy.sh'),
                                 'localhost/gniri:build', REPOSITORY, DIGEST],
                                cwd=ROOT, env=env, text=True, capture_output=True)
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, commands

    def assert_auth_removed(self, commands):
        login = commands[0]
        self.assertEqual(login[:2], ['podman', 'login'])
        auth = Path(login[login.index('--authfile') + 1])
        self.assertFalse(auth.parent.exists(), 'Temporary credentials must be cleaned up')

    def test_private_registry_credentials_are_mounted_readonly_and_removed(self):
        result, commands = self.run_recipe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(commands[-1][:2], ['podman', 'run'])
        self.assert_auth_removed(commands)
        self.assertNotIn('test-only-token', self.log.read_text() + result.stdout + result.stderr)

    def test_failed_registry_login_stops_before_building_or_testing(self):
        result, commands = self.run_recipe(FAIL_LOGIN='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(commands), 1)
        self.assert_auth_removed(commands)

    def test_smoke_failure_is_propagated_and_credentials_are_removed(self):
        result, commands = self.run_recipe(SMOKE_EXIT='9')
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assert_auth_removed(commands)

    def test_every_registry_read_uses_auth_without_weakening_signature_policy(self):
        smoke = (ROOT / 'tests/signature-smoke.sh').read_text()
        reads = [line.strip() for line in smoke.splitlines() if 'skopeo ' in line]
        self.assertEqual(len(reads), 3)
        for line in reads:
            self.assertIn('--authfile "$authfile"', line)
            if ' copy ' in line:
                self.assertIn('--policy "$policy"', line)
                self.assertIn('copy --authfile', line)
                self.assertIn('--remove-signatures', line)
            else:
                self.assertIn('inspect --authfile', line)
        self.assertIn('authfile=/run/registry-auth.json', smoke)
        self.assertIn('[[ -s $authfile ]]', smoke)
        self.assertIn('grep -Ei "$expected"', smoke)
        self.assertNotIn('--insecure-policy', smoke)
        self.assertNotIn('--tls-verify=false', smoke)

    def test_real_transport_regression_runs_before_publication_even_for_pull_requests(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        step = workflow.split('      - name: Offline signature transport regression\n', 1)[1].split('      - ', 1)[0]
        self.assertNotIn('if:', step)
        self.assertIn('--network=none', step)
        self.assertIn('localhost/gniri:build /src/tests/signature-transport-smoke.py', step)
        self.assertLess(workflow.index('Offline signature transport regression'),
                        workflow.index('name: Publish signed candidate'))
