# Release gate

Do not call this image production-ready until these checks pass. Container
build validation is not a substitute for a boot test.

## Artifact-specific evidence

Every release starts with a new evidence record. Checkboxes below are a test
inventory, **not** proof that current HEAD passed. Historical results belong to
the dated images in [validation.md](validation.md), not future builds.
The source workflow requires ShellCheck/actionlint; the image workflow also
runs nested Kitty/Niri, offline Flatpak and real containers/image signature
acceptance/rejection. The ISO workflow runs the real installer regressions.
Full bootc enforcement, GDM, Secure Boot and physical hardware remain separate
gates. See [candidate promotion](releases.md): stable is never updated by a build.

Record the source revision, payload digest, resolved Fedora base, ISO SHA-256,
VM firmware/certificate configuration and test logs. `output/iso/build.json`
binds the inputs to that ISO but deliberately declares it untested. Complete
the generated evidence template only after running every check. Configure
reviewers for GitHub's `stable` environment; do not use placeholder evidence.

After `make build`, run `make check-desktop` to launch a test-only headless
Weston, start the image's Niri with its real fallback configuration, and verify
that Kitty maps a window in Niri. The test uses software rendering in an isolated
container without host display/GPU access. Weston is not added to Gniri. This
checks more than package presence, but does not validate GDM, logind, SELinux or
the VM's DRM/3D setup.

## Source and image

- [x] `make check`: Bash/Python syntax, English minimal Niri configuration,
      no personal dotfiles, weekly scheduling and safe update tests.
- [ ] Release `make build REFRESH=1`: RPM resolution, upstream checksums, font discovery,
      modules, desktop sessions and `bootc container lint`.
- [ ] Release launcher review: Files, Settings, Software, Kitty, Zathura,
      virt-manager and btop. Subsequent builds enforce the allowlist, now including nvtop.
- [ ] No Firefox, unwanted GNOME applications, system remotes or Flatpak apps.
- [ ] User session units pass `systemd-analyze verify`; no ordering cycles.
- [ ] No `/usr/local/sbin` creation warning from tmpfiles on the regenerated ISO
      or on first boot; `/usr` must remain read-only, not remounted as a workaround.
- [ ] Confirm installed OSTree deployment uses composefs (mount information)
      and retains Fedora shim/GRUB/kernel Secure Boot trust after an update.
- [ ] Published digest passes BOTH Cosign verification and the installed
      containers/image signature policy. Unsigned/wrong-key update must fail.

## Installer and VM

The installer-specific mount regression test runs the real Anaconda tasks on
disposable tmpfs filesystems (not a disk). After building the installer image,
use its Podman store (`sudo podman` for the rootful image made by `make iso`):

```sh
sudo podman run --rm --network=none --cap-add SYS_ADMIN \
    --entrypoint python3 \
    -v "$PWD/tests/installer-mount-smoke.py:/run/installer-mount-smoke.py:ro" \
    localhost/gniri-installer:latest /run/installer-mount-smoke.py
```

This tests separate home/var and EFI mount ordering, not partitioning, SELinux
labeling, account login or boot. It does not replace the checks below.

The finalizer regression uses real OSTree deployments and BLS entries on tmpfs,
with and without a separate `/boot`. It reproduces the read-only boot failure,
checks that failed writes retain `fstab`, then checks successful migration,
boot-argument readback, repeated console arguments and idempotency:

```sh
sudo podman run --rm --network=none --cap-add SYS_ADMIN \
    --security-opt label=disable --entrypoint python3 \
    -v "$PWD:/src:ro" localhost/gniri-installer:latest \
    /src/tests/installer-finalize-smoke.py
```

The security-label override applies only to this disposable test container's
repository mount; it does not change the installer or installed SELinux mode.

- [ ] Build ISO with the current `image-builder` flow, not a deprecated action.
- [ ] `make iso` completes locally without GitHub credentials or publication;
      embedded development payload installs with networking disconnected.
- [ ] Boot the ISO in UEFI with Secure Boot enabled and Fedora-compatible
      enrolled certificates. Do not substitute public test keys.
- [ ] Installer passes the initial SELinux/PID 1 freeze; SELinux is enabled
      in permissive mode only in the installer. Installed Gniri is Enforcing.
- [ ] Check that Anaconda requires user confirmation for disk changes.
- [ ] Offline installation, account creation, first boot and fresh user login.
- [ ] Btrfs with a separate `home` subvolume: the chosen user's home is on that
      subvolume, exists through BOTH `/home/$USER` and `/var/home/$USER`, has the
      right owner/SELinux label, and remains writable after a reboot. Also test
      a layout without a separate home mount. See [diagnosis and recovery](installer-troubleshooting.md).
- [ ] Installer initramfs has `/.buildstamp`; native UEFI does not request the
      BIOS-only `edd` driver from either Anaconda hook. BIOS support remains.
- [ ] Installer `IsFinal` matches the base's `RELEASE_TYPE`; stable bases do not
      show a forced pre-release label, while development bases retain the warning.
- [ ] The actual Anaconda bootc deployment command includes `--skip-finalize`;
      target `/boot` remains writable through configuration and the finalizer.
- [ ] DHCP, DNS and HTTPS work on the host's libvirt NAT network, not just QEMU
      user networking; verify host firewall rules without disabling protection.
- [ ] OCI payload installs with 4–6 GiB guest RAM and the live overlay's default
      size: no manual remount, RAM-sized layer spool or `container_images_*`
      failures in `/var/tmp`. Measure peak memory; this is not yet a tested minimum.
- [ ] Installed system boots with Secure Boot enabled; `mokutil --sb-state`.
- [ ] Both GDM sessions work and session selection is remembered.
- [ ] Kitty creates a window in both GNOME and Niri; check Niri's user journal
      on a login failure. Container dependency checks do not prove GDM/DRM works.
- [ ] The resolved Fedora release's and GNOME backgrounds appear in GNOME's background chooser.
- [ ] Fresh Niri login uses `/etc/niri/config.kdl`; user Flathub only.
- [ ] An existing `~/.config/niri/config.kdl` takes precedence without copying.
- [ ] Existing configs/Stow links survive login and an image update unchanged.
- [ ] Login still works without Internet; Flathub provisioning retries later.
- [ ] Fresh user Flathub registration succeeds offline with GPG verification;
      no apps or system remotes appear after boot. Container regression:
      `podman run --rm --network=none --entrypoint bash -v "$PWD/tests/flatpak-smoke.sh:/run/flatpak-smoke.sh:ro" localhost/gniri:development /run/flatpak-smoke.sh`.
- [ ] `systemd-remount-fs.service` succeeds after installation. `/etc/fstab`
      must not attempt to remount logical `/` with physical filesystem options;
      the chosen root subvolume/compression/options remain in `rootflags=`.
- [ ] GNOME and Niri: audio, networking, Bluetooth, keyring and polkit prompts.
- [ ] Flatpak file chooser, screen sharing and clipboard work in both sessions.
- [ ] Idle lock and lock-before-suspend work; no unlocked flash after resume.
- [ ] Correct image tag/registry after install; update signature enforcement.
- [ ] Sunday timer and missed-run catch-up stage without restarting the VM.
- [ ] A failed network/signature check records failure; at most four attempts
      occur within two hours. A rollback/source-change/pause is skipped without retry.
- [ ] Manual `gniri-stage-update` uses the immutable strict policy even if the
      caller sets `CONTAINERS_POLICY_JSON`; ordinary Podman/Distrobox pulls still work.
- [ ] Manual reboot enters new deployment; rollback restores previous system.
- [ ] `/home`, libvirt guests and Tailscale state survive update and rollback.
- [ ] Interrupted update/full-disk tests preserve a bootable deployment; backup
      restoration to a different disposable disk works. See [recovery.md](recovery.md).

## Physical AMD workstation

- [ ] RX 9070 XT: amdgpu, RADV/Vulkan, OpenGL, monitors and suspend/resume.
- [ ] `glxinfo -B`, `vulkaninfo --summary`, `vainfo`, `nvtop` and `amd-smi` on real
      AMD/Intel hardware. Verify camera capture and OpenCL device enumeration.
- [ ] Wacom: exact model, USB/Bluetooth, pen pressure, output mapping and buttons
      in both GNOME and Niri; test in the intended note-taking application.
- [ ] Controllers: each USB, Bluetooth and wireless receiver model, Steam Input
      and Proton via a user-installed Steam Flatpak. Xbox proprietary wireless
      adapters may require out-of-tree drivers; they are not silently included.
- [ ] virt-manager: only the authorized account has passwordless system access.
- [ ] x86 KVM guest with NAT, UEFI, virtual TPM and virtio 3D/OpenGL.
- [ ] ARM32/ARM64 guest with TCG and ARM firmware.
- [ ] Deliberately created Ethernet bridge; no network loss. Ordinary Wi-Fi
      station interfaces usually cannot be bridged without additional support.
- [ ] SELinux remains enforcing and firewalld enabled.

The ISO workflow runs manually and uploads 30-day artifacts, not public
releases. Archive reviewed evidence and tested artifacts durably before promotion.
GitHub-hosted runners have limited disk space; measure image/ISO
size before scheduling ISO generation or choosing a larger/self-hosted runner.
