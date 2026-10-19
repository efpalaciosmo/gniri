# Paquetes incluidos

La fuente de verdad son los manifiestos, no una segunda lista copiada aquí:

| Manifiesto | Contenido |
| --- | --- |
| [core.txt](../packages/core.txt) | Git, Make, Stow, Podman, Fastfetch, `vi` (`vim-minimal`), Zsh y utilidades. |
| [desktop.txt](../packages/desktop.txt) | GNOME Shell, GDM, Settings, Files, Software, Keyring, audio, portales y fondos oficiales Fedora 45/GNOME. |
| [niri.txt](../packages/niri.txt) | Niri, Kitty, Waybar, Fuzzel, Mako, bloqueo, portapapeles y Zathura. |
| [hardware.txt](../packages/hardware.txt) | Kernel/módulos Fedora, firmware AMD, Mesa/RADV, Bluetooth, Wacom y Steam Input. |
| [virtualization.txt](../packages/virtualization.txt) | QEMU/KVM x86, emulación ARM, libvirt modular, virt-manager, UEFI, TPM virtual y virgl. |

`vi` ya está en la base mediante `vim-minimal`; se mantiene explícito para
garantizar que siga disponible. No se añade otro editor ni `vim-enhanced`.
Fastfetch no existía y se añade sin configuración ni ejecución automática
al abrir la terminal.

`f45-backgrounds-gnome` incluye el fondo oficial de Fedora 45 y su registro en
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
firmware no generan iconos adicionales. Los siete lanzadores aprobados están
en [visible-applications.allow](../packages/visible-applications.allow); la
construcción rechaza adiciones inesperadas. Fastfetch y vi no añaden iconos.

Cada imagen incluye los inventarios efectivos `packages.txt`,
`desktop-entries.txt` y `visible-applications.txt` en `/usr/share/gniri/`.
GitHub Actions los publica como artefactos para revisar dependencias y menús.
