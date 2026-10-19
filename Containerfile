# x86_64 host image; ARM machines are guests, not an additional host variant.
FROM quay.io/fedora/fedora-bootc:44@sha256:36c7c5495537c5b0900affeb5ba3256954de98271e334a41b3159cc7293a21b7

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
ARG SOURCE_URL=""
LABEL containers.bootc="1" \
      org.opencontainers.image.title="Gniri" \
      org.opencontainers.image.description="Minimal GNOME and Niri on Fedora bootc" \
      org.opencontainers.image.source="${SOURCE_URL}"
COPY system_files/ /
COPY trust/ /run/gniri-build/trust/
COPY packages/visible-applications.allow /run/gniri-build/packages/
COPY build/configure-image.py build/validate-image.sh build/finalize-image.py /run/gniri-build/
RUN python3 /run/gniri-build/configure-image.py "${IMAGE_REF}" \
    && bash /run/gniri-build/validate-image.sh \
    && python3 /run/gniri-build/finalize-image.py \
    && bootc container lint --fatal-warnings
