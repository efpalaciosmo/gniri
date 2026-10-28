#!/usr/bin/env python3
"""Keep kernel development metadata out of bootc's runtime-populated /boot."""
from pathlib import Path


def normalize_boot(root=Path('/')):
    for source in (root / 'boot').glob('symvers-*.xz'):
        version = source.name.removeprefix('symvers-').removesuffix('.xz')
        modules = root / 'usr/lib/modules' / version
        if not modules.is_dir() or source.is_symlink():
            raise ValueError(f'Unexpected kernel symbol metadata: {source}')
        destination = modules / 'symvers.xz'
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise ValueError(f'Conflicting kernel symbol metadata: {destination}')
            source.unlink()
        else:
            source.rename(destination)


if __name__ == '__main__':
    normalize_boot()
