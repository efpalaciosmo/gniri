#!/usr/bin/env bash
# Run in the published-image-derived disposable container, with anonymous access.
set -euo pipefail
[[ -f /run/.containerenv && $# == 3 ]]
policy=/usr/share/gniri/bootc-policy.json
skopeo --policy "$policy" copy "docker://$1" oci:/var/tmp/signed-policy-test
reject() {
    local reference=$1 expected=$2
    # Prove the image is reachable: a DNS/auth/not-found failure is not a valid
    # negative signature test. Inspect alone does not verify image signatures.
    skopeo inspect "docker://$reference" >/dev/null
    if skopeo --policy "$policy" copy "docker://$reference" oci:/var/tmp/rejected-policy-test \
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
