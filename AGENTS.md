# Repository Guidelines

## Project Structure & Module Organization

Gniri builds a Fedora 45 bootc desktop with GNOME and Niri. The root `Containerfile` defines the OS image; `installer/` contains the Anaconda installer and target finalization logic. `build/` installs packages, configures the image, and validates its contents. `packages/*.txt` groups RPM dependencies, while `packages/visible-applications.allow` controls desktop launchers. `system_files/` mirrors installed filesystem paths for configuration, services, and runtime commands. `scripts/` handles checks, OCI repacking, and ISO generation. Tests live in `tests/`, documentation in `docs/`, and generated ISOs in `output/iso/`.

## Build, Test, and Development Commands

Run commands from the repository root. Image builds require Linux x86_64, Podman, Make, Python 3, network access, and sufficient disk space.

- `make check`: run source checks and Python unit tests.
- `make build`: run checks, build `localhost/gniri:development`, and repack OCI layers; produces an image only.
- `make check-desktop`: after building, verify Kitty maps a window in nested Niri inside a disposable headless container.
- `make iso`: build the local image and generate `output/iso/gniri-x86_64.iso`; requests sudo for privileged build operations.
- `make build RECHUNK=0`: skip layer repacking for diagnosis.

## Coding Style & Naming Conventions

Follow surrounding code: four-space indentation for Python and Bash blocks, and tabs for Make recipes. Use descriptive snake_case Python names, hyphenated script filenames, and the `gniri-` prefix for installed commands and services. Bash scripts use `#!/usr/bin/env bash` and `set -euo pipefail`. Keep fallback Niri configuration in English. `scripts/check.py` checks Python/Bash syntax and runs ShellCheck and Niri validation when installed; no automatic formatter is configured.

## Testing Guidelines

Use standard-library `unittest`: name files `tests/test_*.py` and methods `test_*`. Add regression coverage for behavioral fixes. Run `make check` before submitting. No numeric coverage threshold is configured. Installer smoke tests and VM release gates are documented in `docs/testing.md`; container checks alone do not establish boot readiness.

## Commit & Pull Request Guidelines

History uses concise imperative subjects, such as “Reduce peak disk usage while exporting the installer ISO.” Follow that style. Describe the problem, resulting behavior, and validation in each PR; link relevant issues and identify untested VM or hardware scenarios. Update affected documentation.

## Security & Configuration

Commit only public signing material under `trust/`; keep private keys and credentials out of Git. Preserve Fedora Secure Boot trust, installed SELinux Enforcing, signed update verification, and user-owned dotfiles.
