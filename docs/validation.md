# Validation record

## Installer finalization regression (2026-10-19, afternoon)

- Reproduced the screenshots' exact `mkdir(boot/loader.0): Read-only file system`
  failure using OSTree 2026.4 from the Fedora 45 installer and a separate,
  read-only tmpfs `/boot`. The failed transaction retained the original `fstab`.
  The earlier direct-kernel VM test below reopened mounts manually and did not
  test Anaconda's complete installation lifecycle.
- Corrected the lifecycle: Anaconda's `bootc install to-filesystem` invocation
  passes `--skip-finalize`, keeping the offline target writable until Anaconda
  completes configuration and unmounts it. The finalizer now reloads the saved
  deployment and verifies rootflags and the other arguments before editing
  `fstab`. Real OSTree smoke tests pass with shared/separate `/boot`, including
  preservation of repeated `console=` arguments, backup and idempotency.
- Rebuilt `localhost/gniri-installer:finalize-validation` successfully. Its
  `/.buildstamp` reports `Version=45`, `IsFinal=True`, derived from the base's
  `VERSION_ID=45`, `RELEASE_TYPE=stable`. Unit tests also retain the pre-release
  warning for development, beta, unknown or missing maturity. Both runtime and
  initramfs use the generated buildstamp; no UI widget or warning is suppressed.
- Performed a **fresh Fedora 45 Anaconda installation**, followed by a normal
  UEFI/GRUB boot of the resulting disk in QEMU/KVM with 4 GiB RAM. The test used
  the existing ISO's embedded payload plus Anaconda's official `inst.updates`
  mechanism to load the rebuilt install task, finalizer and buildstamp. Only
  `.cache/finalize-vm/install.qcow2`, a new disposable 30 GiB disk, was attached.
  The test Kickstart is isolated in `.cache`; disk-erasure directives were not
  added to the interactive installer shipped by the project.
- Anaconda finished all post-installation scripts and powered off normally.
  On first boot, the verification service reported **ActiveState=active,
  SubState=exited, Result=success** for `systemd-remount-fs`, **SELinux Enforcing**,
  read-only composefs `/` and physical `/sysroot`, and writable Btrfs `/home`.
  The test user's home existed on its home subvolume with the correct owner.
  `/proc/cmdline` retained `rootflags=subvol=root,compress=zstd:1`; `/etc/fstab`
  retained `/boot`, EFI and home entries, without the physical-root `/` entry.
  Serial logs are local artifacts under `.cache/finalize-vm/` and the extracted
  result is `.cache/finalize-first-boot-result.log`.
- `make check`: **73 tests passed**. ShellCheck passed for the changed installer
  recipe; the rebuilt Anaconda tasks passed all four existing mount layouts.
- This test did **not** validate Secure Boot, graphical login or upgrades. The
  production ISO at `output/iso/gniri-x86_64.iso` still needs regeneration with
  `make iso`; rootful Podman requires interactive sudo authentication here.
  Existing user VM disks were not modified.

## Fedora 45, Flathub and remount follow-up (2026-10-19)

- At the user's explicit request, both images now use the official `45` tag,
  pinned to `sha256:4776d2e96e263938a1b54c5c3a4cdd1c2ca723207b063a58ef36e1eda2fc9d61`.
  The fetched base reports `VERSION_ID=45`, `RELEASE_TYPE=stable`; Fedora's
  public releases JSON still lists 45 Beta. This inconsistency was disclosed;
  tag availability/metadata is not a production-readiness guarantee.
- `make build BUILD_NETWORK=host` passed: official Fedora kernel/shim/GRUB,
  OSTree+composefs, persistent `/etc`/`/var`, SELinux Enforcing, correct Fedora 45
  backgrounds, graphics library checks, unchanged seven-app launcher allowlist,
  and 14 bootc lint checks (one upstream skip). Distrobox 1.8.2.5 is installed;
  no containers are pre-created. NetworkManager, resolved and firewalld are enabled.
- `make check-desktop BUILD_NETWORK=host` passed on Fedora 45: a Kitty window
  mapped in nested Niri under test-only headless Weston. This is not a GDM or
  physical GPU/monitor validation.
- `tests/flatpak-smoke.sh` passed with `--network=none` as a disposable UID-1000
  user: the bundled, checksum-verified official descriptor registered Flathub;
  its URL/key and GPG verification were checked, a second run was idempotent,
  and no user apps or system remotes were created. An offline summary warning
  is expected. The Fedora first-boot remote provisioner is disabled AND masked.
  Existing installed-system remotes are deliberately not deleted automatically.
- The complete Fedora 45 installer built as
  `localhost/gniri-installer:fedora45-validation`, with the rebuilt Fedora 45
  OCI payload. Its Kickstart parsed with an error-on-failure non-chroot finalizer.
  The real Anaconda 45.29-1 mount tasks passed all four tmpfs layouts. Its
  upstream home fix is retained/checked rather than overwritten with the 44 patch.
- Reproduced `systemd-remount-fs` failing with
  `overlay: No changes allowed in reconfigure` in a copy of the user's Fedora 44
  installation. Executed the new root-fstab finalizer in a disposable qcow2 overlay,
  preserving `root=`, other kargs, `subvol=root` and `compress=zstd:1`. After a second
  QEMU/KVM boot using the resulting BLS arguments, the service reported
  **ActiveState=active, SubState=exited, Result=success**; `/` and `/sysroot` stayed
  read-only and SELinux stayed **Enforcing**. Other fstab entries were unchanged.
  This validates the actual migration/boot behavior, not a fresh Fedora 45 ISO
  installation; direct kernel boot bypassed UEFI/Secure Boot.
- `make check`: 70 tests pass; changed Bash scripts pass ShellCheck, and
  `git diff --check` passes. Original VM/disk/host firewall were not changed.
- Host UFW configuration has DROP input/forward policies and no user exceptions
  for libvirt; kernel logs explicitly show blocked Podman DNS forwarding from
  `podman0` to `wlan0`. This explains the rootful build DNS error. Guest DHCP on
  libvirt still needs the scoped host firewall allowances and a runtime retest;
  no claim is made that changing the Fedora image alone fixes that host path.
- Still pending: privileged ISO generation, a fresh Fedora 45 Anaconda install
  and graphical login, Secure Boot, physical hardware, updates and rollback.
  The screenshots did not include Fastfetch's disks output; that specific disk
  layout cannot be judged without its output/`lsblk`/`findmnt`.

## Home directory and networking diagnosis (2026-10-19)

- Inspected a sparse copy of the shut-down `fedora44` VM disk with libguestfs.
  The original disk, VM definition and host firewall were not changed.
- Confirmed `/home -> var/home` and an `efrain` account whose home is
  `/home/efrain`. Anaconda created its directory in the stateroot's backing
  `/var/home`, but `fstab` mounts a separate, empty Btrfs `home` subvolume there
  on boot. This is hidden installation state, not proof the user was never created.
- Fedora's Anaconda 44.30-2 unmounts `/home` in `DeployBootcTask._clean_physroot`
  and omits its deployment bind mount in `PrepareBootcMountTargetsTask.run`.
  Applied the relevant mount-preservation/binding logic from upstream
  [dc4d94d279fe / #7220](https://github.com/rhinstaller/anaconda/pull/7220), keeping
  Fedora 44's supported mountpoint allowlist. The checked fix applies to the
  actual installed RPM source and the patched module compiles.
- Added installer runtime/initramfs `.buildstamp` metadata and guarded both
  Anaconda `edd` requests on native UEFI. The actual RPM hooks patch successfully
  and pass Bash syntax checks. This does not remove or blacklist the BIOS driver.
- Original guest journal: virtio Ethernet/link detected; DHCP repeatedly times
  out with `ip-config-unavailable`. Host libvirt NAT/DHCP is configured but has
  no leases; host UFW is active and logs `virbr0` blocks. These observations do
  not alone identify the exact dropping firewall rule.
- Booted a disposable qcow2 overlay of that same installed system with QEMU/KVM
  user networking. NetworkManager acquired `10.0.2.15` via DHCP; DNS resolved
  `fedoraproject.org` and HTTPS returned HTTP 200. SELinux remained Enforcing.
  The only injected guest files were a diagnostic oneshot/script in the overlay;
  no network settings or installed packages were changed. Direct kernel boot
  bypassed UEFI/Secure Boot; this is not a Secure Boot or desktop test.
- `make check`: 55 tests pass, including mount preservation/order and BIOS/UEFI
  hook branches. ShellCheck passes for the changed installer shell script.
- The real patched Anaconda cleanup/preparation tasks passed four disposable
  tmpfs/bind-mount tests: separate home, no separate home, separate home+var,
  and EFI without a separate `/boot`. The tests write a UID-1000 home through
  the deployment and verify it reaches the intended persistent mount; the EFI
  bind remains visible too. This caught and corrected parent `/boot` ordering
  that would otherwise hide the nested EFI bind. No partitioner or disks are
  used by `tests/installer-mount-smoke.py`; SELinux labels/login are not tested.
- The complete installer Containerfile rebuilt successfully as
  `localhost/gniri-installer:mounts-validation`, including its embedded OCI
  payload and regenerated initramfs. The four mount tests also pass against
  that final image. The initramfs `.buildstamp` matches the runtime file and
  both embedded Anaconda hooks contain the UEFI guard. Privileged ISO generation
  was not run (`sudo` requires interactive authentication).
- A new end-to-end Anaconda installation is still required.
- See [Spanish diagnosis, safe recovery and host-network checks](installer-troubleshooting.md).
  Recovery commands are documented, not executed against the original VM.

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
