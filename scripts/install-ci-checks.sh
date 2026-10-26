#!/usr/bin/env bash
set -euo pipefail
# GitHub-hosted runners only; local checks never install host packages.
[[ ${GITHUB_ACTIONS:-} == true ]]
sudo apt-get update
sudo apt-get install -y shellcheck podman skopeo
mkdir -p "$HOME/.local/bin"
GOBIN="$HOME/.local/bin" go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
printf '%s\n' "$HOME/.local/bin" >> "$GITHUB_PATH"
