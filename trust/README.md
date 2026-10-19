# Image signing

Before publishing, generate your own key pair with `cosign generate-key-pair`.
Keep `cosign.key` private and add **only** `cosign.pub` to this directory.
Configure GitHub secrets `COSIGN_PRIVATE_KEY` (the encrypted private key contents)
and `COSIGN_PASSWORD`.

Local `localhost/gniri:development` builds do not require a key. Registry builds
fail without the public key. The installed policy requires that key for the
Gniri repository, without restricting unrelated Podman images.

Secure Boot and OCI image signing are separate mechanisms. The former uses
Fedora's signed shim/GRUB/kernel; the latter authenticates OS updates.
