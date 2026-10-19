# Audio, energía, Wi-Fi, VPN y memoria

Gniri incluye soporte para el equipo AMD/Realtek actual y equipos x86_64
modernos de escritorio y portátiles. Conserva el kernel, módulos, firmware y
políticas de audio de Fedora; la compatibilidad física depende del dispositivo.

## Audio y diagnóstico

PipeWire y WirePlumber gestionan audio HDA, HDMI/DisplayPort, USB y Bluetooth.
Se incluyen `alsa-ucm`, `alsa-sof-firmware`, `alsa-utils`, `pipewire-utils` y
`pulseaudio-utils`. Los micrófonos USB y auriculares con cable usan sus drivers
de clase y perfiles; no se fuerzan frecuencia de muestreo, latencia o códecs.
Los complementos Bluetooth incluyen SBC, AAC, LDAC, LC3 y mSBC; su uso depende
del perfil y de lo que negocien los auriculares. Abrir el micrófono de unos
auriculares Bluetooth puede cambiar el perfil y la calidad de reproducción.

Comprobaciones locales sin grabar ni publicar datos:

```sh
wpctl status
pactl list short sinks
pactl list short sources
aplay -l
arecord -l
pw-top
systemctl --user status pipewire.socket pipewire-pulse.socket wireplumber.service
journalctl --user -b -u wireplumber -u pipewire
```

En el respaldo de Niri, `XF86AudioMicMute` silencia el micrófono predeterminado.
Los dotfiles personales conservan prioridad y deben definir sus propios atajos.

## Wi-Fi y OpenVPN

El firmware Realtek, Atheros, Broadcom, MediaTek e Intel MVM se declara
explícitamente. Intel MVM incorpora también su dependencia de firmware Bluetooth.
No se añaden drivers DKMS ni ajustes globales para desactivar ahorro energético.
La configuración de conectividad de Fedora permite detectar redes cautivas.

OpenVPN se gestiona desde **Settings → Network → VPN → + → Import from file**.
Están instalados `NetworkManager-openvpn` y `NetworkManager-openvpn-gnome`.
No se inicia ningún túnel ni se copian certificados o credenciales por defecto.

```sh
nmcli device status
nmcli radio
nmcli connection show --active
bluetoothctl show
rfkill list
journalctl -b -u NetworkManager -u bluetooth
```

Los resultados de red pueden contener nombres de dispositivos o conexiones;
revísalos antes de compartirlos. Las conexiones existentes las conserva
NetworkManager en el estado persistente del equipo.

## Energía

`tuned` y `tuned-ppd` ofrecen los perfiles de ahorro, equilibrado y rendimiento
desde GNOME mediante la API PowerProfiles. La configuración Fedora empieza
en equilibrado y contempla batería; no se imponen parámetros de CPU o batería
específicos de una marca. `tuned-adm active` muestra el perfil TuneD efectivo.
`brightnessctl` y los atajos de brillo del respaldo Niri controlan pantallas
internas compatibles. El brillo de monitores externos requiere otra integración.

## Swap comprimida

Se usa **zram**, con `zram-generator-defaults` de Fedora: tamaño lógico
`min(ram, 8192)` MiB y prioridad 100. La memoria se ocupa conforme se utiliza;
no se reservan 8 GiB de RAM al arrancar. Un fragmento en
`/usr/lib/systemd/zram-generator.conf.d/20-gniri.conf` selecciona **Zstandard
nivel 1**, buscando equilibrio entre compresión y coste de CPU en equipos modernos.
No se afirma que sea el algoritmo más rápido para todas las cargas.

No se crea una partición o archivo swap, ni writeback a disco. No se modifica
`swappiness` ni se configura hibernación. La configuración Fedora del kernel
mantiene zswap desactivado de forma predeterminada; no hace falta comprimir
dos veces las páginas destinadas a zram.

```sh
zramctl
swapon --show
cat /sys/block/zram0/comp_algorithm
systemctl status systemd-zram-setup@zram0.service
```

El algoritmo activo debe aparecer como `[zstd]`. Las personalizaciones del
administrador pueden ponerse en `/etc/systemd/zram-generator.conf.d/90-local.conf`;
para desactivar solo nuestro fragmento, usar un enlace del mismo nombre
`20-gniri.conf` a `/dev/null` en ese directorio. Un archivo principal vacío en
`/etc` no desactiva una sección añadida por un fragmento de proveedor.

Fuentes: [configuración de zram-generator 1.2.1](https://github.com/systemd/zram-generator/blob/v1.2.1/man/zram-generator.conf.md),
[zram en el kernel](https://docs.kernel.org/admin-guide/blockdev/zram.html),
[TuneD y la integración Fedora](https://fedoraproject.org/wiki/Changes/TunedAsTheDefaultPowerProfileManagementDaemon),
[Bluetooth en WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html).
