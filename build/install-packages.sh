#!/usr/bin/env bash
set -euo pipefail

mapfile -t packages < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' /run/gniri-build/packages/*.txt)
source /usr/lib/os-release
[[ $ID == fedora && $VERSION_ID =~ ^[0-9]+$ && ${RELEASE_TYPE:-} == stable ]]
packages+=("f${VERSION_ID}-backgrounds-gnome")
# Restrict this community repository to Ghostty; all other RPMs stay on Fedora.
# Source documented at https://ghostty.org/docs/install/binary#fedora.
cat > /etc/yum.repos.d/ghostty.repo <<'EOF'
[ghostty]
name=Ghostty (scottames COPR)
baseurl=https://download.copr.fedorainfracloud.org/results/scottames/ghostty/fedora-$releasever-$basearch/
enabled=1
skip_if_unavailable=False
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://download.copr.fedorainfracloud.org/results/scottames/ghostty/pubkey.gpg
includepkgs=ghostty
EOF
dnf5 -y --refresh --setopt=keepcache=True --setopt=install_weak_deps=False upgrade
dnf5 -y --setopt=keepcache=True --setopt=install_weak_deps=False install "${packages[@]}"

# Tailscale's official stable repository is the only external RPM source.
cat > /etc/yum.repos.d/tailscale.repo <<'EOF'
[tailscale-stable]
name=Tailscale stable
baseurl=https://pkgs.tailscale.com/stable/fedora/$basearch
enabled=1
repo_gpgcheck=1
gpgcheck=1
gpgkey=https://pkgs.tailscale.com/stable/fedora/repo.gpg
includepkgs=tailscale
EOF
dnf5 -y --setopt=keepcache=True --setopt=install_weak_deps=False install tailscale

# An RPM must not provision Flatpak remotes behind our back.
# Refuse unexpected content instead of silently removing installed applications.
for package in firefox fedora-flathub-remote fedora-flatpak-remotes; do
    if rpm -q "$package" >/dev/null 2>&1; then
        printf 'Unexpected browser or system Flatpak remote package: %s\n' "$package" >&2
        exit 1
    fi
done

# Clean transaction history in the layer that created it, rather than hiding it
# in a later layer. Download caches are separate cache mounts and remain reusable.
rm -rf /var/lib/dnf/* /var/log/dnf* /var/log/hawkey.log
