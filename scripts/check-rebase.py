#!/usr/bin/env python3
"""Read-only preflight; never rebase, rewrite accounts, or change user shells."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import subprocess


def validate(data, current_version, local_account):
    if not local_account:
        raise ValueError('The account is not local to /etc/passwd; test account migration before rebasing.')
    if not re.fullmatch(r'[1-9][0-9]*', str(data.get('fedora_version', ''))):
        raise ValueError('Target lacks numbered Fedora provenance')
    if int(data['fedora_version']) < int(current_version):
        raise ValueError('Refusing a rebase to an older Fedora release')
    if not data.get('shell_available'):
        raise ValueError('The target lacks your login shell; do not rebase until the migration is prepared.')
    if not data.get('gdm_available'):
        raise ValueError('The target cannot resolve its GDM account')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--key', type=Path, default=Path(__file__).resolve().parents[1] / 'trust/cosign.pub')
    args = parser.parse_args()
    if not re.fullmatch(r'ghcr.io/[a-z0-9._/-]+(?::(?:stable|latest)|@sha256:[a-f0-9]{64})', args.image):
        parser.error('Use a fully qualified stable/latest channel or immutable GHCR digest')
    if os.geteuid() == 0:
        parser.error('Run as the existing desktop user, not sudo/root')
    account = pwd.getpwuid(os.geteuid())
    entry = subprocess.run(['getent', '-s', 'files', 'passwd', account.pw_name],
                           text=True, capture_output=True, check=False)
    fields = entry.stdout.strip().split(':')
    local = (entry.returncode == 0 and len(fields) == 7 and fields[0] == account.pw_name
             and fields[2:4] == [str(account.pw_uid), str(account.pw_gid)])
    release = dict(line.split('=', 1) for line in Path('/usr/lib/os-release').read_text().splitlines()
                   if line and not line.startswith('#') and '=' in line)
    current = release.get('VERSION_ID', '').strip('"')
    fedora = (release.get('ID', '').strip('"') == 'fedora'
              or 'fedora' in release.get('ID_LIKE', '').strip('"').split())
    if not fedora or not current.isdecimal():
        raise ValueError('This preflight requires a numbered Fedora-based source system')
    digest = subprocess.check_output(['skopeo', 'inspect', '--format', '{{.Digest}}',
                                      'docker://' + args.image], text=True).strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('Could not resolve an immutable target')
    repository = args.image.split('@', 1)[0].rsplit(':', 1)[0]
    target = repository + '@' + digest
    subprocess.run(['cosign', 'verify', '--new-bundle-format=false', '--key', str(args.key), target], check=True)
    probe = '''import json, os, pwd, sys
from pathlib import Path
build=json.loads(Path('/usr/share/gniri/build.json').read_text())
try:
    pwd.getpwnam('gdm'); gdm=True
except KeyError:
    gdm=False
print(json.dumps(dict(fedora_version=build['fedora_version'], gdm_available=gdm,
                     shell_available=os.access(sys.argv[1], os.X_OK))))
'''
    data = json.loads(subprocess.check_output([
        'podman', 'run', '--rm', '--network=none', '--read-only', '--user=65534:65534',
        '--cap-drop=all', '--security-opt=no-new-privileges', '--entrypoint=python3',
        target, '-c', probe, account.pw_shell], text=True))
    validate(data, current, local)
    print(f'Preflight passed: Fedora {current} -> {data["fedora_version"]}; local account and shell retained.')
    print('This does not execute or validate a rebase. Test the transition and recovery on a disposable copy first.')


if __name__ == '__main__':
    main()
