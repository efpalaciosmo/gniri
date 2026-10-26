from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


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

    def test_build_uses_stock_modules_without_signing_secrets(self):
        text = (ROOT / 'Containerfile').read_text()
        self.assertEqual(sum(line.startswith('FROM ') for line in text.splitlines()), 1)
        self.assertNotIn('type=secret', text)
        self.assertIn('podman build ', (ROOT / 'Makefile').read_text())
        self.assertFalse((ROOT / 'system_files/usr/lib/modprobe.d/gniri-xone.conf').exists())
