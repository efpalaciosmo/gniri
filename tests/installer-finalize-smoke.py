#!/usr/bin/env python3
"""Exercise finalization against real OSTree boot entries on disposable tmpfs.

Run with sudo make check-installer: --network=none --cap-add SYS_ADMIN,
--security-opt apparmor=unconfined and the repository read-only at /src.
No host disks are mounted.
"""
import importlib.util
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def check_layout(separate_boot):
    spec = importlib.util.spec_from_file_location('finalizer', '/src/installer/finalize-target.py')
    finalizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(finalizer)
    with tempfile.TemporaryDirectory(prefix='gniri-finalize-', dir='/var/tmp') as temporary:
        sysroot = saved = None
        base = Path(temporary)
        physical, tree = base / 'target', base / 'tree'
        physical.mkdir()
        run('mount', '-t', 'tmpfs', 'gniri-finalize-root', physical)
        try:
            (physical / 'boot').mkdir()
            if separate_boot:
                run('mount', '-t', 'tmpfs', 'gniri-finalize-boot', physical / 'boot')
            run('ostree', 'admin', f'--sysroot={physical}', 'init-fs', physical)
            repo = physical / 'ostree/repo'
            run('ostree', f'--repo={repo}', 'config', 'set', 'sysroot.bootloader', 'none')
            run('ostree', 'admin', f'--sysroot={physical}', 'os-init', 'default')
            (tree / 'usr/etc').mkdir(parents=True)
            (tree / 'var').mkdir()
            (tree / 'usr/lib').mkdir()
            (tree / 'usr/lib/os-release').write_text('ID=fedora\nVERSION_ID=45\n')
            trust = tree / 'usr/share/gniri'
            (trust / 'keys').mkdir(parents=True)
            shutil.copyfile('/usr/share/gniri/keys/cosign.pub', trust / 'keys/cosign.pub')
            target = 'ghcr.io/example/gniri:stable'
            (trust / 'bootc-policy.json').write_text(json.dumps({
                'default': [{'type': 'reject'}], 'transports': {'docker': {
                    'ghcr.io/example/gniri': [{'type': 'sigstoreSigned',
                        'keyPath': '/usr/share/gniri/keys/cosign.pub',
                        'signedIdentity': {'type': 'matchRepository'}}]}}}))
            # Real kernel/initramfs layout; the smoke test does not boot it.
            kernel = next(Path('/usr/lib/modules').glob('*/vmlinuz'))
            destination = tree / 'usr/lib/modules' / kernel.parent.name
            destination.mkdir(parents=True)
            shutil.copyfile(kernel, destination / 'vmlinuz')
            shutil.copyfile(kernel.parent / 'initramfs.img', destination / 'initramfs.img')
            original = ('UUID=root / btrfs subvol=root,compress=zstd:1 0 0\n'
                        'UUID=boot /boot ext4 defaults 1 2\n'
                        'UUID=home /home btrfs subvol=home 0 0\n')
            (tree / 'usr/etc/fstab').write_text(original)
            run('ostree', f'--repo={repo}', 'commit', '-b', 'test', f'--tree=dir={tree}', '--no-xattrs')
            run('ostree', 'admin', f'--sysroot={physical}', 'deploy', '--os=default',
                '--karg=root=UUID=root', '--karg=rootflags=subvol=root',
                '--karg-append=console=tty0', '--karg-append=console=ttyS0,115200',
                '--karg=rd.luks.uuid=luks-test', 'test')
            fstab = next((physical / 'ostree/deploy/default/deploy').glob('*/etc/fstab'))
            import gi
            gi.require_version('OSTree', '1.0')
            from gi.repository import Gio, OSTree
            sysroot = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
            sysroot.load(None)
            deployment = sysroot.get_deployments()[0]
            origin = deployment.get_origin()
            origin.set_string('origin', 'container-image-reference', 'ostree-unverified-registry:' + target)
            sysroot.write_origin_file(deployment, origin, None)
            if separate_boot:
                # Reproduce bootc's premature /boot finalization. Root has
                # already been reopened by PrepareBootcMountTargetsTask.
                run('mount', '-o', 'remount,ro', physical / 'boot')
                try:
                    finalizer.finalize(physical)
                except subprocess.CalledProcessError:
                    assert fstab.read_text() == original
                    print('PASS reproduced read-only boot failure; fstab retained', flush=True)
                else:
                    raise AssertionError('Expected the reported read-only /boot failure')
                run('mount', '-o', 'remount,rw', physical / 'boot')
            # With --skip-finalize the external installer retains writable
            # physical root/boot until its configuration and unmount finish.
            finalizer.finalize(physical, target)
            finalizer.finalize(physical, target)
            saved = OSTree.Sysroot.new(Gio.File.new_for_path(str(physical)))
            saved.load(None)
            assert saved.get_deployments()[0].get_origin().get_string(
                'origin', 'container-image-reference') == 'ostree-image-signed:docker://' + target
            assert fstab.with_name('fstab.gniri-before-rootflags').read_text() == original
            assert 'UUID=root / ' not in fstab.read_text()
            assert original.split('\n', 1)[1] in fstab.read_text()
            entries = list((physical / 'boot/loader/entries').glob('*.conf'))
            assert len(entries) == 1
            options = entries[0].read_text()
            for arg in ('rootflags=subvol=root,compress=zstd:1', 'root=UUID=root',
                        'console=tty0', 'console=ttyS0,115200', 'rd.luks.uuid=luks-test'):
                assert arg in options, options
            print(f'PASS real OSTree migration/readback/idempotency separate_boot={separate_boot}', flush=True)
        finally:
            if saved is not None:
                saved.unload()
            if sysroot is not None:
                sysroot.unload()
            # Sysroot keeps directory descriptors for its lifetime even after
            # unload(). Release the GI wrappers before unmounting the fixture.
            sysroot = saved = deployment = origin = None
            gc.collect()
            run('umount', '-R', physical)


if __name__ == '__main__':
    if not Path('/run/.containerenv').is_file() or os.geteuid() != 0:
        raise SystemExit('Run only inside the disposable installer container.')
    for separate in (True, False):
        check_layout(separate)
