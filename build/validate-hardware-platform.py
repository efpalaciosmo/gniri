#!/usr/bin/env python3
"""Check shared hardware packages and kernel infrastructure, not device models."""
from pathlib import Path
import subprocess
import sys


def require_firmware(root, name):
    for suffix in ('', '.xz', '.zst'):
        path = root / 'usr/lib/firmware' / (name + suffix)
        if path.is_file() and path.stat().st_size:
            return
    raise AssertionError(f'Missing or empty platform firmware: {name}')


def validate_platform(packages_path, root=Path('/')):
    packages = [line.split('#', 1)[0].strip() for line in packages_path.read_text().splitlines()]
    packages = [name for name in packages if name]
    assert packages, 'Shared hardware package manifest is empty'
    subprocess.run(['rpm', '--root', str(root), '-q', *packages], check=True)
    kernels = sorted(path for path in (root / 'usr/lib/modules').iterdir()
                     if path.is_dir())
    assert kernels, 'No installed kernels to validate'
    for kernel in kernels:
        assert (kernel / 'vmlinuz').is_file(), f'{kernel.name}: missing kernel image'
        config = set((kernel / 'config').read_text().splitlines())
        for option in ('CONFIG_MICROCODE=y', 'CONFIG_FW_LOADER_COMPRESS_XZ=y',
                       'CONFIG_FW_LOADER_COMPRESS_ZSTD=y'):
            assert option in config, f'{kernel.name}: missing {option}'
    # Regulatory data is shared infrastructure; GPU/Wi-Fi firmware filenames and
    # module names change upstream and must not pin the distro to selected chips.
    for firmware in ('regulatory.db', 'regulatory.db.p7s'):
        require_firmware(root, firmware)
    print('Shared hardware packages, kernel infrastructure and regulatory data passed.')


if __name__ == '__main__':
    validate_platform(Path(sys.argv[1]))
