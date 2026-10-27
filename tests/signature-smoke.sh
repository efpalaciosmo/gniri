#!/usr/bin/env bash
# Run in the published-image-derived disposable container, with temporary CI auth.
set -euo pipefail
[[ -f /run/.containerenv && $# == 3 ]]
authfile=/run/registry-auth.json
[[ -s $authfile ]]
policy=/usr/share/gniri/bootc-policy.json
# OCI directories cannot store registry signatures. This only suppresses copying
# them to the destination: --policy still verifies the source before copying.
skopeo --policy "$policy" copy --authfile "$authfile" --remove-signatures "docker://$1" oci:/var/tmp/signed-policy-test
reject() {
    local reference=$1 expected=$2
    # Prove the image is reachable: a DNS/auth/not-found failure is not a valid
    # negative signature test. Inspect alone does not verify image signatures.
    skopeo inspect --authfile "$authfile" "docker://$reference" >/dev/null
    if skopeo --policy "$policy" copy --authfile "$authfile" --remove-signatures "docker://$reference" oci:/var/tmp/rejected-policy-test \
        > /var/tmp/gniri-signature-error.log 2>&1; then
        printf 'ERROR: an unsigned or wrong-key image was accepted: %s\n' "$reference" >&2
        exit 1
    fi
    cat /var/tmp/gniri-signature-error.log
    # A timeout while fetching signatures must not be counted as a rejection.
    grep -Ei "$expected" /var/tmp/gniri-signature-error.log
}
reject "$2" 'signature was required, but no signature exists|no signatures found'
reject "$3" 'invalid signature|signature verification failed'
printf 'Real containers/image policy: trusted signature accepted; unsigned/wrong-key rejected.\n'
