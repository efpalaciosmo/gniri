IMAGE ?= localhost/gniri:development
UPDATE_REF ?= ghcr.io/efpalaciosmo/gniri:stable
SOURCE_URL ?=
BUILD_NETWORK ?=
RECHUNK ?= 0
REFRESH ?= 0
CHECKED ?= 0
SOURCE_REVISION ?= $(shell git describe --always --dirty --abbrev=40)

.PHONY: help check check-desktop check-installer build iso iso-local iso-published iso-candidate
help:
	@echo 'make check  - static checks and unit tests'
	@echo 'make check-desktop - test Ghostty windows and nested Niri in a disposable headless container'
	@echo 'sudo make check-installer - test real Anaconda/OSTree tasks in a built rootful installer'
	@echo 'make build  - build the Podman image only (does not create an ISO)'
	@echo 'make build REFRESH=1 - resolve latest stable Fedora and rerun RPM transactions'
	@echo 'make iso    - create an installer from the verified published stable image'
	@echo 'make iso-local - development-only installer; no registry updates'
	@echo 'make iso-candidate PAYLOAD_REF=ghcr.io/owner/gniri@sha256:... - test a signed candidate on latest'
	@echo 'make iso BUILD_NETWORK=host - use host networking if container DNS is failing'
	@echo 'make iso-published PAYLOAD_REF=ghcr.io/owner/gniri@sha256:... TARGET_REF=ghcr.io/owner/gniri:stable'

check:
	python3 scripts/check.py
	python3 -m unittest discover -s tests -v

check-desktop: $(if $(filter 1,$(CHECKED)),,check)
	podman build $(if $(strip $(BUILD_NETWORK)),--network="$(BUILD_NETWORK)") --build-arg "IMAGE=$(IMAGE)" -f tests/desktop.Containerfile -t localhost/gniri-desktop-test:validation .
	podman run --rm --network=none localhost/gniri-desktop-test:validation

check-installer:
	podman run --rm --network=none --cap-add SYS_ADMIN --security-opt label=disable --entrypoint python3 -v "$(CURDIR):/src:ro" localhost/gniri-installer:latest /src/tests/installer-mount-smoke.py
	podman run --rm --network=none --cap-add SYS_ADMIN --security-opt label=disable --entrypoint python3 -v "$(CURDIR):/src:ro" localhost/gniri-installer:latest /src/tests/installer-finalize-smoke.py

build: check
	python3 scripts/build-image.py "$(IMAGE)" --reference "$(IMAGE)" --source "$(SOURCE_URL)" --revision "$(SOURCE_REVISION)" --network "$(BUILD_NETWORK)" $(if $(filter 1,$(REFRESH)),--fresh)
	@if [ "$(RECHUNK)" = 1 ]; then python3 scripts/rechunk-image.py "$(IMAGE)"; fi
	@echo 'Development image ready: $(IMAGE). For its local installer use make iso-local (no registry updates).'

iso: check
	bash scripts/build-published-iso.sh '$(UPDATE_REF)' '$(BUILD_NETWORK)' '$(REFRESH)'

iso-local:
	@echo 'DEVELOPMENT ONLY: this installer has no registry update origin.'
	$(MAKE) build IMAGE=localhost/gniri:development
	GNIRI_BUILD_NETWORK="$(BUILD_NETWORK)" GNIRI_REFRESH="$(REFRESH)" bash scripts/build-local-iso.sh

iso-published: check
	sudo bash scripts/build-iso.sh '$(PAYLOAD_REF)' '$(TARGET_REF)' '$(BUILD_NETWORK)' '$(REFRESH)'

iso-candidate: check
	sudo bash scripts/build-iso.sh '$(PAYLOAD_REF)' '$(patsubst %:stable,%:latest,$(UPDATE_REF))' '$(BUILD_NETWORK)' '$(REFRESH)'
