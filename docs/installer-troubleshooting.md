# Carpeta personal y red en la VM

## `/home/efrain` y `/var/home/efrain`

En esta imagen `/home -> var/home`. Las dos rutas son válidas y deben llevar a
la misma carpeta persistente. No hay que cambiar `$HOME` ni convertir `/home`
en un directorio del sistema inmutable.

Se confirmó un error de **Anaconda 44.30-2** en la instalación Btrfs: desmontaba
el subvolumen `home` al preparar el destino y no lo enlazaba al despliegue bootc
antes de crear usuarios. La cuenta y su carpeta se creaban, pero el montaje de
`home` desde `fstab` ocultaba esa carpeta al reiniciar. El subvolumen visible
quedaba vacío. Esto también provoca errores de aplicaciones al guardar su estado.

La receta de Fedora 44 aplicó las partes de preservación y enlace de montajes de la
[corrección upstream #7220](https://github.com/rhinstaller/anaconda/pull/7220),
manteniendo la lista de puntos de montaje admitidos por Fedora 44. No impone
particiones, crea cuentas al iniciar sesión ni cambia los dotfiles del usuario.
Si cambia el código upstream esperado, la construcción falla para revisarlo.
Fedora 45 ya contiene la corrección upstream de `home`; se comprueba esa
implementación y solo se ajusta el orden del montaje padre `/boot` frente a EFI.

**Para nuevas instalaciones:** ejecutar `make iso` y probar la ISO regenerada
en otro disco virtual. Actualizar solamente el payload no repara una instalación
ya afectada por el instalador anterior.

### Recuperar la instalación afectada, sin reinstalar

Hacer primero una copia del disco virtual con la VM apagada. Después, dentro de
**Gniri instalado**, cerrar la sesión gráfica y entrar en una TTY. Estos comandos
son para el caso confirmado: usuario `efrain`, subvolumen visible vacío y carpeta
original todavía presente bajo el montaje. No ejecutarlos en el anfitrión.

```sh
sudo install -d -m 0700 /mnt/gniri-var
sudo mount --bind /var /mnt/gniri-var
sudo ls -ld /mnt/gniri-var/home/efrain /var/home
```

El bind **no recursivo** permite ver el directorio oculto sin desmontar el home
activo ni hacer escribible `/usr` o `/sysroot`. Continuar solo si el origen es
la carpeta esperada y `/var/home/efrain` no existe:

```sh
sudo test ! -e /var/home/efrain && \
    sudo cp -a --update=none-fail /mnt/gniri-var/home/efrain /var/home/
sudo restorecon -RF /var/home/efrain
sudo umount /mnt/gniri-var
```

No se borra el origen ni se sobrescriben archivos existentes. Si las condiciones
no coinciden, no improvisar con `rm`, `usermod` o permisos `777`. Comprobar después:

```sh
getent passwd efrain
readlink -f /home/efrain
findmnt -T /var/home/efrain
stat -c '%U:%G %a %n' /var/home/efrain
```

Volver a iniciar sesión y comprobar que se pueden crear archivos. La reparación
manual anterior está documentada, no aplicada a la VM original por el agente.

## La tarjeta aparece pero falla la conexión

En el caso investigado, NetworkManager detectaba `enp1s0`, encontraba enlace e
iniciaba DHCP, pero agotaba 45 segundos sin concesión (`ip-config-unavailable`).
La red libvirt `default` tenía DHCP configurado, pero ninguna concesión.
En el anfitrión estaba activo UFW y había bloqueos registrados en `virbr0`.

Una copia del **mismo sistema instalado**, arrancada con la red de usuario de
QEMU en lugar de `virbr0`, consiguió DHCP, DNS y HTTPS con SELinux Enforcing.
Esto localiza el fallo en la ruta de red del anfitrión/libvirt, no en paquetes
DHCP ausentes ni en la necesidad de desactivar SELinux dentro de Gniri.

Dentro de la VM:

```sh
nmcli device status
nmcli --fields GENERAL,IP4,DHCP4 device show
journalctl -b -u NetworkManager --no-pager
```

En el **anfitrión**, con la VM encendida:

```sh
virsh -c qemu:///system net-dhcp-leases default
sudo ufw status verbose
sudo nft list ruleset
sudo tcpdump -ni virbr0 'udp port 67 or udp port 68'
```

Si se confirma que UFW bloquea esa red, permitir solo DHCP/DNS del puente y su
salida enrutada. Ejemplo para la red observada `192.168.122.0/24`, puente
`virbr0` y salida `wlan0` (**comprobar los valores antes de aplicarlo**):

```sh
sudo ufw allow in on virbr0 proto udp from any port 68 to any port 67
sudo ufw allow in on virbr0 proto udp from 192.168.122.0/24 to 192.168.122.1 port 53
sudo ufw allow in on virbr0 proto tcp from 192.168.122.0/24 to 192.168.122.1 port 53
sudo ufw route allow in on virbr0 out on wlan0 from 192.168.122.0/24
```

No desactivar el firewall ni abrir el forwarding global. Otra opción de prueba
es una NIC de usuario con `passt` en virt-manager, sin el puente NAT. No se ha
modificado automáticamente el firewall ni la configuración de la VM original.
Véase la [documentación de firewall de libvirt](https://libvirt.org/firewall.html).

El fallo DNS durante la **construcción** tiene además evidencia directa en el
anfitrión: UFW registró paquetes DNS bloqueados de `podman0` hacia `wlan0`
(`SRC=10.88.0.3`, `DPT=53`). `make iso BUILD_NETWORK=host` evita esa ruta aislada
para construir; no cambia la red de la VM ni sus reglas de firewall.

## `systemd-remount-fs.service` al abrir la terminal

El mensaje de la terminal lo muestra el ayudante de estado de Fedora: el
servicio falló durante el arranque, no al ejecutar el shell. El diario confirmó
`overlay: No changes allowed in reconfigure` al intentar remontar `/`.

Con composefs, `/` es la raíz lógica inmutable; el Btrfs/ext4 físico está en
`/sysroot`. Anaconda escribía en `fstab` una entrada de `/` con opciones del
disco físico. Añadir `ro` no basta para evitar ese intento de reconfiguración.

La nueva ISO ejecuta un finalizador **durante la instalación**: conserva las
opciones físicas (subvolumen, compresión, etc.) en `rootflags=` mediante OSTree,
mantiene el resto de argumentos del kernel y retira solo la entrada de `/` de
`fstab`. Guarda `fstab.gniri-before-rootflags`. Si falla actualizar el arranque,
no retira la entrada y Anaconda informa del error. `/boot`, EFI, `/home`, `/var`
y swap permanecen intactos. No se enmascara el servicio ni se hace escribible
composefs. Véanse [bootc](https://bootc-dev.github.io/bootc/bootc-installation.7.html#finding-and-configuring-the-physical-root-filesystem)
y [el problema upstream](https://bugzilla.redhat.com/show_bug.cgi?id=2332319).

Una ISO nueva no repara automáticamente el `fstab` de la instalación anterior.
No borrar a mano su entrada de `/` sin comprobar primero `root=` y todas sus
opciones en `rootflags=` y tener una copia del disco.

### Error fatal `mkdir(boot/loader.0): Read-only file system`

El error ocurre antes de retirar la entrada de `/` de `fstab`, por lo que
también explica que el fallo de remount reaparezca en esa instalación.
`bootc install to-filesystem` finaliza la raíz física **y `/boot`** en solo
lectura por defecto. Anaconda aún debe configurar el destino y ejecutar los
scripts de instalación; su tarea de montajes reabría la raíz pero no `/boot`.
La transacción OSTree no podía crear la siguiente generación del cargador.

La integración ahora pasa `--skip-finalize` a esa llamada de bootc: Anaconda
conserva el control de los montajes hasta terminar la configuración y el
desmontaje final. Es la interfaz de bootc para instaladores externos, no un
cambio del modo de montaje del sistema instalado. El finalizador relee las
entradas de arranque guardadas y comprueba las opciones físicas y los demás
argumentos antes de retirar la entrada de `fstab`. Un error de escritura o de
verificación sigue deteniendo la instalación y conserva esa entrada.

Véase la [implementación de instalación de bootc](https://github.com/bootc-dev/bootc/blob/main/crates/lib/src/install.rs).

## «PRE-RELEASE / TESTING» en la pantalla de instalación

El instalador es **Anaconda**, no Calamares. Ese texto procede de `IsFinal` en
`/.buildstamp`; la receta anterior imponía `False`, independientemente de la
base usada. Ahora se generan `Version` e `IsFinal` desde `VERSION_ID` y
`RELEASE_TYPE` de la base Fedora instalada: `stable` produce `True`; una base
de desarrollo o sin esa información conserva el aviso. Los mismos metadatos
se incluyen en el entorno instalador y en su initramfs. No se altera el código
de la interfaz para esconder avisos.

La base se resuelve ahora desde el canal estable oficial y se fija por digest
para el payload y el instalador. `RELEASE_TYPE=stable` explica la etiqueta que
generará Anaconda; no certifica que Gniri haya completado su
[validación de publicación](testing.md). Véase [la política del canal](releases.md).

## Discos mostrados por Fastfetch

Varias rutas no equivalen a varios discos físicos. En bootc es normal ver una
raíz composefs/overlay de solo lectura, la raíz física en `/sysroot`, bind mounts
de `/var` y subvolúmenes Btrfs para `home`. Los subvolúmenes comparten capacidad;
no hay que sumar los tamaños repetidos. La ISO montada también puede aparecer
como medio de solo lectura. Esto no demuestra por sí solo un error de disco.

Para revisar el caso concreto hacen falta la salida de Fastfetch y los montajes:

```sh
fastfetch --structure Disk
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
findmnt -T /
findmnt -T /sysroot
findmnt -T /var/home
```

Las capturas recibidas en esta revisión muestran el fallo de systemd y los
remotos Flatpak, pero no el apartado de discos de Fastfetch.

## Avisos tempranos del instalador

- **`.buildstamp missing`:** el flujo genérico no ejecuta Lorax, que normalmente
  genera ese archivo. Ahora la receta proporciona los metadatos de Gniri tanto
  al entorno instalador como a su initramfs.
- **`could not insert 'edd': No such device`:** `edd` exporta información de
  discos del BIOS heredado; no corresponde al arranque UEFI nativo. Los dos
  hooks de Anaconda lo solicitan ahora solo bajo BIOS. No se ocultan los demás
  errores de `modprobe` ni se elimina el módulo para instalaciones BIOS.

Estas correcciones requieren regenerar la ISO. No demuestran por sí solas que
el sistema esté listo para sustituir el equipo principal: sigue siendo necesario
validar instalación, ambas sesiones, Secure Boot, actualización y rollback.

Fuentes adicionales: [sistema de archivos bootc](https://bootc-dev.github.io/bootc/bootc-filesystem.7.html),
[generación de `.buildstamp` en Lorax](https://github.com/rhinstaller/lorax/blob/master/src/pylorax/buildstamp.py)
y [controlador EDD del kernel](https://github.com/torvalds/linux/blob/master/drivers/firmware/edd.c).
