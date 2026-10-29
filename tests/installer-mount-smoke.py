#!/usr/bin/env python3
"""Exercise the real patched Anaconda tasks on disposable tmpfs mounts only.

Run with sudo make check-installer: --network=none --cap-add SYS_ADMIN and
--security-opt apparmor=unconfined allow disposable mounts on Ubuntu runners.
No disk, host filesystem mount, account database or partitioner is used.
"""
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
from types import SimpleNamespace


def mount(*arguments):
    subprocess.run(['mount', *map(str, arguments)], check=True)


def check_layout(home_mount, var_mount, separate_boot):
    from pyanaconda.modules.common.structures.bootc import BootcConfigurationData
    from pyanaconda.modules.payloads.payload.rpm_ostree import installation

    with tempfile.TemporaryDirectory(prefix='gniri-mount-test-', dir='/var/tmp', delete=False) as temporary:
        base = Path(temporary)
        physical, deployment = base / 'physical', base / 'deployment'
        try:
            for root in (physical, deployment):
                root.mkdir()
                mount('-t', 'tmpfs', f'gniri-{root.name}', root)

            points = {'/': 'root', '/boot/efi': 'efi'}
            if separate_boot:
                points['/boot'] = 'boot'
            if home_mount:
                points['/home'] = 'home'
            if var_mount:
                points['/var'] = 'var'
            for point in sorted(set(points) - {'/'}, key=lambda p: p.count('/')):
                target = physical / point.lstrip('/')
                target.mkdir(parents=True, exist_ok=True)
                mount('-t', 'tmpfs', f'gniri-{points[point]}', target)
            scratch = physical / 'root'
            scratch.mkdir()
            (scratch / 'installer-only').touch()

            device_tree = SimpleNamespace(GetMountPoints=lambda: points)
            original_storage = installation.STORAGE
            installation.STORAGE = SimpleNamespace(get_proxy=lambda *_: device_tree)
            try:
                data = BootcConfigurationData()
                data.stateroot = 'default'
                deploy = installation.DeployBootcTask(data, str(physical), str(deployment))
                deploy._clean_physroot()
                assert not scratch.exists(), 'Installer scratch state was not cleaned'
                for point in set(points) - {'/'}:
                    assert os.path.ismount(physical / point.lstrip('/')), point

                # Model bootc's deployment roots, not a different partition layout.
                backing_var = physical / 'ostree/deploy/default/var'
                backing_var.mkdir(parents=True)
                for name in ('var', 'proc', 'sys', 'boot'):
                    (deployment / name).mkdir()
                (deployment / 'home').symlink_to('var/home')
                prepare = installation.PrepareBootcMountTargetsTask(
                    str(deployment), str(physical), data)
                prepare.run()
                assert os.path.samefile(deployment / 'boot/efi', physical / 'boot/efi')

                home = deployment / 'home/installer-test'
                home.mkdir(mode=0o700)
                os.chown(home, 1000, 1000)
                (home / 'probe').write_text('persistent home\n')
                expected = physical / 'home' if home_mount else (
                    physical / 'var/home' if var_mount else backing_var / 'home')
                assert (expected / 'installer-test/probe').read_text() == 'persistent home\n'
                assert home.stat().st_uid == 1000
                assert os.path.samefile(home, deployment / 'var/home/installer-test')
                print(f'PASS home_mount={home_mount} var_mount={var_mount} separate_boot={separate_boot}')
            finally:
                installation.STORAGE = original_storage
        finally:
            # Unmount ONLY this test's tmpfs trees/binds before TemporaryDirectory
            # removes the empty mountpoint directories. Never traverse a live mount.
            targets = [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()
                       if line.split()[4].startswith(str(base) + '/')]
            for target in sorted(targets, key=len, reverse=True):
                subprocess.run(['umount', target], check=True)
            shutil.rmtree(base)


if __name__ == '__main__':
    if not Path('/run/.containerenv').is_file():
        raise SystemExit('Run only inside the disposable installer container.')
    for layout in ((True, False, True), (False, False, True),
                   (True, True, True), (True, False, False)):
        check_layout(*layout)
