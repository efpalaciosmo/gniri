#!/usr/bin/env bash
# Run only in a disposable image, with --network=none and no host home mounted.
set -euo pipefail
[[ -f /run/.containerenv ]]
[[ $(readlink /etc/systemd/system/flatpak-add-fedora-repos.service) == /dev/null ]]
home=$(mktemp -d /var/tmp/gniri-flatpak-test.XXXXXX)
trap 'rm -r -- "$home"' EXIT
useradd --uid 1000 --no-create-home --home-dir "$home" gniri-flatpak-test
chown 1000:1000 "$home"
as_user() {
    runuser -u gniri-flatpak-test -- env HOME="$home" XDG_DATA_HOME="$home/.local/share" "$@"
}
for _ in 1 2; do
    as_user flatpak remote-add --user --if-not-exists flathub /usr/share/gniri/flathub.flatpakrepo
done
[[ $(as_user flatpak remotes --user --columns=name) == flathub ]]
[[ $(as_user flatpak remotes --user --columns=url) == https://dl.flathub.org/repo/ ]]
[[ $(as_user ostree --repo="$home/.local/share/flatpak/repo" config get 'remote "flathub".gpg-verify') == true ]]
[[ -s $home/.local/share/flatpak/repo/flathub.trustedkeys.gpg ]]
[[ -z $(as_user flatpak list --user --columns=application) ]]
[[ -z $(flatpak remotes --system --columns=name) ]]
printf 'Offline user Flathub registration, GPG verification and idempotence passed.\n'
