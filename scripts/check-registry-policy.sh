#!/usr/bin/env bash
# Create unique negative OCI fixtures; never change the OS update tag.
set -euo pipefail
source_image=${1:?Local candidate image required}
repository=${2:?Published Gniri repository required}
good_digest=${3:?Signed candidate digest required}
[[ $repository =~ ^ghcr.io/[a-z0-9._/-]+$ && $good_digest =~ ^sha256:[a-f0-9]{64}$ ]]
[[ ${GITHUB_ACTIONS:-} == true ]]
work=$(mktemp -d)
trap 'rm -r -- "$work"' EXIT
run_id="${GITHUB_RUN_ID:?}-${GITHUB_RUN_ATTEMPT:?}"
for kind in unsigned wrong-key; do
    printf 'FROM %s\nLABEL gniri.policy-test="%s-%s"\n' "$source_image" "$run_id" "$kind" |
        sudo podman build -f - -t "localhost/gniri-policy-test:$kind" .
    sudo podman push --digestfile "$work/$kind.digest" "localhost/gniri-policy-test:$kind" \
        "$repository:policy-test-$run_id-$kind"
done
# These temporary keys test OCI signatures only, never Secure Boot keys.
export COSIGN_PASSWORD
COSIGN_PASSWORD=$(openssl rand -hex 32)
cosign generate-key-pair --output-key-prefix "$work/wrong-key"
wrong_digest=$(cat "$work/wrong-key.digest")
cosign sign --yes --new-bundle-format=false --use-signing-config=false \
    --registry-referrers-mode=legacy --key "$work/wrong-key.key" "$repository@$wrong_digest"
sudo podman run --rm --network=host --entrypoint bash \
    -v "$PWD/tests/signature-smoke.sh:/run/signature-smoke.sh:ro" \
    "$source_image" /run/signature-smoke.sh "$repository@$good_digest" \
    "$repository@$(cat "$work/unsigned.digest")" "$repository@$wrong_digest"
