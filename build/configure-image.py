#!/usr/bin/env python3
"""Image-owned configuration; no account creation or runtime Flatpak installs."""
import configparser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import runpy

signature_policies = runpy.run_path('/run/gniri-build/signature-policy.py')['signature_policies']

reference = sys.argv[1]
if not re.fullmatch(r'(localhost/gniri:development|ghcr\.io/[a-z0-9._/-]+:[a-z0-9._-]+)', reference):
    raise SystemExit('Use localhost/gniri:development or a lower-case tagged GHCR image reference.')
share = Path('/usr/share/gniri')
share.mkdir(exist_ok=True)
# rpm-ostree's inherited tmpfiles rules expect this directory. Materialize it
# while /usr is writable, rather than trying to create it at boot on composefs.
Path('/usr/local/sbin').mkdir(mode=0o755, parents=True, exist_ok=True)
(share / 'image-reference').write_text(reference + '\n')
if reference.startswith('ghcr.io/'):
    public_key = Path('/run/gniri-build/trust/cosign.pub')
    if not public_key.is_file():
        raise SystemExit('Publishing requires trust/cosign.pub; see docs/building.md.')
    (share / 'keys').mkdir(exist_ok=True)
    shutil.copyfile(public_key, share / 'keys/cosign.pub')
    repository = reference.rsplit(':', 1)[0]
    policy_path = Path('/etc/containers/policy.json')
    # Fedora ships its default under /usr/share; preserve any /etc override.
    policy_source = policy_path if policy_path.exists() else Path('/usr/share/containers/policy.json')
    policy = json.loads(policy_source.read_text())
    policy, bootc_policy = signature_policies(policy, repository)
    policy_path.write_text(json.dumps(policy, indent=2) + '\n')
    (share / 'bootc-policy.json').write_text(json.dumps(bootc_policy, indent=2) + '\n')
    # rpm-ostree uses a daemon, so a caller's shell environment does not select
    # its policy. Keep its signed-origin operations on the same strict policy
    # as bootc, without changing general-purpose Podman/Distrobox defaults.
    dropin = Path('/usr/lib/systemd/system/rpm-ostreed.service.d')
    dropin.mkdir(mode=0o755, parents=True, exist_ok=True)
    (dropin / '10-gniri-policy.conf').write_text(
        '[Service]\nEnvironment=CONTAINERS_POLICY_JSON=/usr/share/gniri/bootc-policy.json\n')
    registries = Path('/etc/containers/registries.d')
    registries.mkdir(parents=True, exist_ok=True)
    (registries / 'gniri.yaml').write_text(f'docker:\n  {repository}:\n    use-sigstore-attachments: true\n')

# Preserve ID=fedora / VERSION_ID for package and application compatibility.
release = Path('/usr/lib/os-release')
text = release.read_text()
version = re.search(r'^VERSION_ID=(.+)$', text, flags=re.MULTILINE).group(1).strip('"')
if not version.isdecimal() or not re.search(r'^RELEASE_TYPE=["\']?stable["\']?$', text, re.MULTILINE):
    raise SystemExit('The stable channel must contain a numbered, released Fedora base, not Rawhide.')
if len(sys.argv) < 5 or version != sys.argv[4]:
    raise SystemExit('Fedora version differs from the resolved build input; use scripts/build-image.py.')
text = re.sub(r'^PRETTY_NAME=.*$', f'PRETTY_NAME="Gniri (Fedora {version})"', text, flags=re.MULTILINE)
for key, value in (('VARIANT', '"Gniri"'), ('VARIANT_ID', 'gniri'), ('IMAGE_ID', 'gniri')):
    text = re.sub(rf'^{key}=.*\n?', '', text, flags=re.MULTILINE)
    text += f'\n{key}={value}\n'
release.write_text(text)
(share / 'build.json').write_text(json.dumps({
    'channel': 'quay.io/fedora/fedora-bootc:latest', 'fedora_version': version,
    'base_image': sys.argv[2], 'source_revision': sys.argv[3], 'image_reference': reference,
}, indent=2) + '\n')

for path in Path('/usr/bin').glob('gniri-*'):
    path.chmod(0o755)
subprocess.run(['systemctl', 'preset-all'], check=True)
# The Flatpak RPM itself ships this first-boot provisioner; checking the
# build-time remote list alone does not stop it from adding Fedora on boot.
subprocess.run(['systemctl', 'mask', 'flatpak-add-fedora-repos.service'], check=True)
subprocess.run(['systemctl', 'set-default', 'graphical.target'], check=True)
subprocess.run(['systemctl', '--global', 'preset-all'], check=True)

# Flatpak's RPM may ship .flatpakrepo files; none may auto-provision remotes.
remote_files = list(Path('/etc/flatpak/remotes.d').glob('*')) + list(Path('/usr/share/flatpak/remotes.d').glob('*'))
if remote_files:
    raise SystemExit(f'Unexpected automatic Flatpak remotes: {remote_files}')

subprocess.run(['rpm', '-qa', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n'],
               stdout=(share / 'packages.txt').open('w'), check=True)
desktop_entries = sorted(str(p) for p in Path('/usr/share/applications').glob('*.desktop'))
(share / 'desktop-entries.txt').write_text('\n'.join(desktop_entries) + '\n')
visible = []
for entry in desktop_entries:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(entry)
    desktop = parser['Desktop Entry']
    if desktop.getboolean('NoDisplay', fallback=False) or desktop.getboolean('Hidden', fallback=False):
        continue
    allowed = set(desktop.get('OnlyShowIn', 'GNOME;niri;').split(';'))
    denied = set(desktop.get('NotShowIn', '').split(';'))
    if not ({'GNOME', 'niri'} & allowed - denied):
        continue
    visible.append(Path(entry).name)
expected = {line.split('#')[0].strip() for line in
            Path('/run/gniri-build/packages/visible-applications.allow').read_text().splitlines()}
expected.discard('')
if set(visible) != expected:
    raise SystemExit(f'Unexpected launcher inventory: added {set(visible) - expected}, missing {expected - set(visible)}')
(share / 'visible-applications.txt').write_text('\n'.join(visible) + '\n')
