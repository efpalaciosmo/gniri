#!/usr/bin/env bash
# Run only inside a disposable image with test-only Weston installed.
# No host GPU, display socket, user session or system configuration is used.
set -euo pipefail
[[ -e /run/.containerenv ]]
# GTK needs a session bus even in this isolated headless container.
if [[ -z ${DBUS_SESSION_BUS_ADDRESS:-} ]]; then
    exec dbus-run-session -- bash "$0" "$@"
fi
export XDG_RUNTIME_DIR
XDG_RUNTIME_DIR=$(mktemp -d)
chmod 0700 "$XDG_RUNTIME_DIR"
export HOME="$XDG_RUNTIME_DIR/home"
mkdir -p "$HOME"
export LIBGL_ALWAYS_SOFTWARE=1 WAYLAND_DISPLAY=gniri-test-parent
export GDK_BACKEND=wayland
unset DISPLAY
weston_pid='' niri_pid='' ghostty_pid=''
cleanup() {
    local result=$?
    trap - EXIT
    for pid in "$ghostty_pid" "$niri_pid" "$weston_pid"; do
        if [[ -n $pid ]]; then kill "$pid" 2>/dev/null || true; fi
    done
    if (( result != 0 )); then
        cat "$XDG_RUNTIME_DIR"/*.log 2>/dev/null || true
    fi
    # The disposable container removes these files after terminating remaining
    # compositor children; deleting now races Mesa's asynchronous shader cache.
    exit "$result"
}
trap cleanup EXIT
weston --backend=headless --renderer=gl --socket="$WAYLAND_DISPLAY" \
    --idle-time=0 --no-config --shell=kiosk > "$XDG_RUNTIME_DIR/weston.log" 2>&1 &
weston_pid=$!
for (( attempt=0; attempt<100; attempt++ )); do
    [[ -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]] && break
    kill -0 "$weston_pid"
    sleep 0.1
done
[[ -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]]
# Check the terminal in the parent compositor before testing it under Niri.
timeout 15s ghostty --config-default-files=false --gtk-single-instance=false \
    -e /usr/bin/true > "$XDG_RUNTIME_DIR/ghostty-parent.log" 2>&1
niri --config /etc/niri/config.kdl > "$XDG_RUNTIME_DIR/niri.log" 2>&1 &
niri_pid=$!
export NIRI_SOCKET
for (( attempt=0; attempt<100; attempt++ )); do
    NIRI_SOCKET=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'niri.*.sock' -print -quit)
    [[ -n $NIRI_SOCKET ]] && break
    kill -0 "$niri_pid"
    sleep 0.1
done
[[ -n $NIRI_SOCKET ]]
export WAYLAND_DISPLAY
WAYLAND_DISPLAY=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n')
[[ -n $WAYLAND_DISPLAY && $WAYLAND_DISPLAY != *$'\n'* ]]
ghostty --config-default-files=false --gtk-single-instance=false --class=org.gniri.smoke \
    -e /usr/bin/sleep 30 > "$XDG_RUNTIME_DIR/ghostty-niri.log" 2>&1 &
ghostty_pid=$!
for (( attempt=0; attempt<100; attempt++ )); do
    niri msg --json windows > "$XDG_RUNTIME_DIR/windows.json"
    if python3 -c 'import json, sys; sys.exit(not any(w.get("app_id") == "org.gniri.smoke" for w in json.load(sys.stdin)))' \
        < "$XDG_RUNTIME_DIR/windows.json"; then
        printf 'Ghostty mapped a window in Niri; both also started under headless Weston.\n'
        exit 0
    fi
    kill -0 "$ghostty_pid"
    sleep 0.1
done
printf 'Ghostty did not map a window in Niri.\n' >&2
exit 1
