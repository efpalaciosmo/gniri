#!/usr/bin/env bash
# Resolve the intended registry channel, never a local build tag.
set -euo pipefail
target=${1:?Expected a GHCR update reference}
network=${2:-}
refresh=${3:-0}
[[ $target =~ ^ghcr.io/[a-z0-9._/-]+:stable$ ]] || {
    printf 'The permanent installer requires ghcr.io/owner/image:stable.\n' >&2
    exit 1
}
digest=$(skopeo inspect --format '{{.Digest}}' "docker://$target")
[[ $digest =~ ^sha256:[a-f0-9]{64}$ ]]
payload="${target%:*}@$digest"
# Verify before asking sudo or starting a costly installer build. The rootful
# recipe verifies the same immutable reference again before importing it.
cosign verify --new-bundle-format=false --key trust/cosign.pub "$payload" >/dev/null
printf 'Verified installer payload: %s\nUpdate origin: %s\n' "$payload" "$target"
if (( EUID == 0 )); then
    bash scripts/build-iso.sh "$payload" "$target" "$network" "$refresh"
else
    sudo bash scripts/build-iso.sh "$payload" "$target" "$network" "$refresh"
fi
