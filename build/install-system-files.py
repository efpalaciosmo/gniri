#!/usr/bin/env python3
"""Install image defaults without importing the checkout's umask or ownership."""
from pathlib import Path
import shutil
import sys


def install_system_files(source, root):
    source, root = Path(source), Path(root)
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        destination = root / relative
        if path.is_symlink() or destination.is_symlink():
            raise ValueError(f'Refusing a symlink in the system overlay: {relative}')
        if path.is_dir():
            if not destination.exists():
                destination.mkdir()
                destination.chmod(0o755)
            # Shared RPM-owned directories keep the distribution's permissions.
        elif path.is_file():
            shutil.copyfile(path, destination)
            destination.chmod(0o755 if relative.parent == Path('usr/bin') else 0o644)
        else:
            raise ValueError(f'Unexpected system overlay entry: {relative}')


if __name__ == '__main__':
    install_system_files(sys.argv[1], Path('/'))
