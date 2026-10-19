#!/usr/bin/env python3
"""Dependency-free source checks. Full image and hardware checks are separate."""
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
config = ROOT / 'system_files/etc/niri/config.kdl'
scripts = []
for tree in ('build', 'scripts', 'tests', 'installer', 'system_files'):
    for path in (ROOT / tree).rglob('*'):
        if not path.is_file() or path.suffix in ('.png', '.pyc'):
            continue
        text = path.read_text()
        if text.startswith('#!/usr/bin/env bash'):
            scripts.append(path)
            subprocess.run(['bash', '-n', str(path)], check=True)
        elif path.suffix == '.py' or text.startswith('#!/usr/bin/env python3'):
            ast.parse(text, filename=str(path))
for path in (ROOT / 'packages').glob('*.txt'):
    packages = [line.split('#')[0].strip() for line in path.read_text().splitlines()]
    packages = [line for line in packages if line]
    assert len(packages) == len(set(packages)), f'Duplicate packages in {path}'
    assert all(re.fullmatch(r'[A-Za-z0-9+_.-]+', name) for name in packages), path
    assert not any(name in {'firefox', 'fedora-flatpak-remotes', 'fedora-flathub-remote'} for name in packages)
json.loads((ROOT / 'renovate.json').read_text())
assert not re.search('[áéíóúñ¿¡]', config.read_text(), re.I), 'Niri defaults must be in English'
if shutil.which('niri'):
    subprocess.run(['niri', 'validate', '--config', str(config)], check=True)
else:
    print('niri not installed locally; the image build validates its configuration.')
if shutil.which('shellcheck'):
    subprocess.run(['shellcheck', '-x', '-S', 'warning', *map(str, scripts)], check=True)
else:
    print('shellcheck not installed locally; Bash syntax has been checked.')
print(f'Static checks passed ({len(scripts)} Bash scripts).')
