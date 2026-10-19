#!/usr/bin/env python3
"""Checked installer-only fixes; Fedora 45 already includes the home fix."""
import ast
import hashlib
from pathlib import Path
from importlib.util import find_spec


# Backport the mount preservation/bind-mount parts of Anaconda dc4d94d279fe
# (PR #7220), retaining Fedora 44's mountpoint allowlist. Do not repartition,
# change /home, create accounts on login, or copy homes around at first boot.
CLEAN_OLD = '''        entries = list(os.listdir(self._physroot))
        for entry in entries:
            path = os.path.join(self._physroot, entry)
            # Try to unmount if it's a mount point, use lazy unmount for busy mounts
            if os.path.ismount(path):
                # Skip if /boot
                if path == self._physroot + "/boot":
                    log.debug("Bootc workaround: skip unmounting /boot")
                    continue
                safe_exec_program("umount", ["-l", path])

            safe_exec_program("rm", ["-rf", path])
'''
CLEAN_NEW = '''        # Preserve the storage module's mount points AND their ancestors.
        # In particular, never detach /home before creating the user's home.
        preserve = set()
        for mount_point in user_mount_points:
            while mount_point != "/":
                preserve.add(mount_point)
                mount_point = os.path.dirname(mount_point)

        entries = list(os.listdir(self._physroot))
        for entry in entries:
            path = os.path.join(self._physroot, entry)
            if "/" + entry in preserve:
                continue
            if os.path.ismount(path):
                safe_exec_program("umount", ["-l", path])
            safe_exec_program("rm", ["-rf", path])
'''
MOUNTS_OLD = '''        # Create /var subdirectories (roothome and home) after bind mount
        self._fill_var_subdirectories()
'''
MOUNTS_NEW = MOUNTS_OLD + '''
        # Mount the parent first even when only /boot/efi is a separate FS;
        # binding /boot later would hide the already-bound EFI mount.
        self._handle_boot_if_not_mount_point()

        # The bootc deployment is a different root from the physical target.
        # Bind /home (and /boot/efi) there before users and configuration tasks.
        for mount_point in sorted(mount_points, key=lambda p: p.count("/")):
            if mount_point in ("/", "/var", "/boot", "/dev", "/proc", "/run", "/sys"):
                continue
            self._setup_internal_bindmount(mount_point, recurse=False)
'''

# Reviewed Anaconda 45.29-1: retain its upstream mount-preserving cleanup,
# rather than reapplying Fedora 44's backport over the new implementation.
CLEANUP_45_SHA256 = 'cac074aab9aca33866a778bd642b242c1f29be394a340b7aeba6ac376a75b441'
BOOT_ORDER_OLD = '''        # Handle other user-specified mount points (e.g. /var/tmp, /home, etc.)
        self._handle_other_mount_points(mount_points)

        # Make sure /boot is accessible during %post scripts
        self._handle_boot_if_not_mount_point()
'''
BOOT_ORDER_NEW = '''        # The parent /boot bind must precede /boot/efi, even without a
        # separate /boot filesystem. Do not bind the parent a second time.
        self._handle_boot_if_not_mount_point()
        self._handle_other_mount_points({
            path: device for path, device in mount_points.items() if path != "/boot"
        })
'''


def replace_once(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise RuntimeError(f'{path}: Anaconda changed; review the installer fix')
    path.write_text(text.replace(old, new, 1))


def fix_edd(directory):
    # EDD describes legacy BIOS disk information. On native UEFI the kernel
    # correctly returns ENODEV; do not request this BIOS-only driver there.
    replace_once(directory / 'parse-anaconda-options.sh', 'modprobe -q edd\n',
                 'if [ ! -d /sys/firmware/efi ]; then\n    modprobe -q edd\nfi\n')
    replace_once(directory / 'anaconda-modprobe.sh',
                 '    MODULE_LIST+=" edd iscsi_ibft "\n',
                 '    MODULE_LIST+=" iscsi_ibft "\n'
                 '    if [ ! -d /sys/firmware/efi ]; then\n'
                 '        MODULE_LIST+=" edd "\n'
                 '    fi\n')


def fix_bootc_mounts(path):
    text = path.read_text()
    if CLEAN_OLD in text:
        replace_once(path, CLEAN_OLD, CLEAN_NEW)
        replace_once(path, MOUNTS_OLD, MOUNTS_NEW)
    else:
        tree = ast.parse(text)
        cls = next((node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == 'DeployBootcTask'), None)
        cleanup = next((node for node in cls.body
                        if isinstance(node, ast.FunctionDef) and node.name == '_clean_physroot'), None) if cls else None
        if cleanup is None:
            raise RuntimeError(f'{path}: Anaconda changed; missing bootc cleanup')
        if hashlib.sha256(ast.dump(cleanup).encode()).hexdigest() != CLEANUP_45_SHA256:
            raise RuntimeError(f'{path}: Anaconda changed; review mount preservation')
        replace_once(path, BOOT_ORDER_OLD, BOOT_ORDER_NEW)
    compile(path.read_text(), str(path), 'exec')


if __name__ == '__main__':
    fix_edd(Path('/usr/lib/dracut/modules.d/80anaconda'))
    fix_bootc_mounts(Path(find_spec('pyanaconda').origin).parent /
                    'modules/payloads/payload/rpm_ostree/installation.py')
