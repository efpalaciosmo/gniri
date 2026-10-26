# Image signing

Before publishing, generate your own key pair with `cosign generate-key-pair`.
Keep `cosign.key` private and add **only** `cosign.pub` to this directory.
Configure GitHub secrets `COSIGN_PRIVATE_KEY` (the encrypted private key contents)
and `COSIGN_PASSWORD`.

Local `localhost/gniri:development` builds do not require a key. Registry builds
fail without the public key. The installed policy requires that key for the
Gniri repository, without restricting unrelated Podman images.

The general containers policy preserves Fedora defaults plus the Gniri rule.
The updater selects a separate immutable `/usr/share/gniri/bootc-policy.json`
with `default: reject`; bootc's enforced mode rejects an insecure global default
even if a repository rule requires signatures. Do not replace this strict policy
with the general Podman policy, or use raw `bootc upgrade` as the documented path.

Published ISO generation verifies the digest with Cosign before pulling it on
both local and CI paths. CI publishes candidates only and tests the shipped
containers/image client against signed, unsigned and wrong-key manifests.
Bootc update/rejection and Secure Boot still require the VM release gate.
Promotion needs reviewed evidence and protected-environment approval; see
[releases](../docs/releases.md). Generating a signing key alone is not a release gate.

Secure Boot and OCI image signing are separate mechanisms. The former uses
Fedora's signed shim/GRUB/kernel; the latter authenticates OS updates.
