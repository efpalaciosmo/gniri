from pathlib import Path
import runpy
import subprocess
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = runpy.run_path(str(ROOT / 'build/validate-hardware-platform.py'))


class HardwarePackageTests(unittest.TestCase):
    def test_requested_host_packages_are_explicit(self):
        packages = set()
        for path in (ROOT / 'packages').glob('*.txt'):
            packages.update(line.split('#')[0].strip() for line in path.read_text().splitlines())
        for package in ('amdsmi', 'glx-utils', 'egl-utils', 'vulkan-tools', 'libva-utils',
                        'intel-gmmlib', 'intel-mediasdk', 'intel-vpl-gpu-rt', 'libheif',
                        'libva', 'libva-intel-media-driver', 'mesa-dri-drivers', 'mesa-filesystem',
                        'mesa-libEGL', 'mesa-libGL', 'mesa-libgbm', 'mesa-libOpenCL',
                        'mesa-vulkan-drivers', 'openh264', 'nvtop', 'openrgb-udev-rules',
                        'pam-u2f', 'pam_yubico', 'pamu2fcfg', 'libcamera-gstreamer',
                        'libcamera-tools', 'libimobiledevice-utils', 'libratbag-ratbagd',
                        'libxcrypt-compat', 'lm_sensors', 'solaar-udev', 'traceroute', 'vim-enhanced'):
            self.assertIn(package, packages)
        self.assertNotIn('ffmpeg', packages)

    def test_pam_policy_is_not_changed_by_security_key_tools(self):
        overlay = ROOT / 'system_files'
        self.assertFalse((overlay / 'etc/pam.d').exists())
        self.assertFalse((overlay / 'etc/authselect').exists())

    def test_host_virtualization_stack_is_not_bundled(self):
        for path in (ROOT / 'packages').glob('*.txt'):
            packages = [line.split('#')[0].strip() for line in path.read_text().splitlines()]
            for package in packages:
                if package == 'qemu-guest-agent':
                    continue
                self.assertFalse(package.startswith(('qemu', 'libvirt', 'swtpm', 'edk2-')),
                                 f'{path}: {package}')
                self.assertNotIn(package, ('virt-manager', 'virt-install', 'virt-viewer', 'virglrenderer'))
        overlay = ROOT / 'system_files'
        self.assertFalse((overlay / 'usr/bin/gniri-setup-virtualization').exists())
        self.assertFalse((overlay / 'etc/polkit-1/rules.d/00-gniri-libvirt.rules').exists())
        self.assertNotIn('virt-manager.desktop', (ROOT / 'packages/visible-applications.allow').read_text())
        preset = (overlay / 'usr/lib/systemd/system-preset/00-gniri.preset').read_text()
        self.assertNotIn('virt', preset)
        installation = (ROOT / 'build/install-packages.sh').read_text()
        validation = (ROOT / 'build/validate-hardware.py').read_text()
        for pattern in ("'qemu*'", "'libvirt*'", "'virt-manager'", "'swtpm*'", "'edk2-*'"):
            self.assertIn(pattern, installation)
            self.assertIn(pattern, validation)

    def test_vm_guest_integration_is_explicit_and_validated(self):
        packages = (ROOT / 'packages/hardware.txt').read_text().splitlines()
        for package in ('qemu-guest-agent', 'spice-vdagent'):
            self.assertIn(package, packages)
        preset = (ROOT / 'system_files/usr/lib/systemd/system-preset/00-gniri.preset').read_text()
        self.assertIn('enable qemu-guest-agent.service', preset)
        # SPICE's static socket is started by Fedora's udev rule, not a boot preset.
        self.assertNotIn('enable spice-vdagentd', preset)
        validation = (ROOT / 'build/validate-hardware.py').read_text()
        for dependency in ('qemu-ga', 'spice-vdagentd',
                           '/usr/lib/udev/rules.d/99-qemu-guest-agent.rules',
                           '/usr/lib/udev/rules.d/70-spice-vdagentd.rules',
                           '/usr/lib/systemd/user/graphical-session.target.wants/spice-vdagent.service'):
            self.assertIn(dependency, validation)
        self.assertIn("virtualization_packages - {'qemu-guest-agent'}", validation)
        for module in ('virtio_gpu', 'virtio_console'):
            self.assertIn(module, validation)

    def test_host_package_cleanup_preserves_only_the_qemu_guest_agent(self):
        installation = (ROOT / 'build/install-packages.sh').read_text()
        cleanup = installation.split('mapfile -t virtualization_packages', 1)[1].split(
            '# Tailscale', 1)[0]
        cleanup = 'mapfile -t virtualization_packages' + cleanup
        for installed, removed in (
                ('qemu-guest-agent\n', []),
                ('qemu-guest-agent\nqemu-system-x86-core\nqemu-user-static\nlibvirt-daemon\nqemu-guest-agent-extra\n',
                 ['qemu-system-x86-core', 'qemu-user-static', 'libvirt-daemon', 'qemu-guest-agent-extra']),
                ('', [])):
            with self.subTest(installed=installed):
                script = '''set -euo pipefail
rpm() { cat; }
remove_packages() { printf '%s\\n' "$@"; }
dnf=(remove_packages)
'''
                # Supply a fake RPM inventory without touching the host's packages.
                result = subprocess.run(['bash', '-c', script + cleanup], check=True,
                                        input=installed, capture_output=True, text=True)
                expected = ['--setopt=clean_requirements_on_remove=False', 'remove', *removed] if removed else []
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_build_uses_stock_modules_without_signing_secrets(self):
        text = (ROOT / 'Containerfile').read_text()
        self.assertEqual(sum(line.startswith('FROM ') for line in text.splitlines()), 1)
        self.assertNotIn('type=secret', text)
        self.assertIn('podman build ', (ROOT / 'Makefile').read_text())
        self.assertFalse((ROOT / 'system_files/usr/lib/modprobe.d/gniri-xone.conf').exists())


class HardwarePlatformTests(unittest.TestCase):
    def test_storage_diagnostics_and_periodic_trim_are_explicit(self):
        packages = (ROOT / 'packages/hardware.txt').read_text().splitlines()
        for package in ('pciutils', 'usbutils', 'nvme-cli', 'smartmontools', 'ethtool', 'iw', 'util-linux'):
            self.assertIn(package, packages)
        self.assertIn('enable fstrim.timer',
                      (ROOT / 'system_files/usr/lib/systemd/system-preset/00-gniri.preset').read_text())
        validation = (ROOT / 'build/validate-hardware.py').read_text()
        for command in ('lspci', 'lsusb', 'nvme', 'smartctl', 'ethtool', 'fwupdmgr', 'fstrim'):
            self.assertIn(f"'{command}'", validation)
        self.assertIn("'fstrim.timer'", validation)

    def test_installer_and_desktop_share_platform_packages_and_checks(self):
        desktop = (ROOT / 'Containerfile').read_text()
        installer = (ROOT / 'installer/Containerfile').read_text()
        prepare = (ROOT / 'installer/prepare.sh').read_text()
        self.assertIn('packages/*.txt', desktop)
        self.assertIn('COPY packages/hardware-platform.txt', installer)
        self.assertIn('COPY build/validate-hardware-platform.py', installer)
        self.assertIn('"${platform_packages[@]}"', prepare)
        self.assertLess(prepare.index('python3 /run/gniri-validate-hardware-platform.py'),
                        prepare.index('DRACUT_NO_XATTR=1'))
        self.assertIn("with_name('validate-hardware-platform.py')",
                      (ROOT / 'build/validate-hardware.py').read_text())
        packages = (ROOT / 'packages/hardware-platform.txt').read_text().splitlines()
        for package in ('amd-ucode-firmware', 'amd-gpu-firmware', 'realtek-firmware',
                        'alsa-sof-firmware', 'atheros-firmware', 'brcmfmac-firmware',
                        'cirrus-audio-firmware', 'intel-audio-firmware', 'intel-gpu-firmware',
                        'intel-vsc-firmware', 'iwlbluetooth-firmware', 'iwlwifi-mld-firmware',
                        'iwlwifi-mvm-firmware', 'linux-firmware', 'microcode_ctl',
                        'mt7xxx-firmware', 'mediatek-firmware', 'nvidia-gpu-firmware',
                        'nxpwireless-firmware', 'qcom-wwan-firmware', 'tiwilink-firmware',
                        'kernel-core', 'kernel-modules', 'kernel-modules-extra',
                        'NetworkManager', 'NetworkManager-wifi', 'wireless-regdb',
                        'mesa-dri-drivers', 'mesa-vulkan-drivers'):
            self.assertIn(package, packages)

    def test_firmware_accepts_compression_and_rejects_missing_or_empty_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            firmware = 'regulatory.db'
            path = root / 'usr/lib/firmware' / firmware
            path.parent.mkdir(parents=True)
            for suffix in ('', '.xz', '.zst'):
                compressed = path.with_name(path.name + suffix)
                with self.assertRaisesRegex(AssertionError, firmware):
                    PLATFORM['require_firmware'](root, firmware)
                compressed.touch()
                with self.assertRaisesRegex(AssertionError, firmware):
                    PLATFORM['require_firmware'](root, firmware)
                compressed.write_bytes(b'firmware')
                PLATFORM['require_firmware'](root, firmware)
                compressed.unlink()

    def test_no_installed_kernel_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'usr/lib/modules').mkdir(parents=True)
            manifest = root / 'packages.txt'
            manifest.write_text('kernel-core\nlinux-firmware\n')
            with patch('subprocess.run'), self.assertRaisesRegex(AssertionError, 'No installed kernels'):
                PLATFORM['validate_platform'](manifest, root)

    def test_empty_package_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'packages.txt'
            manifest.write_text('# No packages\n\n')
            with patch('subprocess.run') as run, \
                    self.assertRaisesRegex(AssertionError, 'manifest is empty'):
                PLATFORM['validate_platform'](manifest, Path(temporary))
            run.assert_not_called()

    def test_missing_installed_packages_fail_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / 'packages.txt'
            manifest.write_text('NetworkManager-wifi\nrealtek-firmware\nmt7xxx-firmware\n')
            with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'rpm')), \
                    self.assertRaises(subprocess.CalledProcessError):
                PLATFORM['validate_platform'](manifest, Path(temporary))

    def test_every_installed_kernel_is_checked_without_device_specific_requirements(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / 'packages.txt'
            manifest.write_text('# Shared packages\nlinux-firmware # all vendors\nNetworkManager-wifi\n\n')
            for version in ('first', 'second'):
                kernel = root / 'usr/lib/modules' / version
                kernel.mkdir(parents=True)
                (kernel / 'vmlinuz').write_bytes(b'kernel')
                (kernel / 'config').write_text('CONFIG_MICROCODE=y\n'
                    'CONFIG_FW_LOADER_COMPRESS_XZ=y\nCONFIG_FW_LOADER_COMPRESS_ZSTD=y\n')
            for name in ('regulatory.db', 'regulatory.db.p7s'):
                path = root / 'usr/lib/firmware' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'firmware')
            # No PCI/USB aliases, vendor blobs, named chip modules or AMD-only
            # power options are needed in this valid, hardware-neutral fixture.
            with patch('subprocess.run') as run:
                PLATFORM['validate_platform'](manifest, root)
            run.assert_called_once_with(['rpm', '--root', str(root), '-q',
                                         'linux-firmware', 'NetworkManager-wifi'], check=True)
            (root / 'usr/lib/modules/second/config').write_text('CONFIG_MICROCODE=y\n')
            with patch('subprocess.run'), self.assertRaisesRegex(AssertionError, 'COMPRESS_XZ'):
                PLATFORM['validate_platform'](manifest, root)
