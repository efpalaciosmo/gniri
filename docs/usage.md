# Uso y recuperación

## Escritorio y dotfiles

GDM ofrece GNOME y Niri y recuerda la selección de cada usuario. Niri usa
[`/etc/niri/config.kdl`](../system_files/etc/niri/config.kdl) solo si no existe
`$XDG_CONFIG_HOME/niri/config.kdl` o `~/.config/niri/config.kdl`. El respaldo está
en inglés: `Super+Enter` abre Ghostty; `Super+D`, Fuzzel; `Super+Alt+L`, swaylock.
Incluye Waybar/Mako, el agente polkit de KDE (Qt 6) y bloqueo a los cinco
minutos/antes de suspender. GNOME usa su agente integrado en GNOME Shell.

No se copian dotfiles, temas ni scripts personales al entrar; tampoco se cambia
el shell ni se configura Starship automáticamente. Para partir del respaldo:

```sh
mkdir -p ~/.config/niri
cp --no-clobber /etc/niri/config.kdl ~/.config/niri/config.kdl
```

Puedes usar enlaces Stow revisados, no un playbook de instalación de otra distro.
Tu configuración reemplaza el respaldo completo: debe definir también procesos
de inicio y bloqueo. Los archivos personales de versiones antiguas no se borran.

### Agente de autenticación en Niri

Para recibir solicitudes gráficas de contraseña (por ejemplo, al administrar servicios),
tu configuración personal debe iniciar un único agente. Sustituye la línea de
lxpolkit o el bucle que busca el retirado polkit-gnome por:

```kdl
spawn-at-startup "/usr/libexec/kf6/polkit-kde-authentication-agent-1"
```

Si usas `autostart.kdl`, comprueba que tu configuración principal lo incluya.
La imagen debe contener `polkit-kde`; cambiar el checkout no instala paquetes
en un sistema bootc existente. Tras arrancar una imagen que incluya el cambio,
cierra la sesión por completo y vuelve a entrar para no ejecutar dos agentes.
Comprueba `pkexec /usr/bin/true` como usuario normal: si la política
requiere autenticación, debe aparecer el diálogo. No hace falta desactivar
SELinux, cambiar el firewall ni conceder administración sin contraseña.
Para volver temporalmente al agente anterior, arranca el deployment anterior
y restaura su línea de inicio en tus dotfiles.

## Aplicaciones

Flathub se registra como usuario en segundo plano, con descriptor/clave incluidos
y verificados; también se reimportan las claves del remoto oficial existente sin
borrar aplicaciones ni cambiar sus preferencias. No instala aplicaciones ni
modifica un remoto `flathub` con URL personalizada. Una advertencia de metadatos sin red es
esperable. El remoto de sistema debe estar vacío en una instalación nueva.
El repositorio de sistema se inicializa al arrancar, sin añadir remotos ni apps;
así los comandos que consultan ambas instalaciones no encuentran un OSTree vacío.

```sh
flatpak remotes --user
flatpak remotes --system
flatpak install --user flathub ID_DE_LA_APLICACION
# Por ejemplo:
flatpak install --user flathub com.brave.Browser
sudo tailscale up
```

Si falta Flathub, revisa `journalctl --user -b -u gniri-flathub-user.service` y
reinicia esa unidad. Un remoto Fedora heredado no se elimina automáticamente:
comprueba primero `flatpak list --system --columns=application,origin`; solo si
no se usa, retíralo con `sudo flatpak remote-delete --system fedora`, sin `--force`.
Podman/Distrobox no crean ni descargan contenedores hasta solicitarlos.

La imagen no incluye el hipervisor QEMU, libvirt ni virt-manager, no habilita sus sockets ni
concede acceso polkit a máquinas virtuales. Puedes instalar aplicaciones de
virtualización mediante Flatpak; un cliente que dependa de libvirt en el host
no obtiene ese backend automáticamente. Los discos y datos existentes bajo
`/var` no se borran al actualizar.

### Flathub: `Can't check signature: public key not found`

Si `flathub` ya existe, `remote-add --if-not-exists` no repara sus claves.
El fallo de firma impide consultar el catálogo y puede producir después
`No remote refs found`, búsquedas vacías o errores de AppStream. No desactives
la verificación GPG ni borres el remoto o sus aplicaciones.

En una imagen que incluya la reparación, ejecuta como usuario normal:

```sh
gniri-flathub-user
flatpak remote-ls --user flathub --app --columns=application
flatpak update --user --appstream flathub
flatpak install --user flathub com.brave.Browser
```

También puedes reiniciar `gniri-flathub-user.service` y consultar su journal.
En imágenes anteriores que ya incluyan el descriptor verificado, comprueba con
`flatpak remotes --user --columns=name,url` que `flathub` apunta a
`https://dl.flathub.org/repo/` o `https://flathub.org/repo/`, y reimporta sus claves
sin descargar claves de otra fuente:

```sh
python3 - <<'PY' | flatpak remote-modify --user --gpg-verify --gpg-import=- flathub
import base64
import configparser
import sys
config = configparser.ConfigParser(interpolation=None)
with open('/usr/share/gniri/flathub.flatpakrepo') as stream:
    config.read_file(stream)
sys.stdout.buffer.write(base64.b64decode(config['Flatpak Repo']['GPGKey'], validate=True))
PY
```

Repite las consultas anteriores con red disponible. La reparación solo añade
confianza desde el descriptor incluido; no modifica SELinux, firewall ni apps.
Volver al deployment anterior no revierte las claves del hogar del usuario;
no las elimines como limpieza ni reinstales el sistema por este error.

### Error Flatpak `opendir(objects): No such file or directory`

Indica un directorio `/var/lib/flatpak/repo` incompleto. En un sistema antiguo,
cierra GNOME Software y cualquier operación Flatpak antes de ejecutar:

```sh
sudo ostree --repo=/var/lib/flatpak/repo init --mode=bare-user-only
flatpak remotes --system
flatpak list --system
flatpak install --user flathub com.brave.Browser
```

`ostree init` completa el esqueleto sin borrar configuración, remotos, claves
ni aplicaciones existentes. No elimines `/var/lib/flatpak` para repararlo.
En imágenes nuevas revisa también:

```sh
systemctl status gniri-flatpak-system-repo.service
journalctl -b -u gniri-flatpak-system-repo.service
```

## Hardware y diagnóstico

Se conserva la pila Fedora: amdgpu/Mesa, firmware AMD/Intel/Wi-Fi, PipeWire y
WirePlumber. Herramientas instaladas no equivalen a compatibilidad física probada.
La [política de cobertura de hardware](hardware.md) describe los paquetes compartidos
por escritorio/instalador, los checks independientes del equipo y el diagnóstico.

| Área | Comprobaciones |
| --- | --- |
| Gráficos | `glxinfo -B` (Xwayland), `eglinfo`, `vulkaninfo --summary`, `vainfo`, `nvtop`, `amd-smi list` |
| Audio | `wpctl status`, `pactl list short sinks`, `pactl list short sources`, `aplay -l`, `arecord -l` |
| Wi-Fi/red | `nmcli device status`, `nmcli connection show --active`, `journalctl -b -u NetworkManager` |
| Bluetooth | `bluetoothctl show`, `rfkill list`, `journalctl -b -u bluetooth` |
| Energía | `tuned-adm active`; perfiles GNOME mediante TuneD/tuned-ppd |
| Memoria | `zramctl`, `swapon --show`, `cat /sys/block/zram0/comp_algorithm` |
| Inventario/SSD | `lspci -nnk`, `lsusb`, `sudo nvme smart-log /dev/nvme0`, `sudo smartctl -a /dev/nvme0`, `systemctl status fstrim.timer` |

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

### Gniri como invitado en QEMU/KVM (SPICE)

La imagen incluye `spice-vdagent` para integración SPICE y `qemu-guest-agent`
para comunicación con el hipervisor; este último no cambia la resolución.
Fedora inicia los servicios al detectar sus canales virtio. El agente de sesión
SPICE se inicia con `graphical-session.target`, también en Niri desde GDM;
no añadas otro `spawn-at-startup` a tus dotfiles.

Con la VM apagada, configura en el anfitrión:

- Vídeo **Virtio**, pantalla **SPICE** y canal `com.redhat.spice.0` de tipo
  `spicevmc`. Para Niri usa aceleración 3D/OpenGL compatible con el anfitrión.
- Canal de agente QEMU `org.qemu.guest_agent.0` si deseas esa integración.
- En virt-manager/virt-viewer activa **Auto resize VM with window**. Escalar la
  imagen del visor no es lo mismo que cambiar la resolución del invitado.

Arranca una imagen que contenga estos paquetes y prueba redimensionar el visor
en GNOME y Niri. El cambio en el repositorio no instala nada en un deployment
existente: actualiza por el canal firmado habitual y reinicia manualmente.
En Niri evita fijar `mode`/`modeline` para la salida virtual en tus dotfiles si
quieres seguir el modo preferido que anuncia la VM. La disponibilidad de resize
y portapapeles depende del visor, GPU virtual y compositor/Wayland; instalar los
agentes no garantiza todas las funciones en cualquier hipervisor.

Diagnóstico dentro del invitado:

```sh
rpm -q spice-vdagent qemu-guest-agent
ls -l /dev/virtio-ports/
systemctl status spice-vdagentd.socket spice-vdagentd.service qemu-guest-agent.service
systemctl --user status spice-vdagent.service
journalctl -b -u spice-vdagentd.service -u qemu-guest-agent.service
journalctl --user -b -u spice-vdagent.service
niri msg outputs  # Solo dentro de Niri; compara antes/después de redimensionar.
```

Sin los canales correspondientes es normal que los servicios estén inactivos;
no los fuerces a arrancar en hardware físico. No se necesitan puertos de red,
cambios de firewall ni desactivar SELinux. Si hay una regresión, arranca el
deployment anterior sin borrar dotfiles ni datos de la VM.

## Actualizaciones

Solo las instalaciones con origen GHCR publicado tienen actualizaciones; la ISO
local de desarrollo no tiene registro. Los equipos siguen `gniri:stable`, no el
tag base Fedora. El domingo a las 10:00 local se prepara una actualización, con
hasta 30 minutos de retraso. `Persistent=true` recupera ejecuciones perdidas al
encender, sin despertar el equipo. **Nunca se reinicia automáticamente.**

Gniri no queda fijado al número de Fedora instalado: los builds siguen
`quay.io/fedora/fedora-bootc:latest`. Un candidato probado de la siguiente Fedora
se promueve a `stable` sin cambiar tu referencia de actualización. Las máquinas
de pruebas instaladas con `:latest` siguen ese canal explícitamente.
Se rechaza un destino sin versión de Fedora o que anuncie una versión menor
que la arrancada. La comprobación previa de versión no sustituye la firma: el
despliegue sigue verificándose criptográficamente.

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

Las nuevas instalaciones publicadas guardan un origen firmado antes de su primer
arranque. El daemon de rpm-ostree también usa la política estricta independiente,
por lo que `rpm-ostree update` sigue el origen del deployment y verifica sus
firmas. No pasa por la pausa ni por el registro de intentos del helper: esa pausa
controla la tarea automática, no una actualización manual deliberada. No uses
rebase a `latest` como reparación de una instalación antigua: primero compara
versiones, conserva el deployment anterior y ensaya la migración en una copia.
El nuevo código no modifica por sí solo un `stable` antiguo ni una instalación
con origen local.

## Rollback y copias

### Si desaparece la cuenta del login después de un rebase

Antes de una migración nueva, desde el usuario de escritorio existente ejecuta
`python3 scripts/check-rebase.py ghcr.io/efpalaciosmo/gniri:stable` desde un
checkout confiable. Requiere Skopeo, Cosign y Podman. Verifica el digest firmado,
la versión, que la cuenta sea local y que la imagen proporcione su shell y GDM;
no cambia usuarios ni ejecuta el rebase. Que pase el preflight no sustituye la
prueba de migración y recuperación en una copia desechable.

El rebase debe conservar las cuentas locales, sus contraseñas y `/var/home`.
Que GDM no muestre una cuenta o que el terminal no abra no demuestra que los
datos se hayan borrado. Primero arranca el deployment anterior desde GRUB. No
reinstales, recrees el usuario ni cambies UID, propietario o contraseña para
intentar recuperar el escritorio sin identificar el fallo.

Desde la sesión recuperada, comprueba la cuenta y su shell sin mostrar hashes:

```sh
getent passwd "$USER"
id
getent group wheel
rpm-ostree status
journalctl --list-boots
```

Identifica el arranque fallido en la última lista y sustituye `BOOT_ID`:

```sh
sudo journalctl -b BOOT_ID -u gdm.service -u accounts-daemon.service \
  -u systemd-sysusers.service --no-pager -n 100
```

Si puedes acceder a una TTY del deployment afectado (`Ctrl+Alt+F3`), comprueba
allí `getent passwd NOMBRE_USUARIO`, `id NOMBRE_USUARIO`, el ejecutable de shell
indicado y `findmnt /home /var/home`. Una shell personalizada ausente en la
imagen puede impedir abrir sesiones o terminales sin borrar la cuenta. No
ejecutes `authselect --force`, no reemplaces `/etc/passwd` ni hagas `/usr`
escribible como arreglo. Recuperar el login en el deployment anterior permite
investigar sin alterar la cuenta; no garantiza que una imagen nueva ya la repare.

### Autorización de rpm-ostree

Las operaciones habituales de rpm-ostree no solicitan contraseña a un usuario
del grupo `wheel` en una sesión **local y activa**. La regla del escritorio
autoriza únicamente acciones enumeradas de rpm-ostree; no elimina la
autenticación de sudo, de otros servicios ni de sesiones remotas/inactivas.
Si sigue apareciendo una solicitud, guarda el comando exacto y comprueba `id`
y `loginctl session-status` antes de modificar las políticas. El cambio debe
estar incluido en la imagen arrancada; editar el repositorio no cambia una
instalación existente. La validación criptográfica de imágenes se mantiene.

### Preparar un rollback

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
