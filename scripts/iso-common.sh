#!/usr/bin/env bash
# Shared by the host recipe and the installer-container build.
gniri_validate_iso_refs() {
    local payload=${1:-} target=${2:-}
    if [[ $payload == localhost/gniri:development && $target == "$payload" ]]; then
        return 0
    fi
    if [[ $payload =~ ^quay\.io/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$ &&
          $target =~ ^quay\.io/[a-z0-9._/-]+:(stable|latest)$ &&
          ${payload%@*} == "${target%:*}" ]]; then
        return 0
    fi
    printf 'Use the local development image for both refs, or a Quay.io digest and matching :stable/:latest target.\n' >&2
    return 1
}
