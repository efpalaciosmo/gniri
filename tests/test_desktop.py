from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'system_files'
NIRI = OVERLAY / 'etc/niri/config.kdl'


class DesktopTests(unittest.TestCase):
    def test_only_one_niri_config_is_shipped(self):
        self.assertEqual(list(OVERLAY.rglob('*.kdl')), [NIRI])
        self.assertLess(len(NIRI.read_text().splitlines()), 100)
        self.assertNotIn('include ', NIRI.read_text())

    def test_ghostty_launcher_and_basic_bindings(self):
        text = NIRI.read_text()
        for key, action in (('Mod+Return', 'spawn "ghostty"'), ('Mod+D', 'spawn "fuzzel"'),
                            ('Mod+Q', 'close-window'), ('Mod+Shift+E', 'quit')):
            self.assertRegex(text, re.escape(key) + r'[^\n]+\{ ' + re.escape(action))

    def test_no_personal_themes_or_first_login_copying(self):
        self.assertFalse(any((OVERLAY / 'usr/share/gniri/defaults').rglob('*')))
        for path in ('usr/bin/gniri-user-setup', 'usr/lib/systemd/user/gniri-user-setup.service',
                     'usr/share/glib-2.0/schemas/90-gniri.gschema.override'):
            self.assertFalse((OVERLAY / path).exists(), path)
        self.assertFalse((ROOT / 'scripts/import-dotfiles.py').exists())
        text = NIRI.read_text()
        self.assertNotIn('scripts/', text)
        self.assertNotIn('font', text)
        self.assertNotIn('backgrounds/', text)

    def test_session_tools_use_package_defaults(self):
        text = NIRI.read_text()
        self.assertIn('spawn-at-startup "waybar"', text)
        self.assertIn('spawn-at-startup "mako"', text)
        for app in ('waybar', 'mako', 'ghostty', 'fuzzel', 'swaylock', 'zathura'):
            self.assertFalse((OVERLAY / 'etc/xdg' / app).exists())

    def test_modern_polkit_agent_and_runtime_dependencies(self):
        agent = '/usr/libexec/kf6/polkit-kde-authentication-agent-1'
        config = NIRI.read_text()
        self.assertIn(f'spawn-at-startup "{agent}"', config)
        self.assertNotIn('lxpolkit', config)
        packages = (ROOT / 'packages/niri.txt').read_text().splitlines()
        self.assertNotIn('lxpolkit', packages)
        validation = (ROOT / 'build/validate-image.sh').read_text()
        for package in ('polkit-kde', 'kf6-kirigami', 'kf6-qqc2-desktop-style',
                        'qt6-qtbase-gui'):
            self.assertIn(package, packages)
            self.assertIn(package, validation)
        self.assertIn(f'[[ -x {agent} ]]', validation)
        self.assertIn('[[ -s /usr/lib64/qt6/plugins/platforms/libqwayland.so ]]', validation)
        for module in ('org/kde/kirigami', 'org/kde/desktop'):
            self.assertIn(f'[[ -s /usr/lib64/qt6/qml/{module}/qmldir ]]', validation)

    def test_screen_lock_is_not_removed_with_the_dotfiles(self):
        text = NIRI.read_text()
        self.assertIn('"before-sleep" "swaylock -f"', text)
        self.assertIn('"timeout" "300" "swaylock -f"', text)
        self.assertIn('"resume" "niri msg action power-on-monitors"', text)

    def test_flathub_remains_user_only_and_asynchronous(self):
        text = (OVERLAY / 'usr/lib/systemd/user/gniri-flathub-user.service').read_text()
        self.assertIn('ExecStart=/usr/bin/gniri-flathub-user', text)
        self.assertNotIn('flatpak install', text)
        self.assertIn('DefaultDependencies=no', text)
        self.assertIn('After=graphical-session.target', text)
        helper = (OVERLAY / 'usr/bin/gniri-flathub-user').read_text()
        self.assertIn('/usr/share/gniri/flathub.flatpakrepo', helper)
        self.assertNotIn('https://flathub.org/repo/flathub.flatpakrepo', text)
        presets = (OVERLAY / 'usr/lib/systemd/user-preset/00-gniri.preset').read_text()
        self.assertIn('enable gniri-flathub-user.service', presets)
        self.assertNotIn('gniri-user-setup', presets)

    def test_fastfetch_and_both_vim_commands(self):
        packages = (ROOT / 'packages/core.txt').read_text().splitlines()
        self.assertIn('fastfetch', packages)
        self.assertIn('vim-minimal', packages)
        self.assertIn('vim-enhanced', packages)

    def test_distrobox_is_explicit_and_checked(self):
        self.assertIn('distrobox', (ROOT / 'packages/core.txt').read_text().splitlines())
        self.assertIn('for command in distrobox ', (ROOT / 'build/validate-image.sh').read_text())

    def test_fedora_first_boot_flatpak_provisioner_is_blocked(self):
        preset = (OVERLAY / 'usr/lib/systemd/system-preset/00-gniri.preset').read_text()
        self.assertIn('disable flatpak-add-fedora-repos.service', preset)
        configure = (ROOT / 'build/configure-image.py').read_text()
        self.assertIn("['systemctl', 'mask', 'flatpak-add-fedora-repos.service']", configure)
        validation = (ROOT / 'build/validate-image.sh').read_text()
        self.assertIn('readlink /etc/systemd/system/flatpak-add-fedora-repos.service', validation)

    def test_official_flathub_descriptor_is_checksum_verified(self):
        script = (ROOT / 'build/install-upstream.sh').read_text()
        self.assertIn('https://flathub.org/repo/flathub.flatpakrepo', script)
        self.assertIn('"$FLATHUB_REPO_SHA256"', script)
        self.assertIn('/usr/share/gniri/flathub.flatpakrepo', script)

    def test_system_flatpak_repo_is_initialized_after_tmpfiles_before_login(self):
        self.assertIn('ostree', (ROOT / 'packages/core.txt').read_text().splitlines())
        unit = (OVERLAY / 'usr/lib/systemd/system/gniri-flatpak-system-repo.service').read_text()
        self.assertIn('After=systemd-tmpfiles-setup.service', unit)
        self.assertIn('Before=gdm.service flatpak-system-helper.service', unit)
        self.assertIn('RequiresMountsFor=/var/lib/flatpak', unit)
        self.assertIn('StateDirectory=flatpak', unit)
        self.assertIn('ExecStart=/usr/bin/ostree --repo=/var/lib/flatpak/repo init --mode=bare-user-only', unit)
        self.assertNotIn('remote-add', unit)
        self.assertNotIn('rm ', unit)
        preset = (OVERLAY / 'usr/lib/systemd/system-preset/00-gniri.preset').read_text()
        self.assertIn('enable gniri-flatpak-system-repo.service', preset)
        smoke = (ROOT / 'tests/flatpak-smoke.sh').read_text()
        self.assertIn('systemd-tmpfiles --create --prefix=/var/lib/flatpak', smoke)
        self.assertIn('opendir(objects)', smoke)
        self.assertIn('as_user flatpak list --columns=application', smoke)

    def test_fedora_backgrounds_and_session_helper_are_explicit(self):
        packages = (ROOT / 'packages/desktop.txt').read_text().splitlines()
        for package in ('gnome-backgrounds', 'dbus-tools'):
            self.assertIn(package, packages)
        installation = (ROOT / 'build/install-packages.sh').read_text()
        self.assertIn('f${VERSION_ID}-backgrounds-gnome', installation)
        validation = (ROOT / 'build/validate-image.sh').read_text()
        self.assertIn('/usr/share/gnome-background-properties/f${VERSION_ID}.xml', validation)
        self.assertIn('dbus-update-activation-environment', validation)

    def test_graphics_libraries_are_checked_beyond_executable_presence(self):
        validation = (ROOT / 'build/validate-image.sh').read_text()
        for library in ('libEGL.so.1', 'libGLESv2.so.2', 'libGL.so.1', 'libgbm.so.1'):
            self.assertIn(library, validation)
        self.assertIn('ctypes.CDLL(library)', validation)
        self.assertIn('ghostty +validate-config', validation)

    @unittest.skipUnless(shutil.which('niri'), 'Validated again inside the image build')
    def test_config_parses_with_niri(self):
        subprocess.run(['niri', 'validate', '--config', str(NIRI)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
