# Uso y recuperación

## Aplicaciones y cuentas

GDM ofrece GNOME y Niri, con Niri como preferencia inicial. No se modifica tu
shell de inicio de sesión ni se crean `.zshrc` o configuraciones de Starship.
Para personalizar el escritorio, consulta [dotfiles.md](dotfiles.md).

Flathub se añade como usuario en segundo plano al entrar en la sesión, con
reintentos si no hay Internet. No instala aplicaciones ni bloquea el escritorio.

```sh
flatpak remotes --user
flatpak remotes --system  # Vacío en una instalación nueva.
flatpak install --user flathub ID_DE_LA_APLICACION
sudo tailscale up
```

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
