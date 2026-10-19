# Test-only compositor: never install Weston in the distributed Gniri image.
ARG IMAGE=localhost/gniri:development
FROM ${IMAGE}
RUN dnf5 -y --disable-repo=tailscale-stable --setopt=install_weak_deps=False install weston
COPY tests/desktop-smoke.sh /run/desktop-smoke.sh
ENTRYPOINT ["bash", "/run/desktop-smoke.sh"]
