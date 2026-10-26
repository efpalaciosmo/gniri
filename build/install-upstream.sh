#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=upstream.env
source /run/gniri-build/upstream.env
[[ $(uname -m) == x86_64 ]]
cache=/var/cache/gniri
mkdir -p "$cache"
work=$(mktemp -d)
trap 'rm -r "$work"' EXIT

fetch() {
    local name=$1 url=$2 checksum=$3
    if ! printf '%s  %s\n' "$checksum" "$cache/$name" | sha256sum --check --status; then
        curl --fail --location --retry 5 --output "$cache/$name" "$url"
    fi
    printf '%s  %s\n' "$checksum" "$cache/$name" | sha256sum --check
}

fetch "JetBrainsMono-${NERD_FONTS_VERSION}.tar.xz" \
    "https://github.com/ryanoasis/nerd-fonts/releases/download/v${NERD_FONTS_VERSION}/JetBrainsMono.tar.xz" \
    "$NERD_FONTS_SHA256"
mkdir "$work/fonts"
tar -xJf "$cache/JetBrainsMono-${NERD_FONTS_VERSION}.tar.xz" -C "$work/fonts"
install -d /usr/share/fonts/jetbrains-mono-nerd /usr/share/licenses/gniri-nerd-fonts
# Keep every weight of the family actually used by the defaults, without
# duplicating the NL, Propo and Nerd Font Mono variants from the full archive.
find "$work/fonts" -name 'JetBrainsMonoNerdFont-*.ttf' -exec install -m 0644 -t /usr/share/fonts/jetbrains-mono-nerd/ {} +
install -m 0644 "$work/fonts/OFL.txt" /usr/share/licenses/gniri-nerd-fonts/

# Pinned upstream tools; review RPM availability when the stable base changes.
fetch "starship-${STARSHIP_VERSION}.tar.gz" \
    "https://github.com/starship/starship/releases/download/v${STARSHIP_VERSION}/starship-x86_64-unknown-linux-musl.tar.gz" \
    "$STARSHIP_SHA256"
tar -xzf "$cache/starship-${STARSHIP_VERSION}.tar.gz" -C "$work" starship
install -m 0755 "$work/starship" /usr/bin/starship
fetch "zsh-completions-${ZSH_COMPLETIONS_VERSION}.tar.gz" \
    "https://codeload.github.com/zsh-users/zsh-completions/tar.gz/refs/tags/${ZSH_COMPLETIONS_VERSION}" \
    "$ZSH_COMPLETIONS_SHA256"
tar -xzf "$cache/zsh-completions-${ZSH_COMPLETIONS_VERSION}.tar.gz" -C "$work"
install -d /usr/share/zsh/site-functions /usr/share/licenses/gniri-zsh-completions
install -m 0644 "$work/zsh-completions-${ZSH_COMPLETIONS_VERSION}"/src/_* /usr/share/zsh/site-functions/
install -m 0644 "$work/zsh-completions-${ZSH_COMPLETIONS_VERSION}/LICENSE" /usr/share/licenses/gniri-zsh-completions/
install -d /usr/share/zsh/site-functions
STARSHIP_CACHE="$work/starship-cache" starship completions zsh > /usr/share/zsh/site-functions/_starship
fetch "flathub-${FLATHUB_REPO_SHA256}.flatpakrepo" \
    'https://flathub.org/repo/flathub.flatpakrepo' "$FLATHUB_REPO_SHA256"
install -D -m 0644 "$cache/flathub-${FLATHUB_REPO_SHA256}.flatpakrepo" \
    /usr/share/gniri/flathub.flatpakrepo
fc-cache --force
