IMAGE ?= localhost/gniri:development
SOURCE_URL ?=
BUILD_NETWORK ?=

.PHONY: help check check-desktop build iso iso-local iso-published
help:
	@echo 'make check  - static checks and unit tests'
	@echo 'make check-desktop - test Kitty windows and nested Niri in a disposable headless container'
	@echo 'make build  - build local development image with Podman'
	@echo 'make iso    - build a local development ISO; no account or publication required'
	@echo 'make iso BUILD_NETWORK=host - use host networking if container DNS is failing'
	@echo 'make iso-published PAYLOAD_REF=ghcr.io/owner/gniri@sha256:... TARGET_REF=ghcr.io/owner/gniri:stable'

check:
	python3 scripts/check.py
	python3 -m unittest discover -s tests -v

check-desktop: check
	podman build $(if $(strip $(BUILD_NETWORK)),--network="$(BUILD_NETWORK)") --build-arg "IMAGE=$(IMAGE)" -f tests/desktop.Containerfile -t localhost/gniri-desktop-test:validation .
	podman run --rm --network=none localhost/gniri-desktop-test:validation

build: check
	podman build $(if $(strip $(BUILD_NETWORK)),--network="$(BUILD_NETWORK)") --layers --build-arg "IMAGE_REF=$(IMAGE)" --build-arg "SOURCE_URL=$(SOURCE_URL)" -t "$(IMAGE)" .

iso: iso-local

iso-local:
	$(MAKE) build IMAGE=localhost/gniri:development
	GNIRI_BUILD_NETWORK="$(BUILD_NETWORK)" bash scripts/build-local-iso.sh

iso-published: check
	sudo bash scripts/build-iso.sh '$(PAYLOAD_REF)' '$(TARGET_REF)' '$(BUILD_NETWORK)'
