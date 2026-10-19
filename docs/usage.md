# Uso y recuperación

## Aplicaciones y cuentas

GDM ofrece GNOME y Niri, con Niri como preferencia inicial. No se modifica tu
shell de inicio de sesión ni se crean `.zshrc` o configuraciones de Starship.
Para personalizar el escritorio, consulta [dotfiles.md](dotfiles.md).

Flathub se añade **como usuario** en segundo plano al entrar en la sesión.
El descriptor oficial y su clave GPG van dentro de la imagen, verificados por
SHA-256: registrar el remoto no requiere descargar el descriptor al iniciar.
Flatpak puede advertir que no puede actualizar metadatos sin red; eso no impide
que el remoto quede registrado. No se instalan aplicaciones ni se bloquea el
escritorio. El aprovisionador de remotos Fedora del RPM queda enmascarado.

```sh
flatpak remotes --user
flatpak remotes --system  # Vacío en una instalación nueva.
flatpak install --user flathub ID_DE_LA_APLICACION
sudo tailscale up
```

El comando es `flatpak remotes --user`, no `flatpak --remotes`. Si falta Flathub:

```sh
systemctl --user status gniri-flathub-user.service
journalctl --user -b -u gniri-flathub-user.service
systemctl --user restart gniri-flathub-user.service
```

Las instalaciones anteriores pueden conservar el remoto de sistema `fedora`;
no se borra automáticamente porque podría tener aplicaciones del usuario.
Revisar primero `flatpak list --system --columns=application,origin`. Solo si
ya no se usa, retirarlo deliberadamente con
`sudo flatpak remote-delete --system fedora` (sin `--force`).

Distrobox está incluido junto a Podman. No se crean contenedores ni se descargan
imágenes automáticamente: `distrobox create` necesita red para obtener su imagen
si todavía no está en el almacén local.

## Virtualización

Autoriza deliberadamente una cuenta local:

```sh
sudo gniri-setup-virtualization "$USER"
```

Añade la cuenta a `libvirt`, establece una regla polkit específica y activa
la red NAT. Cierra la sesión por completo y vuelve a entrar; comprueba
`virsh -c qemu:///system list --all` sin `sudo`. Es un permiso elevado de
administración del anfitrión. Seleccionar otra cuenta sustituye la autorización
sin contraseña anterior.

Para 3D: vídeo **Virtio con aceleración 3D** y pantalla **SPICE con OpenGL**,
local. ARM sobre AMD usa emulación TCG, más lenta que KVM. Los puentes se
crean explícitamente con NetworkManager; no se cambia tu conexión de red.

## Hardware, VPN y memoria

OpenVPN está integrado en Settings → Network → VPN, con importación de archivos
de configuración. GNOME ofrece perfiles de energía mediante TuneD/tuned-ppd.
La swap zram usa el tamaño adaptable Fedora, hasta 8 GiB, con Zstandard nivel 1;
no necesita partición swap. Para audio USB/Bluetooth y las herramientas de
diagnóstico, consulta [hardware.md](hardware.md).

## Actualizaciones

Las ISO creadas con `make iso` contienen una imagen local de desarrollo:
no descargan actualizaciones de un registro inexistente. El calendario que
sigue se aplica al instalar una imagen publicada con un origen GHCR válido.

`bootc-fetch-apply-updates.timer` prepara actualizaciones **cada domingo a las
10:00, hora local**, con hasta 30 minutos de retraso aleatorio. Se eliminan
los disparadores por arranque y por intervalos del timer original. No hay
comprobación diaria. `Persistent=true` recupera una ejecución perdida cuando
el equipo vuelva a encenderse, aunque ya no sea domingo; no lo despierta.

Primero se exige la política de firmas de Gniri. `bootc upgrade` prepara el
nuevo despliegue para el siguiente reinicio **decidido por ti**. No se usa
`--apply`, reinicio automático, soft reboot automático ni `systemd-sysupdate`.
Elegir frecuencia semanal retrasa la recepción de correcciones respecto a la
frecuencia diaria; siempre puedes actualizar manualmente.

```sh
bootc status
systemctl list-timers bootc-fetch-apply-updates.timer
journalctl -u bootc-fetch-apply-updates.service
sudo bootc upgrade  # No reinicia.
```

GNOME Software gestiona aparte las actualizaciones de aplicaciones Flatpak.
El timer del sistema no reinicia tus máquinas virtuales.

## Rollback

```sh
sudo systemctl disable --now bootc-fetch-apply-updates.timer
sudo bootc rollback
# Reinicia manualmente cuando hayas cerrado tu trabajo.
```

También puedes elegir el despliegue anterior en GRUB. Mantén el timer
desactivado hasta resolver el fallo para que no prepare de nuevo la versión
problemática. Al resolverlo: `sudo systemctl enable --now bootc-fetch-apply-updates.timer`.
