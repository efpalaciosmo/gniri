#!/usr/bin/env bash
# Payload identity changes must not invalidate installer RPMs or initramfs.
set -euo pipefail
payload=${1:?Payload image required}
target=${2:?Target image reference required}
# shellcheck source=scripts/iso-common.sh
source /run/gniri-iso-common.sh
gniri_validate_iso_refs "$payload" "$target"
# No clearpart, autopart, user password, reboot or non-interactive directives.
# Published payloads are pinned by digest and update from :stable. Local
# development payloads do not fetch updates. Both install from immutable OCI
# blobs embedded in squashfs, without rebuilding multi-GB layers in live RAM.
cat > /usr/share/anaconda/interactive-defaults.ks <<EOF
bootc --source-imgref oci:/usr/share/gniri/installer-payload --target-imgref ${target}
selinux --enforcing
%post --nochroot --erroronfail
/usr/bin/python3 /usr/libexec/gniri-installer-finalize.py --target-ref "${target}"
%end
EOF
