import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIGEST = 'sha256:' + 'a' * 64


@unittest.skipIf(os.geteuid() == 0, 'Exercises the unprivileged installer entry point')
class PublishedInstallerTests(unittest.TestCase):
    def run_recipe(self, target='ghcr.io/example/gniri:stable', **variables):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            log = directory / 'commands.jsonl'
            client = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name
with open(os.environ['COMMAND_LOG'],'a') as stream:
    stream.write(json.dumps([name, *sys.argv[1:]])+'\\n')
if name=='skopeo': print(os.environ['MOCK_DIGEST'])
if name=='cosign': sys.exit(int(os.environ.get('VERIFY_EXIT','0')))
'''
            for name in ('skopeo', 'cosign', 'sudo'):
                path = directory / name
                path.write_text(client)
                path.chmod(0o755)
            env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'],
                       COMMAND_LOG=str(log), MOCK_DIGEST=DIGEST, **variables)
            result = subprocess.run(['/usr/bin/bash', str(ROOT / 'scripts/build-published-iso.sh'),
                                     target, 'host', '1'], cwd=ROOT, env=env,
                                    text=True, capture_output=True)
            commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, commands

    def test_resolution_binds_signature_and_installer_to_the_same_digest(self):
        result, calls = self.run_recipe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in calls], ['skopeo', 'cosign', 'sudo'])
        self.assertEqual(calls[1][-1], 'ghcr.io/example/gniri@' + DIGEST)
        self.assertEqual(calls[2], ['sudo', 'bash', 'scripts/build-iso.sh',
                                  'ghcr.io/example/gniri@' + DIGEST,
                                  'ghcr.io/example/gniri:stable', 'host', '1'])

    def test_invalid_target_or_failed_signature_cannot_start_privileged_build(self):
        result, calls = self.run_recipe(target='localhost/gniri:development')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        result, calls = self.run_recipe(VERIFY_EXIT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('sudo', [call[0] for call in calls])
