# x86_64 desktop image.
ARG BASE_IMAGE=quay.io/fedora/fedora-bootc:latest@sha256:1543ba2788ee2055e0d44a8d879c79a2f527326600eca95a5f673414a48ff73c
FROM ${BASE_IMAGE}

# Frequently changed defaults are copied AFTER the expensive RPM transaction.
COPY packages/*.txt /run/gniri-build/packages/
COPY build/install-packages.sh /run/gniri-build/install-packages.sh
RUN --mount=type=cache,target=/var/cache/libdnf5,sharing=locked \
    bash /run/gniri-build/install-packages.sh

COPY build/upstream.env build/install-upstream.sh /run/gniri-build/
RUN --mount=type=cache,target=/var/cache/gniri,sharing=locked \
    bash /run/gniri-build/install-upstream.sh

# Metadata must not invalidate the expensive package/download layers.
ARG IMAGE_REF=localhost/gniri:development
ARG FEDORA_VERSION
ARG SOURCE_URL=""
ARG SOURCE_REVISION="unknown"
ARG BASE_IMAGE
LABEL containers.bootc="1" \
      org.opencontainers.image.version="${FEDORA_VERSION}" \
      org.opencontainers.image.title="Gniri" \
      org.opencontainers.image.description="Minimal GNOME and Niri on Fedora bootc" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"
COPY system_files/ /run/gniri-build/system_files/
COPY trust/ /run/gniri-build/trust/
COPY packages/visible-applications.allow /run/gniri-build/packages/
COPY build/configure-image.py build/configure-rpm-ostree.py build/signature-policy.py build/validate-image.sh build/validate-hardware.py build/validate-accounts.py build/finalize-image.py build/normalize-boot.py build/install-system-files.py /run/gniri-build/
RUN python3 /run/gniri-build/install-system-files.py /run/gniri-build/system_files \
    && python3 /run/gniri-build/configure-rpm-ostree.py \
    && python3 /run/gniri-build/configure-image.py "${IMAGE_REF}" "${BASE_IMAGE}" "${SOURCE_REVISION}" "${FEDORA_VERSION}" \
    && bash /run/gniri-build/validate-image.sh \
    && python3 /run/gniri-build/normalize-boot.py \
    && python3 /run/gniri-build/finalize-image.py \
    && bootc container lint --fatal-warnings
