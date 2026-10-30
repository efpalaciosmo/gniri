# Cobertura de hardware y diagnóstico

## Política general

Gniri es una imagen x86_64 de propósito general, no una configuración para un
equipo, placa o GPU concretos. Se conserva el kernel firmado de Fedora y sus
paquetes de módulos y firmware, sin recortarlos según los dispositivos presentes
en la máquina que construye o prueba la imagen.

`packages/hardware-platform.txt` se instala explícitamente tanto en el escritorio
como en el instalador. El escritorio instala además `packages/hardware.txt`.
Mover un paquete entre esos manifiestos no lo elimina de la imagen: el build
del escritorio lee **todos** los archivos `packages/*.txt`.

Las dependencias débiles están deshabilitadas, por lo que la cobertura de firmware
se solicita explícitamente:

- AMD e Intel: gráficos, microcódigo y audio, incluido SOF y firmware Intel VSC.
- Wi-Fi/Bluetooth Intel: firmware MVM, MLD y Bluetooth, incluyendo las familias
  nuevas que Fedora separa en paquetes distintos.
- Redes Atheros/Qualcomm, Broadcom, MediaTek (`mt7xxx-firmware` y
  `mediatek-firmware`), Realtek, NXP, TI y firmware Qualcomm WWAN.
- Firmware NVIDIA para los drivers upstream. **No** se incluye el driver
  propietario NVIDIA; el soporte gráfico efectivo depende de GPU, kernel y Mesa.
- `linux-firmware`, firmware de audio Cirrus y la base regulatoria Wi-Fi firmada.
- `kernel-core`, `kernel-modules` y `kernel-modules-extra`, sin listas reducidas
  de módulos por fabricante o modelo.

Se mantienen `NetworkManager` y `NetworkManager-wifi`, Mesa, PipeWire y
WirePlumber. Incluir firmware no garantiza todos los dispositivos de una marca:
también hacen falta drivers upstream y, según la función, integración de usuario.
Por ejemplo, firmware WWAN o de cámara no equivale por sí solo a soporte completo
de cualquier módem o cámara de portátil.

## Qué comprueba el build

`build/validate-hardware-platform.py` consulta los paquetes instalados usando el
propio manifiesto compartido, verifica que existen kernels y comprueba su soporte
genérico de microcódigo y firmware comprimido, además de la base regulatoria.
No lee `/sys` ni `/proc`, no consulta el hardware del anfitrión, no carga módulos
y no exige identificadores PCI/USB, códecs, familias de CPU ni blobs de GPU
específicos. Las divisiones o renombrados de módulos por chip no son una interfaz
fija de Gniri.

Los checks del escritorio comprueban también bibliotecas, servicios e integración
de audio/red/gráficos e invitados virtuales. Son comprobaciones del contenido de
la imagen, **no una certificación de compatibilidad física**. El inventario real
de cada build se guarda en `/usr/share/gniri/packages.txt`.

Las pruebas físicas deben cubrir equipos diversos, incluyendo AMD e Intel,
distintos fabricantes de red, NVMe/SATA, portátiles y sobremesas. Registra cada
resultado con el digest y checksum del artefacto según [las pruebas de release](testing.md).
No conviertas el inventario de un equipo en requisitos globales del build.

## Diagnóstico en un sistema instalado

```sh
cat /usr/share/gniri/build.json
uname -r
lspci -nnk
lsusb
nmcli device status
iw reg get
bluetoothctl show
wpctl status
lsblk -d -o NAME,MODEL,TRAN,SIZE,ROTA
systemctl status fstrim.timer
fwupdmgr get-devices
getenforce
systemctl is-active firewalld
sudo journalctl -b -k --grep='firmware|drm|wifi|nvme|microcode|Hardware Error'
```

Usa `vulkaninfo --summary`, `glxinfo -B` y `vainfo` en la sesión gráfica para
comprobar aceleración. `ethtool -i INTERFAZ` identifica el driver Ethernet;
`sudo nvme smart-log DISPOSITIVO` y `sudo smartctl -a DISPOSITIVO` consultan salud
de almacenamiento. Sustituye los marcadores según `nmcli`/`lsblk` y revisa logs
e identificadores antes de compartirlos. No ejecutes formateos ni flasheos como
prueba de compatibilidad.

`fstrim.timer` utiliza la programación Fedora para TRIM periódico. No se inicia
un daemon SMART adicional ni se desactivan globalmente ASPM, APST, ahorro Wi-Fi
o autosuspend Bluetooth. No se fuerza el país Wi-Fi ni variables globales de GPU.
Los ajustes locales requieren problemas reproducibles; no hay que desactivar
SELinux ni abrir puertos para estos diagnósticos.

Prueba arranque de ISO, instalación offline, Secure Boot, GNOME y Niri,
aceleración, audio/micrófono, periféricos, reconexión de red y suspensión/reanudación
en cada equipo. `fwupdmgr get-devices` no garantiza actualizaciones LVFS para
todos los dispositivos; consulta siempre el fabricante y la revisión exacta
antes de actualizar firmware.

## Recuperación

Ante una regresión, arranca el deployment anterior y conserva logs. Los cambios
del repositorio requieren un nuevo build probado y la actualización firmada
habitual; no modifican por sí solos un sistema instalado. Para anular TRIM
periódico localmente: `sudo systemctl disable --now fstrim.timer`; para restaurarlo:
`sudo systemctl enable --now fstrim.timer`.
