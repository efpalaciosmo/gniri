#!/usr/bin/env bash
set -euo pipefail
# Keep Fedora's OSTree + composefs boot path; a base refresh must not silently
# opt this image into composefs-native, custom UKIs or a different bootloader.
python3 - <<'PY'
import configparser
import json
from pathlib import Path
import subprocess

path = next((p for p in (Path('/etc/ostree/prepare-root.conf'),
                         Path('/usr/lib/ostree/prepare-root.conf')) if p.is_file()), None)
assert path is not None, 'OSTree prepare-root.conf is required'
config = configparser.ConfigParser()
config.read(path)
assert config.get('composefs', 'enabled').strip().lower() in {'yes', 'true', '1'}, 'Keep composefs enabled in OSTree mode'
assert config.getboolean('sysroot', 'readonly'), 'The physical sysroot must remain read-only'
for section in ('root', 'etc'):
    assert not config.getboolean(section, 'transient', fallback=False), 'Keep persistent machine state'
assert not Path('/usr/lib/composefs/setup-root-conf.toml').exists(), 'Native composefs is not the selected backend'
inspection = json.loads(subprocess.check_output(['bootc', 'container', 'inspect', '--json']))
assert not {'selinux=0', 'enforcing=0'}.intersection(inspection['kargs']), 'Do not weaken SELinux in the desktop payload'
kernel = inspection['kernel']
assert kernel and kernel['unified'] is False, 'Keep the stock kernel/initramfs boot path, not a custom UKI'
reference = Path('/usr/share/gniri/image-reference').read_text().strip()
if reference.startswith('ghcr.io/'):
    policy = json.loads(Path('/usr/share/gniri/bootc-policy.json').read_text())
    assert policy['default'] == [{'type': 'reject'}], 'bootc must not inherit an insecure policy default'
    repository = reference.rsplit(':', 1)[0]
    assert set(policy['transports']['docker']) == {repository}
    assert policy['transports']['docker'][repository] == [{
        'type': 'sigstoreSigned', 'keyPath': '/usr/share/gniri/keys/cosign.pub',
        'signedIdentity': {'type': 'matchRepository'},
    }]
    assert Path('/usr/share/gniri/keys/cosign.pub').stat().st_size > 0
PY
rpm -q bootupd shim-x64 grub2-efi-x64 kernel-core composefs
python3 /run/gniri-build/validate-hardware.py
python3 /run/gniri-build/validate-accounts.py
grep -qx 'SELINUX=enforcing' /etc/selinux/config
[[ -d /usr/local/sbin ]]
for package in firefox fedora-flathub-remote fedora-flatpak-remotes gnome-tour gnome-initial-setup; do
    if rpm -q "$package" >/dev/null 2>&1; then
        printf 'Unexpected package: %s\n' "$package" >&2
        exit 1
    fi
done
[[ -z $(flatpak remotes --system --columns=name) ]]
[[ -z $(flatpak list --system --columns=application) ]]
[[ $(readlink /etc/systemd/system/flatpak-add-fedora-repos.service) == /dev/null ]]
[[ -s /usr/share/gniri/flathub.flatpakrepo ]]
rpm -q polkit-kde kf6-kirigami kf6-qqc2-desktop-style qt6-qtbase-gui
[[ -x /usr/libexec/kf6/polkit-kde-authentication-agent-1 ]]
[[ -s /usr/lib64/qt6/plugins/platforms/libqwayland.so ]]
[[ -s /usr/lib64/qt6/qml/org/kde/kirigami/qmldir ]]
[[ -s /usr/lib64/qt6/qml/org/kde/desktop/qmldir ]]
[[ -f /usr/share/wayland-sessions/niri.desktop ]]
[[ -f /usr/share/wayland-sessions/gnome.desktop ]]
[[ -f /usr/share/xdg-desktop-portal/niri-portals.conf ]]
source /usr/lib/os-release
rpm -q "f${VERSION_ID}-backgrounds-base" "f${VERSION_ID}-backgrounds-gnome" gnome-backgrounds
[[ -s /usr/share/gnome-background-properties/f${VERSION_ID}.xml ]]
[[ -s /usr/share/backgrounds/f${VERSION_ID}/default/f${VERSION_ID}-01-day.jxl ]]
[[ -s /usr/share/backgrounds/f${VERSION_ID}/default/f${VERSION_ID}-01-night.jxl ]]
# Niri/Ghostty load EGL/GLES/GL at runtime: ldd on the main executable alone
# cannot prove these libraries are usable. Do not silently accept missing dlopen
# dependencies when installing without weak RPM dependencies.
python3 - <<'PY'
import ctypes
for library in ('libEGL.so.1', 'libGLESv2.so.2', 'libGL.so.1', 'libgbm.so.1'):
    ctypes.CDLL(library)
PY
ghostty +version
ghostty +validate-config --config-file=/dev/null
fc-match 'JetBrainsMono Nerd Font' --format '%{family}\n' | grep -F 'JetBrainsMono Nerd Font'
[[ -s /usr/share/licenses/gniri-nerd-fonts/OFL.txt ]]
niri validate --config /etc/niri/config.kdl
[[ ! -e /usr/share/gniri/defaults && ! -e /usr/bin/gniri-user-setup ]]
for command in distrobox fastfetch vi vim traceroute ghostty niri-session dbus-update-activation-environment fuzzel mako waybar swayidle swaylock nautilus wpctl playerctl; do
    command -v "$command"
done
for module in uinput wacom amdgpu; do
    found=false
    for kernel in /usr/lib/modules/*; do
        if modinfo -k "${kernel##*/}" "$module" >/dev/null 2>&1; then found=true; fi
    done
    "$found" || { printf 'Missing module: %s\n' "$module" >&2; exit 1; }
done
systemctl is-enabled gdm.service bootc-fetch-apply-updates.timer gniri-flatpak-system-repo.service
systemd-analyze --man=no verify /usr/lib/systemd/system/gniri-flatpak-system-repo.service
systemctl --global is-enabled gniri-flathub-user.service
install -d -m 0700 /run/gniri-build/verify-runtime
XDG_RUNTIME_DIR=/run/gniri-build/verify-runtime systemd-analyze --user --man=no verify \
    /usr/lib/systemd/user/gniri-flathub-user.service \
    /usr/lib/systemd/user/niri.service
[[ $(readlink /etc/systemd/system/default.target) == */graphical.target ]]
! grep -RE -- '--apply|systemctl (reboot|soft-reboot)' /usr/bin/gniri-stage-update
printf 'Image checks passed. Boot, Secure Boot and hardware tests are still required.\n'
