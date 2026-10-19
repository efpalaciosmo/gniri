# DLT OS: Repository and Architecture Summary

This document is the maintainer-oriented map of this repository. The main
[`README.md`](README.md) explains how to use DLT OS; this file explains what the
project is, how its pieces fit together, how to build it, and what should be
changed when turning it into a different operating-system image.

## 1. What this project is

DLT OS is a customized, image-based Linux distribution built on top of
[Bazzite](https://bazzite.gg/), Fedora, Universal Blue, and
[bootc](https://bootc-dev.github.io/bootc/). Its final system is distributed as
an OCI container image and can also be converted into bootable disk images.

It is **not** an operating system written from scratch: this repository does
not implement a kernel, bootloader, package manager, or libc. Instead, it
assembles an opinionated OS image from an existing Bazzite base by:

- adding and removing RPM packages;
- installing Go, Rust, and Python tools;
- adding system-wide configuration and helper scripts;
- enabling systemd user services;
- rebuilding the initramfs;
- validating the result; and
- publishing signed, updateable container images.

The current image targets systems with NVIDIA GPUs because its base is
`ghcr.io/ublue-os/bazzite-nvidia-open:stable`.

## 2. High-level architecture

```text
Bazzite NVIDIA base image
          |
          v
     Containerfile
          |
          +-- build_files/       Install packages and tools
          +-- system_files/      Overlay files onto the final root filesystem
          +-- validation         Validate niri and lint the bootc image
          |
          v
   OCI/bootc image (dltos)
          |
          +-- GHCR/Forgejo registry publication
          +-- rpm-ostree rechunking for smaller updates
          +-- bootc-image-builder
                  |
                  +-- QCOW2 image
                  +-- raw disk image
                  +-- installer ISO (configuration needs repair; see below)
```

At runtime, bootc/rpm-ostree manages the OS deployment. The system image is
treated as an atomic unit, while users keep mutable data and per-user settings
in their home directories. Updates replace the deployed image rather than
incrementally modifying the host with ordinary package-management commands.

## 3. Repository map

| Path | Purpose |
| --- | --- |
| [`Containerfile`](Containerfile) | Defines the multi-stage OS image build and the order of all customization phases. |
| [`build_files/`](build_files/) | Shell scripts that install software, enable services, rebuild initramfs, and validate the image. |
| [`system_files/`](system_files/) | Root filesystem overlay copied directly into the final image. Paths below this directory become paths below `/`. |
| [`disk_config/`](disk_config/) | bootc-image-builder configuration for disks and installer ISOs. |
| [`Justfile`](Justfile) | Main local build, rechunk, disk-image, VM, lint, and formatting commands. |
| [`dltos.just`](dltos.just) | DLT OS-specific recipes for comparing and importing user configurations. |
| [`image-template.env`](image-template.env) | Image name, organization, description, tags, logo, and builder-image defaults. |
| [`.github/workflows/`](.github/workflows/) | GitHub Actions for building, publishing, signing, and creating disk images. |
| [`.forgejo/workflows/`](.forgejo/workflows/) | Equivalent Forgejo automation. |
| [`cosign.pub`](cosign.pub) | Public key used to verify signed images. The private key must never be committed. |
| [`artifacthub-repo.yml`](artifacthub-repo.yml) | Artifact Hub repository ownership metadata. |
| [`repo_files/`](repo_files/) | Repository-facing assets such as the project logo. |
| [`README.md`](README.md) | User-facing description, switching instructions, features, and software inventory. |
| [`LICENSE`](LICENSE) | Apache License 2.0. |

## 4. Image build sequence

The [`Containerfile`](Containerfile) uses three stages.

### 4.1 Go helper build

The `go_builder` stage compiles `niri-float-sticky`. The resulting binary is
copied to `/usr/bin/niri-float-sticky` in the final image.

### 4.2 Zsh plugin bundle

The `zsh_configs` stage uses Antidote and
[`build_files/zsh_plugins.txt`](build_files/zsh_plugins.txt) to generate one
system-wide Zsh plugin bundle. This avoids cloning plugins separately for every
user at runtime.

### 4.3 Final OS image

The final stage starts from Bazzite NVIDIA Open and runs these phases in order:

1. **Base desktop** — [`build_files/00-base.sh`](build_files/00-base.sh)
   - installs Zsh and Kitty;
   - installs niri, Noctalia, desktop portals, Qt configuration tools, media
     controls, and Wayland utilities;
   - removes unwanted or conflicting software; and
   - currently pins `xwayland-satellite` to a specific build.
2. **Development tooling** —
   [`build_files/10-tooling.sh`](build_files/10-tooling.sh)
   - installs language environments for Go, Rust, Python, and Node.js;
   - installs shell, networking, mail, graphics, document, container,
     development, AI, data, and backup tools;
   - installs some tools using `dnf5`, some with `go install`, some with
     `cargo install`, and others with `uv tool install`; and
   - replaces the Docker executables with wrappers that default to the user's
     Podman socket.
3. **Filesystem overlay** — `COPY system_files /`
   - adds all project-owned system configuration, scripts, service units,
     application defaults, branding, and user tmpfiles rules.
4. **Services** — [`build_files/20-services.sh`](build_files/20-services.sh)
   - applies the required SELinux context to `bat`; and
   - globally enables the `bat-cache-build` and `niri-float-sticky` user
     services.
5. **Branding** —
   [`build_files/30-cosmetics.sh`](build_files/30-cosmetics.sh)
   - changes the inherited Bazzite fastfetch startup configuration to use the
     DLT OS profile.
6. **Boot files** —
   [`build_files/40-initramfs.sh`](build_files/40-initramfs.sh)
   - creates a reproducible, compressed initramfs with ostree and FIDO2
     support.
7. **Validation** —
   [`build_files/50-validations.sh`](build_files/50-validations.sh)
   - validates `/etc/niri/config.kdl`.
8. **Final bootc check** — `bootc container lint`
   - verifies that the resulting container obeys bootc image requirements.

### 4.4 Build caching and compilation performance

Caching is an intentional part of this repository's build design. It combines
container layer caching with a shared `/var/cache` mount, then redirects the
package managers and language build systems into that mount. This allows
expensive downloads and intermediate compilation artifacts to be reused
without storing those temporary files in the final OS image.

#### Shared cache mounts

Each scripted customization `RUN` instruction (`00-base.sh` through
`50-validations.sh`), as well as the initial DNF configuration step, has these
mounts:

```dockerfile
RUN --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/cache/libdnf5 \
    ...
```

These are builder-managed caches, not ordinary image directories:

- their contents can survive the completion of a `RUN` instruction and be
  reused by later instructions and subsequent builds on the same builder;
- their contents are not committed into the resulting image layer;
- downloads and compiler intermediates therefore do not unnecessarily enlarge
  the shipped OS; and
- reuse depends on preserving the container builder's storage. A new or
  cleaned builder starts with empty caches.

The nested `/var/cache/libdnf5` mount gives DNF's cache its own persistent
mount. Early in the final stage, the Containerfile also runs:

```bash
dnf5 config-manager setopt keepcache=1
```

This prevents DNF from deleting downloaded packages after a successful
transaction, making those packages available to later build steps or rebuilds.

#### Language-specific cache placement

The environment scripts copied before `10-tooling.sh` deliberately point build
caches below the mounted `/var/cache` path while placing final executables and
runtime files in the real image filesystem:

| Ecosystem | Cached paths | Persistent output paths | Effect |
| --- | --- | --- | --- |
| Go | `GOPATH=/var/cache/go`, `GOCACHE=/var/cache/go-build` | `GOBIN=/usr/bin` | Reuses downloaded modules and compiled Go objects; installed commands remain in the image. |
| Rust/Cargo | `CARGO_HOME=/var/cache/cargo`, `CARGO_TARGET_DIR=/var/cache/cargo-target` | `CARGO_INSTALL_ROOT=/usr` | Reuses Cargo registry/git data and target artifacts; installed binaries remain below `/usr`. |
| Python/uv | `UV_CACHE_DIR=/var/cache/uv` | Python and tools below `/usr/share/uv`, executables below `/usr/bin` | Reuses uv downloads/build data while keeping installed runtimes and tools in the image. |
| DNF | `/var/cache/libdnf5` and other data below `/var/cache` | RPM-installed files throughout the image | Reuses repository metadata and downloaded RPMs. |

`UV_LINK_MODE=copy` is important because installed uv-managed files must be
real files in the image, not links that point back into a cache mount that will
not exist in the final image.

This design is most useful when `10-tooling.sh` must run again: Go, Cargo, and
uv can reuse previous inputs and compiler results even though the generated
layer itself was invalidated.

#### Container layer reuse

The Containerfile also preserves normal OCI build-layer caching by copying and
running the build phases separately:

```text
copy 00-base.sh       -> run base installation
copy tooling scripts -> run tooling installation
copy system_files/    -> enable services -> cosmetics -> initramfs -> validation
```

For example, changing only `30-cosmetics.sh` should allow the builder to reuse
the expensive base and tooling layers. Changing `10-tooling.sh` invalidates its
tooling layer and everything after it, but does not inherently invalidate the
earlier base-package layer. Changing the base image invalidates the final
stage, so all customization layers may need to run again.

The broad `COPY system_files /` creates one invalidation boundary: changing any
file in that tree causes the service, cosmetics, initramfs, and validation
steps after it to run again. It does not invalidate the earlier base and
tooling installation layers.

#### What is and is not cached

The final-stage package and language caches are comprehensive, but not every
operation has an explicit cache mount:

- `go_builder`, which compiles `niri-float-sticky`, relies on ordinary layer
  reuse; it does not mount Go module or compilation caches;
- `zsh_configs` relies on layer reuse for the Antidote clone and generated
  plugin bundle;
- Alpine intentionally uses `apk add --no-cache`, so it does not preserve an
  APK package cache inside that stage; and
- fetched base images and ordinary image layers use Podman's local container
  storage rather than the `/var/cache` mount.

This distinction matters: a cache mount can still help when a `RUN` layer must
be rebuilt, whereas an ordinary layer cache helps only when that instruction
and all of its inputs remain unchanged.

#### Local builds versus CI

Repeated local builds benefit when they use the same Podman storage and it has
not been pruned. The self-hosted Forgejo runner may obtain the same benefit if
its workspace and container storage persist between jobs.

The GitHub Actions workflow currently does **not** export or restore Podman
layers or cache-mount data between jobs. GitHub-hosted runners are normally
ephemeral, so cache reuse should not be assumed across separate workflow runs.
The cache still avoids committing temporary build data and can be shared
between relevant instructions during one build.

To maximize the current cache design:

1. reuse the same local builder and container-storage location;
2. avoid routine cache/storage pruning unless disk space requires it;
3. order frequently changed files after expensive, stable build steps; and
4. keep final outputs outside `/var/cache`, because cache contents are not part
   of the published image.

Potential future improvements include persistent CI cache import/export,
explicit cache mounts in `go_builder`, and splitting the large tooling step by
ecosystem so unrelated tooling changes invalidate less work. Any such change
should be tested with Podman/Buildah, which is the builder used by the Justfile
and current workflows.

## 5. System configuration model

Everything under [`system_files/`](system_files/) is copied to the equivalent
absolute path in the image. For example:

```text
system_files/etc/zshrc
             -> /etc/zshrc

system_files/usr/bin/tray-launch
             -> /usr/bin/tray-launch
```

Important areas include:

- `/etc/zshrc`, `/etc/zprofile`, and `/etc/zshrc.d/`: the global Zsh
  environment, plugins, aliases, keybindings, and prompt;
- `/etc/niri/` and `/usr/share/niri/defaults/`: niri's system and initial user
  configuration;
- `/etc/environment.d/`: application and desktop environment variables;
- `/etc/systemd/user/`: services enabled for users;
- `/usr/share/user-tmpfiles.d/`: rules that copy default application settings
  into a user's home directory when those settings do not already exist;
- `/usr/share/nvim/defaults/`, `/usr/share/emacs/defaults/`, and similar paths:
  initial editor and application configurations;
- `/usr/bin/docker` and `/usr/bin/docker-compose`: compatibility wrappers that
  direct Docker clients to rootless Podman unless `DOCKER_HOST` is already set;
- `/usr/bin/tray-launch`: waits for KDE's status notifier before launching a
  tray application;
- `/usr/bin/dltsh`: a deprecated Distrobox launcher that now starts the host's
  login Zsh and displays a limited number of migration warnings; and
- `/etc/distrobox/dltos.ini`: a Fedora Toolbox-based test environment matching
  important host tools and shell settings.

The tmpfiles `C` rules are significant: they provide defaults for new users but
do not continually overwrite an existing user's customized files.

## 6. Software included

The exact package list is maintained in the build scripts and should remain the
source of truth. Broadly, the image includes:

- **Desktop:** niri, Noctalia, Kitty, desktop portals, Qt theming, media and
  Wayland utilities;
- **Languages:** Go, Rust/Cargo, Python/uv, Node.js/npm, language servers,
  formatters, and linters;
- **Shell:** Zsh, Antidote, Starship, chezmoi, direnv, zoxide, bat, ripgrep,
  fd, eza, yazi, and monitoring/debugging utilities;
- **Networking:** iperf3, mkcert, netcat, nmap, rclone, HTTPie, and s5cmd;
- **Development:** Neovim, Emacs, Git tools, pre-commit, Ansible, OpenTofu,
  Hugo, and lazygit;
- **Containers:** Podman integration, Docker CLI compatibility, Compose,
  Cosign, and lazydocker;
- **Data:** jq, yq, SQLite, PostgreSQL tools, DuckDB, Miller, csvkit, VisiData,
  gnuplot, and termgraph;
- **Graphics/documents:** ImageMagick, HEIC support, rembg, Pandoc, and TeX;
- **AI and backup:** Ramalama and BorgBackup.

See [`build_files/10-tooling.sh`](build_files/10-tooling.sh) for the current
authoritative list and [`README.md`](README.md) for user-oriented descriptions.

## 7. Local development workflow

### Prerequisites

A typical development host needs:

- Git;
- `just`;
- Podman with permission to build containers;
- `sudo` for bootable disk-image creation;
- `shellcheck` and `shfmt` for shell validation and formatting; and
- KVM support to run the generated image efficiently in a VM.

### Inspect available commands

```bash
just
```

### Validate repository code

```bash
just check   # Check Justfile syntax
just lint    # Run ShellCheck over shell scripts
```

Format shell scripts and Justfiles with:

```bash
just format
just fix
```

### Build the bootc container image

```bash
just build
```

Defaults come from [`image-template.env`](image-template.env), so this builds
`dltos:latest`. A custom local name and tag can be supplied:

```bash
just build localhost/my-os development
```

To rechunk the image for smaller future downloads:

```bash
just ostree-rechunk
```

### Build and run a virtual machine image

```bash
just rebuild-qcow2  # Rebuild the container and create a QCOW2 disk
just run-vm-qcow2   # Run it through the qemux/qemu container
```

Generated artifacts are written below `output/` and are ignored by Git.

The ISO recipes currently refer to a missing `disk_config/iso.toml`; choose and
wire up either `iso-kde.toml` or `iso-gnome.toml` before relying on them. See
[Known gaps](#11-known-gaps-and-maintenance-risks).

### Compare user configuration with image defaults

For supported applications, use recipes such as:

```bash
just diff-niri-user-configs
just import-niri-user-configs
just diff-all-user-configs
```

`diff-*` shows differences. `import-*` copies the current user's files into the
repository, so review the resulting Git diff carefully and make sure it does
not contain credentials or personal data.

## 8. Installation and updates

An existing compatible bootc/Bazzite installation can switch to the published
image with:

```bash
sudo bootc switch ghcr.io/datalabtechtv/dltos:stable
reboot
```

The base image currently expects a supported NVIDIA GPU. After installation,
updates can be applied with:

```bash
sudo bootc upgrade
```

Image signatures can be verified with [`cosign.pub`](cosign.pub). Never commit
the corresponding `cosign.key`; it is explicitly ignored by Git.

## 9. CI, publishing, and release flow

### Container image workflow

The GitHub container workflow runs for pull requests, pushes to `main`, manual
dispatches, and a daily schedule. It:

1. checks out the repository and frees runner disk space;
2. validates Justfile syntax;
3. builds the bootc image;
4. rechunks it using rpm-ostree;
5. generates date, commit, and channel tags;
6. pushes non-PR builds to GHCR; and
7. signs the pushed digest using the `SIGNING_SECRET` repository secret.

The Forgejo workflows serve the same general purpose for a Forgejo-hosted
registry. Renovate and Dependabot configuration help track dependency and
workflow-action updates.

### Disk image workflow

The disk workflow uses bootc-image-builder to produce QCOW2 and Anaconda ISO
artifacts. Manually dispatched builds may upload artifacts to GitHub or, when
configured, to S3 using repository secrets.

Required publishing secrets and settings include the Cosign private key and,
for optional S3 uploads, provider, access key, secret key, region, endpoint,
and bucket values. Secrets belong in the CI platform's secret store, never in
this repository.

## 10. Turning this into your own OS image

Use the following checklist for a fork. Make each change in a focused commit so
that updates from the original project remain easier to merge.

1. **Choose scope and hardware support**
   - Decide whether this remains a Bazzite-based desktop image.
   - Select a base image appropriate for NVIDIA, AMD/Intel, Steam Deck, or a
     general-purpose Fedora Atomic system.
2. **Rename and rebrand**
   - Update every value in [`image-template.env`](image-template.env).
   - Replace logos and fastfetch branding in `repo_files/` and
     `system_files/usr/share/dltos/`.
   - Rename DLT-specific directories, commands, Distrobox names, and text if a
     complete rebrand is desired.
   - Update README badges, links, image references, and Artifact Hub metadata.
3. **Select software intentionally**
   - Edit `build_files/00-base.sh` for desktop packages.
   - Edit `build_files/10-tooling.sh` for developer and user tools.
   - Avoid installing tools merely because the original image included them;
     each package increases image size, build time, and maintenance work.
4. **Own the configuration**
   - Review every file below `system_files/`.
   - Remove personal preferences that should not be system-wide.
   - Keep user defaults under `/usr/share/<app>/defaults` and provision them
     with tmpfiles when users should be able to modify them safely.
5. **Repair and customize installers**
   - Choose KDE or GNOME installer configuration.
   - Replace the template image reference in both ISO TOML files with your
     registry/image.
   - Update Just and CI paths to use the selected file.
6. **Configure distribution**
   - Enable package publishing in the repository settings.
   - Generate a new Cosign key pair and configure the private key as a CI
     secret.
   - Publish only the new public key.
   - Review all GitHub and Forgejo workflows for organization-specific values.
7. **Test before installing on hardware**
   - Run static checks.
   - Build the container image.
   - Build and boot a QCOW2 VM.
   - Test login, networking, updates, rollback, desktop portals, graphics,
     audio, user-default creation, and recovery behavior.
   - Test on non-critical hardware before switching a primary workstation.
8. **Document release policy**
   - Define stable/testing tags, supported hardware, update frequency,
     rollback instructions, security reporting, and a changelog process.

## 11. Known gaps and maintenance risks

These items are visible in the current repository and should be addressed
before treating installer artifacts as production-ready:

1. **Missing ISO configuration path:** the Justfile and GitHub disk workflow
   refer to `disk_config/iso.toml`, but the repository contains only
   `iso-kde.toml` and `iso-gnome.toml`.
2. **Wrong installer target:** both existing ISO configurations switch the
   installed system to `ghcr.io/ublue-os/image-template:latest`, not to DLT OS.
3. **Architecture mismatch:** CI offers an ARM64 disk build, while the
   Containerfile downloads an x86-64-only `zsh-patina` archive and uses a base
   image whose ARM64 support must be confirmed.
4. **Partially floating dependencies:** the project uses tags such as
   `stable`, `latest`, and `master`, plus several unpinned `go install`
   commands. This keeps software fresh but reduces reproducibility and can
   break builds without a repository change.
5. **Limited automated validation:** the build validates the niri config and
   bootc structure, while most application configs and runtime behavior are
   not automatically tested.
6. **Documentation drift:** package versions and installation locations can
   change faster than the manually maintained README. The scripts must be
   treated as authoritative.
7. **Hardware coupling:** the NVIDIA-specific base is inappropriate for many
   systems. Hardware support should be explicit in every release description.

## 12. Should all source code be copied into Markdown?

No. Keeping a second complete copy of the code in this document would:

- duplicate the source of truth;
- become outdated whenever a source file changes;
- make reviews and diffs noisy;
- remove useful syntax, file history, and executable permissions; and
- make this guide unnecessarily large and difficult to navigate.

The preferred documentation pattern is:

- link to the real source file;
- explain its responsibility and how it interacts with other files;
- include only short examples that teach a command, file mapping, or concept;
  and
- use permalinks to a specific commit when documentation must describe an
  immutable historical version.

A generated source archive may be useful for an offline release, but it should
be produced automatically and distributed separately rather than maintained by
hand inside Markdown.

## 13. Suggested next milestones

1. Fix and test one installer ISO path end to end.
2. Complete the rebrand and select the correct hardware/base-image target.
3. Pin externally downloaded tools and verify their checksums.
4. Add automated tests for shell scripts and important configuration files.
5. Add a VM smoke test covering boot, login, networking, and `bootc upgrade`.
6. Define stable and testing release channels.
7. Add contribution, security, and release documentation if the image will be
   used by anyone other than its maintainer.

---

When implementation and documentation disagree, the `Containerfile`, build
scripts, system overlay, and workflows describe what the repository actually
builds. Update this summary whenever those architectural responsibilities or
release paths change.
