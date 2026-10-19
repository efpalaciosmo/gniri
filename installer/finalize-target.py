#!/usr/bin/env python3
"""Migrate only Anaconda's physical-root fstab entry to OSTree rootflags.

Run from the installer, after target configuration, before the first boot.
composefs is the logical /, so remounting it with physical Btrfs/ext4 options
fails. Keep all other fstab entries and kernel arguments unchanged.
https://bugzilla.redhat.com/show_bug.cgi?id=2332319
"""
import argparse
import os
from pathlib import Path
import shutil
import shlex
import subprocess


def plan_root_mount(fstab, existing_flags):
    lines = fstab.splitlines(keepends=True)
    roots = [(index, line.split()) for index, line in enumerate(lines)
             if line.strip() and not line.lstrip().startswith('#')
             and len(line.split()) >= 2 and line.split()[1] == '/']
    if not roots:
        return fstab, None
    if len(roots) != 1 or len(roots[0][1]) < 4:
        raise ValueError('Expected exactly one well-formed physical-root fstab entry')
    index, fields = roots[0]
    if fields[2] in {'overlay', 'composefs', 'tmpfs'}:
        raise ValueError('Expected a physical filesystem, not a virtual root')

    flags = {}
    for option in filter(None, existing_flags.split(',')):
        flags[option.split('=', 1)[0]] = option
    for option in fields[3].split(','):
        if option in {'defaults', 'auto', 'noauto', 'nofail', '_netdev', 'ro', 'rw'}:
            continue
        if option.startswith(('x-', 'comment=')):
            continue
        flags[option.split('=', 1)[0]] = option
    lines[index] = '# Physical root is mounted by the initramfs via root=/rootflags=.\n'
    return ''.join(lines), ','.join(flags.values())


def migrate_fstab(path, existing_flags, write_kernel_flags):
    original = path.read_text()
    updated, flags = plan_root_mount(original, existing_flags)
    if flags is None:
        return False
    # Never remove the root entry if updating the boot configuration fails.
    write_kernel_flags(flags)
    backup = path.with_name('fstab.gniri-before-rootflags')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated)
    return True


def finalize(physical):
    import gi
    gi.require_version('OSTree', '1.0')
    from gi.repository import Gio, OSTree

    physical = Path(physical).resolve()
    if physical == Path('/') or not os.path.ismount(physical):
        raise RuntimeError('Expected a mounted offline installation target, not the running root')
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
    sysroot.load(None)
    deployments = sysroot.get_deployments()
    if len(deployments) != 1:
        raise RuntimeError(f'Expected one fresh installation deployment, got {len(deployments)}; '
                           'check that the target /boot is mounted')
    deployment = deployments[0]
    root = Path(sysroot.get_deployment_directory(deployment).get_path())
    arguments = dict(argument.split('=', 1) if '=' in argument else (argument, '')
                     for argument in shlex.split(deployment.get_bootconfig().get('options')))
    if not arguments.get('root'):
        raise RuntimeError('No root= kernel argument; refusing to remove the fstab fallback')
    existing_flags = arguments.get('rootflags', '')

    def write_flags(flags):
        if flags:
            subprocess.run(['ostree', 'admin', 'instutil', 'set-kargs',
                            f'--sysroot={physical}', '--merge', f'--replace=rootflags={flags}'],
                           check=True)

    changed = migrate_fstab(root / 'etc/fstab', existing_flags, write_flags)
    print('Root fstab entry migrated to kernel arguments.' if changed else
          'No root fstab migration needed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sysroot')
    target = parser.parse_args().sysroot
    if target is None:
        from pyanaconda.core.configuration.anaconda import conf
        target = conf.target.physical_root
    finalize(target)
