# Validation record

## Installer memory and desktop follow-up (2026-10-19)

- The user reports that the previous ISO installs and permits login with 10 GiB
  guest RAM, but Kitty and the Niri session do not open. This is not a successful
  validation of both desktop sessions.
- The failure with less guest RAM was identified in `packaging.log`:
  `write /var/tmp/container_images_…: no space left on device`. The destination
  had 46 GB free; `/var/tmp` used the live overlay with a 1.2 GB limit. Raising
  RAM or remounting `/run` is not the installer solution.
- The ISO recipe now exports a directory OCI payload on the build disk, embeds
  it in the installer, and uses `oci:/usr/share/gniri/installer-payload` instead
  of containers-storage. OCI reads immutable blobs directly rather than
  reconstructing them in live `/var/tmp`. The old image-builder payload-copy
  argument is removed to avoid embedding the image twice.
- A real export of the local payload (75 layers, approximately 1.9 GB of OCI
  blobs) and `ostree container image pull` succeeded offline in a disposable
  rootless container with `/var/tmp` limited to **64 MiB**. It remained empty
  after import. The destination repository was on the build disk. This tests
  the import path, not Anaconda partitioning, bootloader installation or peak
  total guest memory.
- Podman's named directory build context and `skopeo inspect` on the embedded
  OCI payload passed in a separate installer-derived test image.
- The complete updated installer Containerfile also built successfully, including
  its Anaconda initramfs and embedded OCI blobs. Pykickstart parsed the generated
  Kickstart and confirmed the OCI source and local development update target;
  the installer remains permissive while the target requests Enforcing.
- `make build` passed with `f44-backgrounds-gnome`, its base package,
  `gnome-backgrounds` and explicit `dbus-tools`. Fedora's wallpaper metadata
  and day/night JXL assets exist. Graphics `dlopen` checks, Kitty's native module,
  Niri validation and all 14 bootc lint checks passed (one upstream skip).
- `make check-desktop` passed on the rebuilt image: test-only headless Weston,
  nested Niri with the actual fallback configuration, and a Kitty window
  confirmed by Niri IPC. Software rendering was limited to the disposable test
  container; no global software-rendering setting, host display socket or host
  GPU access was used. Weston is not part of the distributed image.
- Static checks, 40 unit tests and ShellCheck on changed shell scripts passed.
  Actual GDM/DRM behavior in the user's VM still requires the Niri user journal
  and Kitty's startup error; no unverified compositor/GPU workaround is shipped.
- Regenerate the ISO to include these changes. End-to-end installation with the
  new OCI source and a measured lower-memory guest is still pending.

## Earlier validation

Local x86_64 build validated again after separating personal dotfiles and
switching updates to Sundays (2026-10-18, local date).

- `podman build --layers --tag localhost/gniri:development .`: passed.
- `bootc container lint --fatal-warnings`: **14 checks passed**, one skipped
  by bootc, no lint warnings.
- All requested Fedora RPM names resolve. Starship/zsh-completions use pinned
  upstream inputs because Fedora 44 does not provide those packages.
- `make check`: source syntax, minimal Niri configuration and unit tests pass.
- ShellCheck (container, warning level): passed.
- Actionlint and workflow YAML parsing: passed.
- `niri validate`: passed with both the host's Niri and Fedora's image package.
- User session services and Niri pass `systemd-analyze --user verify`.
- Installed module discovery: amdgpu, kvm_amd, uinput and wacom present.
- Selected boot path: OSTree with composefs enabled (`enabled=yes`), read-only
  sysroot, Fedora shim/GRUB/bootupd and a non-UKI kernel. No native-backend marker
  or generated UKI; actual Secure Boot boot testing is still pending.
- JetBrainsMono Nerd Font found by Fontconfig; family uses approximately 40 MiB,
  without shipping redundant NL/Propo/Mono variants.
- Only `/etc/niri/config.kdl` is shipped, with no dotfile bundle, theme override
  or login-copying service. The original external dotfiles were not modified.
- Fastfetch 2.68.1 added; `vi` remains supplied by `vim-minimal` (Vim 9.2).
- `systemd-analyze calendar` resolves Sunday 10:00 in the local timezone.
  The effective timer has no additional boot or interval triggers.
- Exactly seven visible host applications; no browser or system Flatpak remote.
- Overlay contents in the image match the repository's current system files.
- Local ISO orchestration has reference-validation and mocked sudo/Podman tests:
  streaming rootless images to rootful storage, rejecting mismatched image IDs,
  and stopping on missing images/export failures. These tests do not create an
  ISO or execute privileged installation operations.
- The separate installer container was built successfully with both references
  set to `localhost/gniri:development`. Its Kickstart selects the local
  containers-storage payload; Anaconda initramfs and Fedora EFI boot files are
  present. This is not yet a generated or boot-tested ISO.
- The user's generated ISO was inspected read-only: SHA-256 matches
  `SHA256SUMS`, El Torito includes a UEFI boot entry, and its `Install Gniri`
  GRUB entry originally contained neither `selinux=0` nor `enforcing=0`.
  A subsequent user boot attempt froze PID 1 with SELinux context failures;
  absence of those flags was not evidence of a working installer.
- With user approval, the installer recipe now uses `selinux=1 enforcing=0`
  and a permissive installer config, following Anaconda/bootc's runtime model.
  The separate desktop payload remains Enforcing and rejects permissive boot
  arguments during validation; Kickstart requests `selinux --enforcing` for
  the installed system. Runtime behavior must still be verified in the VM.
- A 90-second QEMU/KVM diagnostic with no destination disk or networking booted
  the existing ISO's extracted kernel/initramfs with those temporary arguments.
  It loaded SELinux policy, passed switch-root and `basic.target`, and started
  `anaconda-pre.service` without the reported PID 1 freeze. Exit 124 was the
  intentional timeout (QEMU received SIGTERM), not a kernel panic. Direct kernel
  boot bypassed UEFI/Secure Boot; the installer UI and installation were not
  validated. A `.buildstamp missing` warning remains to investigate if needed.
- The rebuilt installer container contains `SELINUX=permissive`, the explicit
  live boot arguments, and a separate `selinux --enforcing` Kickstart directive.
- The `/usr/local/sbin` tmpfiles warning was reproduced on the previous image
  with a read-only root (exit 73). After creating the directory during image
  composition, the inherited rule passes with a read-only root (exit 0).
  The corrected installer container was also rebuilt successfully, and the
  same inherited rule passes there with a read-only root (exit 0). Existing
  ISOs are not rewritten; regenerate them to include it.
- Expanded local image size: approximately 4.2 GiB. This is **not** an OCI
  compressed download size. QEMU, ARM emulation, firmware and kernel modules
  account for substantial non-desktop content.

Known non-fatal RPM output may include GSettings deprecated-path notices and
SELinux/audit scriptlet messages specific to container builds.
These do not constitute a tested boot or a running SELinux policy check.

**Not performed by the agent:** public GHCR publication/signature enforcement
against a real registry, privileged ISO generation, installation and installed-system
boot, UEFI/Secure Boot validation, actual graphics,
Wacom/controller, guest 3D, update/rollback or suspend tests. No account, private
signing key or registry credentials were embedded. No host rebase or installation
was performed. See [the release gate](testing.md) before using on bare metal.
The local ISO recipe still needs an end-to-end privileged run; sudo authentication
is interactive and was not available to the agent. GitHub is no longer a
prerequisite for that local run.

## Interpreting the observed build messages

- `/usr/local/sbin: Read-only file system`: osbuild runs tmpfiles with `/usr`
  mounted read-only; an inherited rpm-ostree rule requested a missing directory.
  This was a real missing path, not merely dismissed as harmless. Bake the
  directory into both images instead of making `/usr` writable or hiding errors.
- `Not using native diff ... CONFIG_OVERLAY_FS_REDIRECT_DIR`: containers/storage
  selects its fallback diff implementation. This is a build-time performance
  message; it does not change kernel selection, Secure Boot or the filesystem
  contents being packaged. No host kernel/storage settings were changed.
- Missing `/dev/log`/audit connection during container composition: does not
  demonstrate a boot-time logging failure. Runtime logging and SELinux still
  need to be checked after installation.

A successful build or checksum is not proof that a desktop OS is ready for
bare metal. In the installed test VM, check `mokutil --sb-state`, `getenforce`,
`systemctl --failed` and `bootc status`, then test both desktops and an
update/rollback cycle before migrating the primary workstation.
