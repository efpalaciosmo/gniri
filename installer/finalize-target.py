#!/usr/bin/env python3
"""Migrate only Anaconda's physical-root fstab entry to OSTree rootflags.

Run from the installer, after target configuration, before the first boot.
composefs is the logical /, so remounting it with physical Btrfs/ext4 options
fails. Keep all other fstab entries and kernel arguments unchanged.
https://bugzilla.redhat.com/show_bug.cgi?id=2332319
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import re
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


def deployment_arguments(sysroot):
    deployments = sysroot.get_deployments()
    if len(deployments) != 1:
        raise RuntimeError(f'Expected one fresh installation deployment, got {len(deployments)}; '
                           'check that the target /boot is mounted')
    return deployments[0], shlex.split(deployments[0].get_bootconfig().get('options'))


def verify_arguments(before, after, flags):
    expected = [arg for arg in before if not arg.startswith(('rootflags=', 'ostree='))]
    actual = [arg for arg in after if not arg.startswith(('rootflags=', 'ostree='))]
    saved_flags = [arg for arg in after if arg.startswith('rootflags=')]
    if actual != expected or saved_flags != [f'rootflags={flags}']:
        raise RuntimeError('Saved boot arguments do not match the rootflags migration; keeping fstab')


def signed_origin(current, target):
    if not re.fullmatch(r'ghcr.io/[a-z0-9._/-]+:(stable|latest)', target):
        raise ValueError('Expected a published stable/latest update target')
    allowed = ('ostree-unverified-registry:' + target,
               'ostree-unverified-image:docker://' + target,
               'ostree-image-signed:docker://' + target)
    if current not in allowed:
        raise ValueError('Installed deployment origin differs from the requested update target')
    return 'ostree-image-signed:docker://' + target


def enroll_origin(sysroot, deployment, root, target):
    repository = target.rsplit(':', 1)[0]
    policy = json.loads((root / 'usr/share/gniri/bootc-policy.json').read_text())
    expected = [{'type': 'sigstoreSigned', 'keyPath': '/usr/share/gniri/keys/cosign.pub',
                 'signedIdentity': {'type': 'matchRepository'}}]
    if (policy != {'default': [{'type': 'reject'}], 'transports': {'docker': {repository: expected}}}
            or not (root / 'usr/share/gniri/keys/cosign.pub').read_text().strip()):
        raise ValueError('Installed image lacks the strict update policy and trust key')
    origin = deployment.get_origin()
    origin.set_string('origin', 'container-image-reference',
                      signed_origin(origin.get_string('origin', 'container-image-reference'), target))
    sysroot.write_origin_file(deployment, origin, None)


def finalize(physical, target=None):
    import gi
    gi.require_version('OSTree', '1.0')
    from gi.repository import Gio, OSTree

    physical = Path(physical).resolve()
    if physical == Path('/') or not os.path.ismount(physical):
        raise RuntimeError('Expected a mounted offline installation target, not the running root')
    sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
    sysroot.load(None)
    deployment, before = deployment_arguments(sysroot)
    root = Path(sysroot.get_deployment_directory(deployment).get_path())
    arguments = dict(argument.split('=', 1) if '=' in argument else (argument, '')
                     for argument in before)
    if not arguments.get('root'):
        raise RuntimeError('No root= kernel argument; refusing to remove the fstab fallback')
    existing_flags = arguments.get('rootflags', '')

    def write_flags(flags):
        if flags:
            subprocess.run(['ostree', 'admin', 'instutil', 'set-kargs',
                            f'--sysroot={physical}', '--merge', f'--replace=rootflags={flags}'],
                           check=True)
            # Read back the on-disk BLS configuration, not the cached deployment.
            saved = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
            saved.load(None)
            _, after = deployment_arguments(saved)
            verify_arguments(before, after, flags)

    changed = migrate_fstab(root / 'etc/fstab', existing_flags, write_flags)
    if target and target != 'localhost/gniri:development':
        # Use the public OSTree API on the offline target. Enroll before the
        # first boot so native rpm-ostree cannot start an unverified update.
        current = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
        current.load(None)
        selected, _ = deployment_arguments(current)
        enroll_origin(current, selected, root, target)
        saved = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
        saved.load(None)
        selected, _ = deployment_arguments(saved)
        if selected.get_origin().get_string('origin', 'container-image-reference') != \
                'ostree-image-signed:docker://' + target:
            raise RuntimeError('Signed update origin did not survive readback')
        current.unload()
        saved.unload()
        print(f'Installed signed update origin: {target}')
    sysroot.unload()
    print('Root fstab entry migrated to kernel arguments.' if changed else
          'No root fstab migration needed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sysroot')
    parser.add_argument('--target-ref')
    args = parser.parse_args()
    physical = args.sysroot
    if physical is None:
        from pyanaconda.core.configuration.anaconda import conf
        physical = conf.target.physical_root
    finalize(physical, args.target_ref)
