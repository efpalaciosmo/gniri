# Uso y recuperación

## Escritorio y dotfiles

GDM ofrece GNOME y Niri y recuerda la selección de cada usuario. Niri usa
[`/etc/niri/config.kdl`](../system_files/etc/niri/config.kdl) solo si no existe
`$XDG_CONFIG_HOME/niri/config.kdl` o `~/.config/niri/config.kdl`. El respaldo está
en inglés: `Super+Enter` abre Ghostty; `Super+D`, Fuzzel; `Super+Alt+L`, swaylock.
Incluye Waybar/Mako, agente polkit y bloqueo a los cinco minutos/antes de suspender.

No se copian dotfiles, temas ni scripts personales al entrar; tampoco se cambia
el shell ni se configura Starship automáticamente. Para partir del respaldo:

```sh
mkdir -p ~/.config/niri
cp --no-clobber /etc/niri/config.kdl ~/.config/niri/config.kdl
```

Puedes usar enlaces Stow revisados, no un playbook de instalación de otra distro.
Tu configuración reemplaza el respaldo completo: debe definir también procesos
de inicio y bloqueo. Los archivos personales de versiones antiguas no se borran.

## Aplicaciones y virtualización

Flathub se registra como usuario en segundo plano, con descriptor/clave incluidos
y verificados; no instala aplicaciones. Una advertencia de metadatos sin red es
esperable. El remoto de sistema debe estar vacío en una instalación nueva.

```sh
flatpak remotes --user
flatpak remotes --system
flatpak install --user flathub ID_DE_LA_APLICACION
sudo tailscale up
```

Si falta Flathub, revisa `journalctl --user -b -u gniri-flathub-user.service` y
reinicia esa unidad. Un remoto Fedora heredado no se elimina automáticamente:
comprueba primero `flatpak list --system --columns=application,origin`; solo si
no se usa, retíralo con `sudo flatpak remote-delete --system fedora`, sin `--force`.
Podman/Distrobox no crean ni descargan contenedores hasta solicitarlos.

```sh
sudo gniri-setup-virtualization "$USER"
# Cierra la sesión por completo y vuelve a entrar.
virsh -c qemu:///system list --all
```

Esto concede **administración elevada del anfitrión** a una cuenta local mediante
libvirt/polkit y activa NAT. Seleccionar otra cuenta sustituye la autorización
sin contraseña anterior. Para 3D: Virtio con aceleración y SPICE/OpenGL local.
ARM32/64 usa TCG; x86 usa KVM. Los puentes se crean deliberadamente; una interfaz
Wi-Fi en modo estación normalmente no admite un puente Ethernet convencional.

## Hardware y diagnóstico

Se conserva la pila Fedora: amdgpu/Mesa, firmware AMD/Intel/Wi-Fi, PipeWire y
WirePlumber. Herramientas instaladas no equivalen a compatibilidad física probada.

| Área | Comprobaciones |
| --- | --- |
| Gráficos | `glxinfo -B` (Xwayland), `eglinfo`, `vulkaninfo --summary`, `vainfo`, `nvtop`, `amd-smi list` |
| Audio | `wpctl status`, `pactl list short sinks`, `pactl list short sources`, `aplay -l`, `arecord -l` |
| Wi-Fi/red | `nmcli device status`, `nmcli connection show --active`, `journalctl -b -u NetworkManager` |
| Bluetooth | `bluetoothctl show`, `rfkill list`, `journalctl -b -u bluetooth` |
| Energía | `tuned-adm active`; perfiles GNOME mediante TuneD/tuned-ppd |
| Memoria | `zramctl`, `swapon --show`, `cat /sys/block/zram0/comp_algorithm` |

OpenVPN: Settings → Network → VPN → Import from file. No se inicia ningún túnel
ni se incluyen credenciales. Bluetooth negocia perfiles/códecs según el equipo;
usar el micrófono puede reducir calidad de reproducción. Revisa también
`journalctl --user -b -u wireplumber -u pipewire` ante fallos de audio.

Zram usa `min(ram, 8192)` MiB, prioridad 100 y `zstd(level=1)`; no reserva toda esa
RAM al arrancar. No se configura swap de disco, writeback ni hibernación. Los
ajustes locales van en `/etc/systemd/zram-generator.conf.d/`; un enlace
`20-gniri.conf` a `/dev/null` allí desactiva solo el fragmento Gniri.

No se fuerzan variables gráficas globales ni se relajan permisos de `/dev/dri`.
VA-API, OpenCL y las métricas AMD dependen de la GPU; no se incluye ROCm completo.
Los códecs/runtimes Flatpak son independientes del host; no hay RPM Fusion ni
promesa de H.264/HEVC acelerado que Fedora excluya. Las reglas OpenRGB/Solaar no
instalan sus GUI. Las herramientas U2F/Yubico no cambian PAM/authselect ni exigen
llave para entrar. Adaptadores Xbox propietarios pueden necesitar drivers externos.
Revisa nombres de conexiones y datos sensibles antes de compartir diagnósticos.

## Actualizaciones

Solo las instalaciones con origen GHCR publicado tienen actualizaciones; la ISO
local de desarrollo no tiene registro. Los equipos siguen `gniri:stable`, no el
tag base Fedora. El domingo a las 10:00 local se prepara una actualización, con
hasta 30 minutos de retraso. `Persistent=true` recupera ejecuciones perdidas al
encender, sin despertar el equipo. **Nunca se reinicia automáticamente.**

```sh
gniri-stage-update --status
sudo gniri-stage-update
systemctl list-timers bootc-fetch-apply-updates.timer
journalctl -u bootc-fetch-apply-updates.service
```

Usa este helper, no `bootc upgrade` directamente: selecciona la política estricta
y comprueba origen, rollback y pausa. Los fallos se reintentan cada 15 minutos,
con límite de cuatro intentos dentro de dos horas; las omisiones deliberadas no.
El resultado, última comprobación correcta y digest preparado se guardan en
`/var/lib/gniri/updates/status.json`. Un éxito no demuestra que el nuevo escritorio
funcione. No hay notificación gráfica: revisa el estado si falla la comprobación
semanal. GNOME Software gestiona aparte las aplicaciones Flatpak.

## Rollback y copias

```sh
sudo systemctl disable --now bootc-fetch-apply-updates.timer
sudo systemctl stop bootc-fetch-apply-updates.service
sudo install -D -m 0644 /dev/null /etc/gniri/updates-paused
sudo bootc rollback
# Reinicia manualmente cuando hayas cerrado tu trabajo.
```

También puedes elegir el deployment anterior en GRUB o usar una TTY si falla GDM.
Tras arrancar una versión antigua, detén timer y servicio: puede no conocer el
marcador nuevo. No prepares otra vez el digest fallido. Cuando haya uno validado,
retira deliberadamente `/etc/gniri/updates-paused`, ejecuta
`sudo systemctl reset-failed bootc-fetch-apply-updates.service` y habilita el timer.

**Rollback no restaura datos mutables.** Antes de migrar o actualizar:

- Verifica un destino separado/cifrado con `findmnt`/`lsblk`; guarda una copia fuera
  del equipo y prueba descifrado/restauración en otro disco o VM.
- Copia hogares/dotfiles, datos Flatpak/containers y estado necesario de servicios
  bajo `/var/lib` (puede contener secretos). Revisa `/etc` selectivamente; no lo
  sobrescribas completo al restaurar. Detén servicios o usa backups consistentes.
- Apaga las VM antes de copiar discos e incluye pools personalizados, XML,
  TPM y NVRAM; copiar una VM activa no garantiza consistencia.
- Preserva propietarios, ACL, xattrs y enlaces; GNU tar admite
  `--acls --xattrs --selinux --numeric-owner`. Usa `umask 077`, verifica checksums
  y prueba archivos, enlaces Stow, VM y SELinux Enforcing tras restaurar.

Si GRUB falla, usa un medio Fedora firmado de recuperación sin formatear discos.
Si falta espacio, identifica `/boot`, `/var` y raíz con `df`, `du` y `findmnt`:
no borres `/ostree` ni `/sysroot`, ni hagas `/usr` escribible como arreglo.

## Problemas conocidos del instalador

| Síntoma | Diagnóstico y precaución |
| --- | --- |
| `container_images_*: no space left on device` | Una ISO antigua puede reconstruir capas en el overlay live; regenera la ISO con payload OCI, no aumentes RAM/remountes `/run` como solución. El mínimo de RAM sigue pendiente de medición. |
| `systemd-remount-fs` / `overlay: No changes allowed in reconfigure` | El finalizador migra opciones físicas a `rootflags=` y guarda `fstab.gniri-before-rootflags`; no borres la entrada `/` de una instalación antigua sin verificar `root=`/`rootflags=` y tener copia. |
| `mkdir(boot/loader.0): Read-only file system` | Anaconda necesita `--skip-finalize` hasta completar configuración. Regenera el instalador; no hagas escribible permanentemente el sistema instalado. |
| `.buildstamp` / `edd` en UEFI | La receta genera metadatos e initramfs y solicita EDD solo en BIOS. `IsFinal` describe la base, no certifica preparación de Gniri. |
| DHCP falla con enlace activo | Comprueba leases/NAT y logs del firewall del anfitrión; que funcione con red de usuario QEMU no prueba `virbr0`. Limita cualquier permiso a DHCP/DNS/routing del puente; no desactives el firewall. |

Las nuevas ISO no reparan automáticamente instalaciones antiguas. `/home` enlaza
a `/var/home`; una regresión de Anaconda podía crear la carpeta bajo un montaje
que luego la ocultaba. Para ese caso, primero copia el disco con la VM apagada.
Desde una TTY del usuario afectado **dentro de Gniri**, no en el anfitrión:

```sh
sudo install -d -m 0700 /mnt/gniri-var
sudo mount --bind /var /mnt/gniri-var
sudo ls -ld "/mnt/gniri-var/home/$USER" /var/home
```

El bind debe ser **no recursivo**. Continúa solo si el origen es el hogar esperado
y el destino no existe; no sobrescribas ni borres el origen:

```sh
sudo test ! -e "/var/home/$USER" && \
    sudo cp -a --update=none-fail "/mnt/gniri-var/home/$USER" /var/home/
sudo restorecon -RF "/var/home/$USER"
sudo umount /mnt/gniri-var
```

Verifica usuario, propietario, montaje y escritura antes de volver a GDM. Si no
coinciden esas condiciones, detente: no improvises con `rm`, `usermod` ni permisos 777.


Ghostty es el terminal predeterminado. `Super+Enter` abre una ventana en el home;
los ajustes personales de Ghostty y del shell siguen en tus dotfiles. En bootc,
`/home` enlaza a `/var/home`: ambas rutas son normales. El perfil del sistema
normaliza el directorio lógico al iniciar un shell interactivo que ya esté en
el home para que el prompt pueda mostrar `~`; no cambia directorios de proyectos.
Si el prompt personal conserva colores o saltos extraños, revisa que sus códigos
ANSI estén delimitados con `\[` y `\]` en Bash (o `%{` y `%}` en Zsh).
