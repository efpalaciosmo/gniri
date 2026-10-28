#!/usr/bin/env python3
"""Read-only checks from a real user's GNOME/Niri session in an installed VM."""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', choices=('gnome', 'niri'), required=True)
    args = parser.parse_args()
    if os.geteuid() == 0 or Path('/run/.containerenv').exists() or Path('/.dockerenv').exists():
        raise SystemExit('Run as the logged-in desktop user inside the installed VM, not root/a container.')
    account = pwd.getpwuid(os.geteuid())
    assert pwd.getpwnam(account.pw_name).pw_uid == os.geteuid()
    home = Path(account.pw_dir)
    assert home.is_dir() and home.stat().st_uid == account.pw_uid
    assert os.access(home, os.R_OK | os.W_OK | os.X_OK)
    assert Path(account.pw_shell).is_file() and os.access(account.pw_shell, os.X_OK)
    assert args.desktop in os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    assert os.environ.get('XDG_SESSION_TYPE') == 'wayland'
    assert output('systemctl', 'is-active', 'gdm.service') == 'active'
    assert output('systemctl', '--user', 'is-active', 'graphical-session.target') == 'active'
    assert output('getenforce') == 'Enforcing'
    options = set(output('findmnt', '-n', '-o', 'OPTIONS', '/').split(','))
    assert 'ro' in options, 'Installed root must remain read-only'
    assert output('ghostty', '+version')
    build = json.loads(Path('/usr/share/gniri/build.json').read_text())
    status = json.loads(output('bootc', 'status', '--json'))
    image = status['spec']['image']
    repository = build['image_reference'].rsplit(':', 1)[0]
    assert image['image'] in (repository + ':stable', repository + ':latest')
    assert image['transport'] == 'registry' and image['signature'] == 'containerPolicy'
    print(json.dumps({'result': 'pass', 'scope': 'booted-desktop-sanity', 'desktop': args.desktop,
                      'user': account.pw_name, 'uid': account.pw_uid,
                      'fedora_version': build['fedora_version'], 'source_revision': build['source_revision'],
                      'update_reference': image['image']}, indent=2))


if __name__ == '__main__':
    main()
