#!/usr/bin/env python3
"""Check functional hardware dependencies without accessing the host's devices."""
import ctypes
import configparser
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

def require_file(path):
    assert Path(path).is_file(), f'Missing hardware integration file: {path}'


for command in ('aplay', 'arecord', 'alsamixer', 'pw-cli', 'pw-dump', 'pw-top',
                'pactl', 'nmcli', 'nmtui', 'iw', 'bluetoothctl', 'btmon',
                'tuned-adm', 'zramctl', 'brightnessctl', 'openvpn', 'glxinfo',
                'eglinfo', 'vulkaninfo', 'vainfo', 'amd-smi', 'nvtop', 'sensors',
                'cam', 'ideviceinfo', 'ratbagd', 'pamu2fcfg'):
    assert shutil.which(command), f'Missing hardware/diagnostic command: {command}'

# Virtualization applications are user-installed, not part of the host image.
assert not subprocess.check_output(['rpm', '-qa', '--qf', '%{NAME}\n',
                                   'qemu*', 'libvirt*', 'virt-manager', 'virt-install',
                                   'virt-viewer', 'swtpm*', 'edk2-*'], text=True).strip(), \
    'Unexpected host virtualization packages'

require_file('/usr/share/alsa/ucm2/ucm.conf')
# Check libraries and dynamic drivers without requiring a display or GPU.
for library in ('libva.so.2', 'libOpenCL.so.1', 'libheif.so.1', 'libopenh264.so.8'):
    ctypes.CDLL(library)
for driver in ('radeonsi_drv_video.so', 'iHD_drv_video.so'):
    require_file('/usr/lib64/dri/' + driver)
assert any(Path('/etc/OpenCL/vendors').glob('*.icd')), 'OpenCL ICD is required'
subprocess.run(['python3', '-c', 'import amdsmi'], check=True)
for module in ('pam_u2f.so', 'pam_yubico.so'):
    ctypes.CDLL('/usr/lib64/security/' + module)
assert any(Path('/usr/lib/firmware').rglob('sof-*.ri*')), 'SOF firmware is required'
assert any(Path('/usr/lib/firmware').glob('iwlwifi-*.ucode*')), 'Intel Wi-Fi firmware is required'
for firmware in ('rtw89/rtw8852c_fw-2.bin', 'rtl_bt/rtl8852cu_fw.bin'):
    assert any(Path('/usr/lib/firmware', firmware + suffix).is_file()
               for suffix in ('', '.xz', '.zst')), f'Missing firmware: {firmware}'

# These plugins are loaded dynamically; an installed main executable is not enough.
for plugin in ('alsa/libspa-alsa.so', 'bluez5/libspa-bluez5.so'):
    ctypes.CDLL('/usr/lib64/spa-0.2/' + plugin)
for codec in ('sbc', 'aac', 'ldac', 'lc3', 'hfp-msbc'):
    require_file(f'/usr/lib64/spa-0.2/bluez5/libspa-codec-bluez5-{codec}.so')

# Verify both NetworkManager's backend and the GTK editor can actually be loaded.
require_file('/usr/lib/NetworkManager/VPN/nm-openvpn-service.name')
for library in ('libnm-vpn-plugin-openvpn.so', 'libnm-vpn-plugin-openvpn-editor.so'):
    ctypes.CDLL('/usr/lib64/NetworkManager/' + library)
subprocess.run(['systemctl', 'is-enabled', 'tuned.service', 'tuned-ppd.service',
                'NetworkManager.service', 'bluetooth.service'], check=True)

for kernel in Path('/usr/lib/modules').iterdir():
    if not kernel.is_dir():
        continue
    for module in ('rtw89_8852ce', 'iwlwifi', 'btusb', 'btrtl', 'snd_hda_intel',
                   'snd_usb_audio', 'snd_sof', 'zram'):
        subprocess.run(['modinfo', '-k', kernel.name, module], check=True,
                       stdout=subprocess.DEVNULL)
    assert 'CONFIG_ZRAM_BACKEND_ZSTD=y' in (kernel / 'config').read_text()

# Exercise the packaged generator with its real config parser and fake RAM sizes.
# Test mode never loads modules or writes to /sys, even inside a container.
with tempfile.TemporaryDirectory(prefix='gniri-zram-') as temporary:
    root = Path(temporary)
    (root / 'proc').mkdir()
    (root / 'proc/cmdline').write_text('')
    config = root / 'usr/lib/systemd'
    config.mkdir(parents=True)
    shutil.copy('/usr/lib/systemd/zram-generator.conf', config)
    shutil.copytree('/usr/lib/systemd/zram-generator.conf.d', config / 'zram-generator.conf.d')
    effective = configparser.ConfigParser()
    effective.read([config / 'zram-generator.conf',
                    *sorted((config / 'zram-generator.conf.d').glob('*.conf'))])
    assert effective['zram0']['compression-algorithm'] == 'zstd(level=1)'
    assert 'writeback-device' not in effective['zram0']
    for ram_mib in (2048, 32768):
        (root / 'proc/meminfo').write_text(f'MemTotal: {ram_mib * 1024} kB\n')
        output = root / f'generated-{ram_mib}'
        output.mkdir()
        result = subprocess.run(['/usr/lib/systemd/system-generators/zram-generator', str(output)],
                                env={**os.environ, 'ZRAM_GENERATOR_ROOT': str(root),
                                     'SYSTEMD_LOG_LEVEL': 'debug'}, check=True,
                                capture_output=True, text=True)
        assert (output / 'dev-zram0.swap').is_file(), result.stderr
        assert 'Priority=100' in (output / 'dev-zram0.swap').read_text()
        assert (output / 'swap.target.wants/dev-zram0.swap').is_file()
        print(f'Zram generator: valid Fedora defaults + Zstandard level 1 with {ram_mib} MiB RAM')

print('Graphics, peripherals, audio, network, energy and zram dependencies passed.')
