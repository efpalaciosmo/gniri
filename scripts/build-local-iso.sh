#!/usr/bin/env bash
# No registry or GitHub credentials: use the image built on this workstation.
set -euo pipefail
image=localhost/gniri:development
network=${GNIRI_BUILD_NETWORK:-}
podman image exists "$image" || {
    printf 'Build the local image first with: make build\n' >&2
    exit 1
}
if (( EUID != 0 )); then
    # Rootless and rootful Podman do not share image stores. Stream an OCI
    # archive instead of trying to pull localhost from a registry or keeping
    # an extra multi-GB archive on disk. Authenticate before stdin is a pipe.
    sudo -v
    source_id=$(podman image inspect --format '{{.Id}}' "$image")
    podman save --format oci-archive "$image" | sudo podman load
    loaded_id=$(sudo podman image inspect --format '{{.Id}}' "$image")
    [[ $source_id == "$loaded_id" ]] || {
        printf 'The rootful image does not match the local source.\n' >&2
        exit 1
    }
    # Pass the requested mode explicitly: sudo normally filters environment.
    sudo bash scripts/build-iso.sh "$image" "$image" "$network"
    # Only adjust generated output, never the repository or system files.
    sudo chown -R "$(id -u):$(id -g)" output/iso
else
    bash scripts/build-iso.sh "$image" "$image" "$network"
fi
