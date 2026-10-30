#!/usr/bin/env python3
"""Clean build-only state INSIDE the generated container, then declare /var dirs."""
import grp
import os
from pathlib import Path
import pwd
import shlex
import shutil
import stat
import subprocess


def clean_systemd_runtime(root=Path('/')):
    # systemd records its last unit-load timestamp here, including during build
    # tooling. This runtime-only marker must not survive into the bootc image.
    runtime = root / 'run/systemd'
    (runtime / 'systemd-units-load').unlink(missing_ok=True)
    # Leave unknown content for bootc's fatal lint rather than hiding it with a
    # recursive removal. Container-runtime-injected mounts must also stay intact.
    if runtime.is_dir() and not any(runtime.iterdir()):
        runtime.rmdir()


def main():
    # Refuse to run on a regular host, even if accidentally invoked with sudo.
    if not Path('/run/.containerenv').exists() or not Path('/run/gniri-build').is_dir():
        raise SystemExit('Image finalization must run inside the Gniri build container.')

    # These are generated caches/logs, not RPM-owned operating-system data. Reject
    # any unexpected state rather than removing unreviewed package content.
    for root, dirs, files in os.walk('/var', followlinks=False):
        dirs[:] = [d for d in dirs if not Path(root, d).is_symlink()]
        for name in files:
            path = Path(root, name)
            if path.is_symlink():
                continue
            if not any(str(path).startswith(prefix) for prefix in (
                '/var/cache/', '/var/log/', '/var/lib/flatpak/', '/var/lib/dnf/',
            )):
                raise SystemExit(f'Unreviewed persistent file in image: {path}')
            path.unlink()

    # Do not turn a build-time repository into an empty tmpfiles skeleton. The
    # runtime initializer creates a valid mutable store after package tmpfiles run;
    # Flatpak itself cannot open a repo/ directory without objects/ and config.
    flatpak_repo = Path('/var/lib/flatpak/repo')
    if flatpak_repo.exists():
        shutil.rmtree(flatpak_repo)

    # Regenerate our rules from the image's directories, not from our previous
    # output. Otherwise a derived/rebuilt image skips all old entries and then
    # overwrites the file that declared them, leaving /var without boot-time dirs.
    generated = Path('/usr/lib/tmpfiles.d/gniri-var.conf')
    generated.unlink(missing_ok=True)
    declared = set()
    configuration = subprocess.check_output(['systemd-tmpfiles', '--cat-config'], text=True)
    for line in configuration.splitlines():
        columns = shlex.split(line, comments=True)
        if len(columns) > 1:
            path = columns[1]
            for macro, value in (('%C', '/var/cache'), ('%S', '/var/lib'), ('%L', '/var/log')):
                path = path.replace(macro, value)
            declared.add(path)
    rules = ['# Generated from package-created directories; runtime data is not shipped.']
    for root, dirs, _ in os.walk('/var', followlinks=False):
        dirs[:] = sorted(d for d in dirs if not Path(root, d).is_symlink())
        for name in dirs:
            path = Path(root, name)
            if str(path) in declared:
                continue
            info = path.stat()
            user, group = pwd.getpwuid(info.st_uid).pw_name, grp.getgrgid(info.st_gid).gr_name
            rules.append(f'd {path} {stat.S_IMODE(info.st_mode):04o} {user} {group} - -')
    generated.write_text('\n'.join(rules) + '\n')
    for name in ('/run/dnf', '/run/gluster', '/run/selinux-policy', '/run/gniri-build'):
        path = Path(name)
        if path.exists():
            shutil.rmtree(path)
    # Package scriptlets create these empty runtime directories. OpenVPN's tmpfiles
    # rules and TuneD itself recreate them at runtime; reject unexpected contents.
    for name in ('/run/openvpn-client', '/run/openvpn-server', '/run/tuned'):
        path = Path(name)
        if path.exists():
            path.rmdir()
    clean_systemd_runtime()


if __name__ == '__main__':
    main()
