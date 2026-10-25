#!/usr/bin/env bash
set -euo pipefail
if (( EUID != 0 )) || (( $# < 2 || $# > 3 )); then
    printf 'Use make iso for a local image, or make iso-published with PAYLOAD_REF and TARGET_REF.\n' >&2
    exit 1
fi
payload=$1 target=$2
# Optional override for the build and the privileged image-builder container.
# Empty keeps Podman's default isolation; never force host networking in CI.
network_args=()
if [[ -n ${3:-} ]]; then
    network_args+=(--network="$3")
fi
# shellcheck source=scripts/iso-common.sh
source "${BASH_SOURCE[0]%/*}/iso-common.sh"
gniri_validate_iso_refs "$payload" "$target"
# renovate: datasource=docker depName=ghcr.io/osbuild/image-builder-cli
builder=ghcr.io/osbuild/image-builder-cli:latest@sha256:98b1e2f70a0df78baaef727098fb1153ea52fb7cd336ecd45a4cc14bab5e418c
if [[ $payload == localhost/gniri:development ]]; then
    podman image exists "$payload" || {
        printf 'The local payload is absent from rootful Podman. Use make iso.\n' >&2
        exit 1
    }
else
    podman pull "$payload"
fi
# containers-storage reconstructs layer blobs in /var/tmp when bootc reads it.
# On the live ISO that directory is RAM-backed. Export once at build time to an
# OCI directory: its immutable blobs can be streamed straight from squashfs.
# Keep this multi-GB staging directory on the build disk, not the host's /tmp.
mkdir -p output/iso
payload_dir=$(mktemp -d "$PWD/output/installer-payload.XXXXXX")
build_dir=''
cleanup() {
    rm -rf -- "$payload_dir"
    if [[ -n $build_dir ]]; then rm -rf -- "$build_dir"; fi
}
trap cleanup EXIT
podman save --format oci-dir --output "$payload_dir" "$payload"
podman build "${network_args[@]}" --layers -f installer/Containerfile \
    --build-context "gniri-payload=$payload_dir" \
    --build-arg "PAYLOAD_REF=$payload" --build-arg "TARGET_REF=$target" \
    -t localhost/gniri-installer:latest .
# COPY has embedded these blobs in the installer image. Release the staging
# copy before osbuild creates its filesystem trees, squashfs and ISO exports.
rm -rf -- "$payload_dir"
# image-builder requires DefaultRootFs even to introspect a generic ISO input.
# This CLI fallback does not edit the embedded Kickstart or partition any disk:
# the installed system's filesystem is still selected interactively in Anaconda.
# Use fresh output so an older ISO can never make a failed/no-output run pass.
build_dir=$(mktemp -d "$PWD/output/iso-build.XXXXXX")
printf 'Generating installer ISO. Build log: %s/output/iso-build.log\n' "$PWD"
if ! podman run "${network_args[@]}" --rm --privileged --security-opt label=type:unconfined_t \
    -v "$build_dir:/output" \
    -v /var/lib/containers/storage:/var/lib/containers/storage \
    "$builder" build --output-dir /output \
    --bootc-ref localhost/gniri-installer:latest \
    --bootc-default-fs ext4 bootc-generic-iso 2>&1 | tee output/iso-build.log; then
    printf 'ISO generation failed. See %s/output/iso-build.log; the previous ISO was not replaced.\n' "$PWD" >&2
    exit 1
fi
python3 scripts/publish-iso.py "$build_dir" output/iso
