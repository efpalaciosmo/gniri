from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'system_files'


class BootPathTests(unittest.TestCase):
    def test_fedora_boot_configuration_is_inherited_not_replaced(self):
        self.assertFalse((OVERLAY / 'usr/lib/ostree/prepare-root.conf').exists())
        self.assertFalse((OVERLAY / 'etc/ostree/prepare-root.conf').exists())
        self.assertFalse((OVERLAY / 'usr/lib/composefs/setup-root-conf.toml').exists())
        self.assertFalse(any(OVERLAY.rglob('*.efi')))

    def test_image_validation_guards_the_selected_backend(self):
        text = (ROOT / 'build/validate-image.sh').read_text()
        for required in ("config.get('composefs', 'enabled')", "config.getboolean('sysroot', 'readonly')",
                         "kernel['unified'] is False", 'bootupd shim-x64 grub2-efi-x64 kernel-core composefs'):
            self.assertIn(required, text)
        self.assertIn("assert not Path('/usr/lib/composefs/setup-root-conf.toml').exists()", text)

    def test_tmpfiles_directory_is_created_before_usr_becomes_readonly(self):
        configure = (ROOT / 'build/configure-image.py').read_text()
        installer = (ROOT / 'installer/prepare.sh').read_text()
        self.assertIn("Path('/usr/local/sbin').mkdir(mode=0o755, parents=True, exist_ok=True)", configure)
        self.assertIn('install -d -m 0755 /usr/local/sbin', installer)
        self.assertIn('[[ -d /usr/local/sbin ]]', (ROOT / 'build/validate-image.sh').read_text())
