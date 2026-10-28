#!/usr/bin/env python3
"""Check NSS and shell access as an unprivileged desktop user, without a login."""
import os
from pathlib import Path
import pwd
import subprocess
import xml.etree.ElementTree as ET

# root-only validation can hide unreadable directories and missing vendor users.
assert os.geteuid() == 0, 'Run account validation inside the image build as root'
for name in ('root', 'gdm', 'polkitd'):
    pwd.getpwnam(name)
unprivileged = pwd.getpwnam('nobody')
subprocess.run([
    '/usr/bin/bash', '--noprofile', '--norc', '-ec',
    'getent passwd root gdm polkitd >/dev/null; '
    'getent group wheel gdm >/dev/null; '
    'test -r /etc/niri/config.kdl; '
    'test -r /etc/profile.d/gniri-home.sh; '
    'test -x /usr/bin/gniri-stage-update; '
    'test -x /usr/bin/ghostty; '
    'ghostty +version >/dev/null',
], user=unprivileged.pw_uid, group=unprivileged.pw_gid, extra_groups=[],
    cwd='/', check=True, env={**os.environ, 'HOME': '/nonexistent'})
rule = Path('/usr/share/polkit-1/rules.d/10-gniri-rpm-ostree.rules')
assert rule.is_file() and rule.stat().st_mode & 0o004, 'Missing readable desktop rpm-ostree policy'
registered = [action.attrib['id'] for path in Path('/usr/share/polkit-1/actions').glob('*.policy')
              for action in ET.parse(path).iter('action')]
for name in ('upgrade', 'rebase', 'rollback', 'repo-refresh'):
    assert registered.count('org.projectatomic.rpmostree1.' + name) == 1, \
        f'Missing or duplicate rpm-ostree action: {name}'
print('NSS, desktop defaults, shell and terminal executable accessible without root.')
