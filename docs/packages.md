# Paquetes incluidos

La fuente de verdad son los manifiestos, no una segunda lista copiada aquí:

| Manifiesto | Contenido |
| --- | --- |
| [core.txt](../packages/core.txt) | Git, Make, Stow, Podman, Fastfetch, `vi`/`vim`, traceroute, Zsh y utilidades. |
| [desktop.txt](../packages/desktop.txt) | GNOME Shell, GDM, Settings, Files, Software, Keyring, audio, portales y fondos oficiales Fedora/GNOME. |
| [niri.txt](../packages/niri.txt) | Niri, Kitty, Waybar, Fuzzel, Mako, bloqueo, portapapeles y Zathura. |
| [hardware.txt](../packages/hardware.txt) | Kernel/módulos Fedora, firmware AMD/Intel y Wi-Fi moderno, Mesa/RADV, Bluetooth, Wacom, Steam Input, TuneD, OpenVPN y zram. |
| [security.txt](../packages/security.txt) | Módulos PAM U2F/Yubico y `pamu2fcfg`, sin modificar las políticas de inicio de sesión. |
| [virtualization.txt](../packages/virtualization.txt) | QEMU/KVM x86, emulación ARM, libvirt modular, virt-manager, UEFI, TPM virtual y virgl. |

`vi` se mantiene mediante `vim-minimal`; `vim-enhanced` añade `vim`, `vimdiff`
y las funciones completas del editor. El paquete Fedora para `traceroute` se
llama `traceroute`, no `traceruter`.
Fastfetch no existía y se añade sin configuración ni ejecución automática
al abrir la terminal.

`f<VERSION_ID>-backgrounds-gnome`, seleccionado automáticamente desde la base,
incluye el fondo oficial de esa versión Fedora y su registro en
el selector de GNOME; `gnome-backgrounds` aporta la colección estándar. No se
sobrescribe el fondo elegido por el usuario. `dbus-tools` se declara
explícitamente para que `niri-session` pueda actualizar el entorno de activación
D-Bus sin depender de paquetes recomendados.

Tailscale usa su repositorio RPM oficial estable. Starship, zsh-completions y
JetBrainsMono Nerd Font se instalan desde [versiones/checksums fijos](../build/upstream.env).
La fuente conserva todos los pesos de la familia usada, sin duplicar las
variantes NL/Propo/Mono. Instalar un programa no incorpora tus dotfiles.

No se instalan grupos Workstation, dependencias débiles, navegador, extensiones,
Homebrew, COPR ni aplicaciones Flatpak. Los paquetes de drivers, servicios y
firmware no generan iconos adicionales. Los ocho lanzadores aprobados están
en [visible-applications.allow](../packages/visible-applications.allow); la
construcción rechaza adiciones inesperadas. `nvtop` añade el octavo lanzador;
Fastfetch y Vim no añaden iconos.

Cada imagen incluye los inventarios efectivos `packages.txt`,
`desktop-entries.txt` y `visible-applications.txt` en `/usr/share/gniri/`.
GitHub Actions los publica como artefactos para revisar dependencias y menús.

Los perfiles ALSA UCM, firmware SOF y herramientas ALSA/PipeWire completan el
audio. `pulseaudio-utils` aporta `pactl`, sin instalar otro servidor de audio.
OpenVPN incluye el backend NetworkManager y el editor GNOME. El idioma sigue
siendo inglés. Véase [hardware.md](hardware.md) para uso y límites de validación.

La pila gráfica y de vídeo AMD/Intel, OpenCL, herramientas de diagnóstico,
cámara, reglas udev y compatibilidad se declaran explícitamente: no dependen de
recomendaciones RPM. Se mantienen los paquetes Fedora/Cisco solicitados
`libheif`, `openh264` y el plugin GStreamer OpenH264; **no** se añade RPM Fusion
ni FFmpeg completo/códecs freeworld al host. Las aplicaciones Flatpak obtienen
sus códecs y controladores de espacio de usuario desde sus propios runtimes y
extensiones; el kernel y firmware siguen siendo del host.
