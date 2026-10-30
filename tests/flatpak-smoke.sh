#!/usr/bin/env bash
# Run only in a disposable image, with --network=none and no host home mounted.
set -euo pipefail
[[ -f /run/.containerenv ]]
[[ $(readlink /etc/systemd/system/flatpak-add-fedora-repos.service) == /dev/null ]]
# Image /var is not deployed as runtime state. Exercise the boot-time tmpfiles
# boundary too, rather than only checking Flatpak before image finalization.
[[ ! -e /var/lib/flatpak/repo ]]
systemd-tmpfiles --create --prefix=/var/lib/flatpak
mkdir -p /var/lib/flatpak/repo
if flatpak remotes --system >/dev/null 2>/run/flatpak-repo-error; then
    printf 'An empty repository skeleton unexpectedly opened successfully.\n' >&2
    exit 1
fi
grep -F 'opendir(objects)' /run/flatpak-repo-error
read -r -a initialize_repo < <(sed -n 's/^ExecStart=//p' \
    /usr/lib/systemd/system/gniri-flatpak-system-repo.service)
"${initialize_repo[@]}"
[[ -d /var/lib/flatpak/repo/objects && -s /var/lib/flatpak/repo/config ]]
# A second boot must not reset administrator configuration or remotes/keys.
flatpak remote-add --system --if-not-exists flathub /usr/share/gniri/flathub.flatpakrepo
before=$(sha256sum /var/lib/flatpak/repo/config /var/lib/flatpak/repo/flathub.trustedkeys.gpg)
# Also complete a partial repository that already has configuration and keys.
rmdir /var/lib/flatpak/repo/objects
"${initialize_repo[@]}"
"${initialize_repo[@]}"
[[ $(sha256sum /var/lib/flatpak/repo/config /var/lib/flatpak/repo/flathub.trustedkeys.gpg) == "$before" ]]
flatpak remote-delete --system flathub
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
[[ -z $(as_user flatpak remotes --system --columns=name) ]]
[[ -z $(as_user flatpak list --system --columns=application) ]]
[[ -z $(as_user flatpak list --columns=application) ]]
printf 'Offline system repository initialization, user Flathub, GPG verification and idempotence passed.\n'
