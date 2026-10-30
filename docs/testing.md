# Pruebas y estado de validación

**Una construcción, checksum o JSON no prueba preparación para producción.**
Cada candidato necesita evidencia propia: revisión Git, digest de payload/base,
SHA-256 de ISO, firmware/certificados de VM y logs revisados. `output/iso/build.json`
registra entradas, pero declara la ISO sin validar. La [promoción](building.md)
requiere evidencia y revisión; los resultados históricos no validan otro HEAD.

## Comprobaciones reproducibles

Desde la raíz del repositorio:

```sh
make check
make build REFRESH=1
make check-desktop
sudo make check-installer  # Tras generar el instalador rootful con make iso.
```

`make check` comprueba sintaxis y ejecuta unittest; usa Niri/ShellCheck/actionlint
si están instalados. CI instala y exige los dos linters. `check-desktop` usa
Weston/software rendering en un contenedor desechable sin GPU/display del host;
confirma una ventana Ghostty en Niri, no GDM, logind, SELinux ni DRM físico.

La construcción comprueba además NSS y ejecuta Bash y `ghostty +version` con
UID sin privilegios. Esto detecta defaults/directorios inaccesibles que los
checks como root pueden ocultar. La instalación del overlay fija permisos sin
importar un `umask 077` del checkout y conserva los de directorios compartidos
de Fedora. Las pruebas de autorización ejecutan el JavaScript polkit con Node.js
si está disponible: cubren administradores locales activos y rechazos por
grupo, sesión o acción ajena. No sustituyen una comprobación de polkit/logind
en un escritorio arrancado.

En Niri, comprueba además que el agente Qt 6 de `polkit-kde` muestre el diálogo
al abrir virt-manager con `qemu:///system`, desde una cuenta sin autorización
libvirt sin contraseña. Prueba autenticación correcta, contraseña incorrecta y
cancelación; repite con configuración personal y tras cerrar/abrir sesión.
No deben aparecer errores de módulos QML ni dos agentes simultáneos. En GNOME,
debe seguir usándose el agente integrado de GNOME Shell. La presencia del
ejecutable y los módulos en la imagen no valida estos flujos interactivos.

El gate de migración debe partir también de una instalación Atomic existente:
registrar cuenta/UID/grupos/shell antes del rebase y comprobarlos después, junto
con acceso al hogar, GDM, ambas sesiones y apertura del terminal como usuario
normal. Una prueba de contenedor o una instalación nueva no valida ese rebase.

`tests/installer-finalize-smoke.py` comprueba además el origen firmado por la API
real de OSTree y su lectura posterior, antes del primer arranque. El gate de
promoción exige `rebase-accounts` además de los logins, Secure Boot y actualización/
rollback. `tests/booted-smoke.py` puede ejecutarse desde cada sesión normal de
una VM instalada para registrar comprobaciones de cuentas, escritorio y origen;
no marca como probados hardware, backup o transiciones que no ejecutó.

`check-installer` ejecuta tareas reales Anaconda/OSTree sobre tmpfs: layouts de
home/var/EFI y `/boot`, readback de argumentos, preservación de `fstab` tras fallo
e idempotencia. No usa particionador ni discos. `label=disable` afecta solo al
contenedor de prueba, no al modo SELinux del sistema instalado. En runners Ubuntu,
el perfil AppArmor predeterminado deniega `mount` incluso con `SYS_ADMIN`;
`apparmor=unconfined` se aplica únicamente a esos dos contenedores desechables.
Se conservan seccomp, el aislamiento de red y el checkout montado en solo lectura;
no se usa `--privileged`, no se montan discos ni se modifica AppArmor del anfitrión.

El [job iso 123245652586](https://github.com/efpalaciosmo/gniri/actions/runs/40812429679/job/123245652586)
generó la ISO, pero falló al crear el fixture de confianza del finalizador: buscaba
`/usr/share/gniri/keys/cosign.pub` en el runtime del instalador, que hereda Fedora,
no el `/usr` del payload. El fixture copia ahora `trust/cosign.pub` del checkout
de solo lectura a su deployment temporal, conservando la política estricta y la
prueba real de origen firmado. No se añade la clave al runtime ni se omiten los
checks previos a publicar el artefacto. `make check` cubre la creación del fixture
sin depender de archivos del runtime; esto no valida por sí solo arranque o firmas.
La reproducción local en un contenedor Fedora 44 con Anaconda 44.30-2, OSTree
2026.4 y kernel 7.2.13 reprodujo el mismo `FileNotFoundError` antes del cambio.
Después pasaron los cuatro layouts de montajes y ambos layouts del finalizador
sin clave en el runtime, sin red y con el checkout de solo lectura. Se usó Docker
para estas regresiones; no se reconstruyó una ISO ni se repitió el workflow remoto.

Regresor Flatpak sin red:

```sh
podman run --rm --network=none --entrypoint bash \
  -v "$PWD/tests/flatpak-smoke.sh:/run/flatpak-smoke.sh:ro" \
  localhost/gniri:development /run/flatpak-smoke.sh
```

CI prueba además el precheck real de políticas offline y el cliente
containers/image contra manifests firmados, sin firma y de clave incorrecta.
El contenedor recibe un authfile temporal de GHCR montado en solo lectura;
los logins del host no se heredan y las credenciales no se incluyen en la imagen.
Un error DNS/autenticación no cuenta como rechazo de firma. El precheck offline
**no** sustituye la prueba de actualización/rechazo con bootc en una VM arrancada.

Antes de publicar, CI ejecuta también una regresión real de transporte, incluso
en pull requests y sin acceso externo. Se puede repetir localmente:

```sh
podman run --rm --network=none --entrypoint python3 \
  -v "$PWD:/src:ro" localhost/gniri:development /src/tests/signature-transport-smoke.py
```

Usa el Skopeo de la imagen Fedora, un registro HTTPS en loopback con autenticación
y claves ECDSA temporales. Reproduce el error original de copiar firmas a un
destino `oci:` y ejecuta `signature-smoke.sh`: acepta la firma confiable, rechaza
unsigned/wrong-key y falla ante manifests ausentes, errores al descargar firmas,
credenciales inválidas o una política debilitada. Comprueba además los digests
del manifest y blobs exportados. `copy --remove-signatures` evita **exportar** las
firmas a OCI (no soportado); `--policy` sigue verificando el origen antes de copiar.
No debe usarse `--insecure-policy` ni cambiar la política instalada para resolverlo.
La regresión sustituye política/clave/auth **solo dentro del contenedor desechable**;
no modifica la imagen original, el host, el firewall ni SELinux. Al salir, `--rm`
elimina esos fixtures. No usa claves de producción ni tokens GitHub y no reemplaza
la prueba GHCR del candidato firmado real ni las pruebas bootc en VM.

### Diagnóstico del fallo de publicación 40430420740

El [job build 121946453172](https://github.com/efpalaciosmo/gniri/actions/runs/40430420740/job/121946453172)
construyó y firmó el candidato, pero falló en `signature-smoke.sh` al copiarlo a
`oci:/var/tmp/signed-policy-test`: `Pushing signatures for OCI images is not supported`.
No fue un fallo de DNF, arranque, SELinux ni verificación Cosign. El inventario del
run registra Fedora 44, `skopeo-1.22.3-1.fc44` y `containers-common-0.67.2-1.fc44`;
la reproducción local con esas mismas versiones falló antes del cambio y pasó
con `--remove-signatures`, conservando los rechazos criptográficos negativos.

Referencias upstream: [skopeo-copy, `--remove-signatures`](https://github.com/containers/skopeo/blob/main/docs/skopeo-copy.1.md),
[verificación de política antes de copiar](https://github.com/containers/image/blob/main/copy/single.go)
y [comprobación de firmas del destino](https://github.com/containers/image/blob/main/copy/sign.go).
La prueba local no certifica que una ejecución posterior de GitHub, la ISO o una
instalación hayan pasado: esos resultados necesitan sus propios logs y evidencia.

El pipeline de construcción de `main` publica únicamente candidatos firmados e
inventarios. Las ISOs se generan y prueban localmente con `make iso-candidate`,
`make iso` o `make iso-published`. El workflow separado `promote.yml` exige el
registro revisado y aprobación en `stable`; no construye otra imagen. Los helpers
de release conservados validan la identidad y bytes de artefactos existentes.
Sus unit tests usan bytes simulados; no crean una release ni validan un arranque.

## Gate por candidato

Esta lista es un inventario, no resultados ya obtenidos:

- [ ] **Imagen:** construcción fresca, checksums upstream, lint fatal, comparación
  de repacking, módulos/firmware, sesiones, fuentes y allowlist. Sin navegador,
  aplicaciones Flatpak ni remotos de sistema. Unidades verificadas sin ciclos;
  `/usr/local/sbin` existe sin errores tmpfiles ni remount de `/usr`.
- [ ] **ISO/offline:** receta actual sin credenciales GitHub, payload OCI y una
  única ISO/checksum/metadatos nuevos. Anaconda pide confirmación de discos,
  crea cuenta y completa primer arranque offline. Mide memoria pico con 4–6 GiB;
  ese rango no es todavía un mínimo garantizado.
- [ ] **Montajes:** prueba home separado y sin separar, además de var/EFI. Hogar
  visible por `/home/$USER` y `/var/home/$USER`, propietario/etiqueta correctos y
  escritura tras reboot. `systemd-remount-fs` correcto, `/` y `/sysroot` de solo
  lectura; opciones físicas conservadas en `rootflags=`. Deployment con composefs.
- [ ] **Arranque seguro:** ISO e instalación arrancan con Secure Boot y certificados
  Fedora (no claves públicas de prueba); repite tras actualización y rollback.
  Instalador SELinux permisivo, destino Enforcing. Initramfs con `.buildstamp`,
  EDD solo BIOS e `IsFinal` acorde con la base; Anaconda conserva `/boot` escribible
  hasta completar configuración mediante `--skip-finalize`.
- [ ] **Ambos escritorios:** login GDM y selección recordada, Ghostty, fondos Fedora,
  portales Flatpak (archivos/pantalla/clipboard), polkit, keyring, red, audio y
  Bluetooth. Login offline, Flathub solo de usuario, sin apps preinstaladas;
  prioridad de dotfiles/Stow y preservación tras actualización.
- [ ] **Bloqueo/hardware:** idle y bloqueo antes de suspensión, sin flash desbloqueado
  al reanudar. AMD/Intel real: OpenGL/Vulkan/VA-API/OpenCL, monitores y suspensión;
  Wi-Fi/Bluetooth/reconexión, USB/audio/micrófono, cámara, Wacom (presión/mapeo/botones)
  y cada mando/receptor/Steam Input. No se asume soporte Xbox externo al kernel.
- [ ] **Confianza/actualización:** digest correcto pasa Cosign **y** la política
  instalada. El helper bootc rechaza unsigned/wrong-key sin cambiar deployments,
  ignora una política insegura del entorno, respeta origen/pausa/rollback y deja
  funcionar Podman/Distrobox. El timer y catch-up preparan sin reiniciar; fallos
  registran estado/reintentos limitados. Reboot manual entra en el nuevo deployment.
- [ ] **Recuperación:** rollback restaura el sistema y preserva hogares, libvirt y
  Tailscale; no se vuelve a preparar el digest defectuoso. Ensaya interrupción,
  disco lleno y restauración de backup solo en discos desechables.
- [ ] **Virtualización/red:** cuenta autorizada es la única con acceso sin contraseña;
  KVM x86 con NAT/UEFI/TPM/virtio 3D y ARM32/64 con TCG/firmware. DHCP/DNS/HTTPS
  funcionan en libvirt NAT, no solo en red QEMU de usuario. Puentes deliberados
  sin perder red; SELinux Enforcing y firewalld activos.

Registra dentro de la VM `mokutil --sb-state`, `getenforce`, `systemctl --failed`,
`bootc status`, `findmnt` y journals pertinentes. No desactives protecciones para
hacer pasar las pruebas. Conserva evidencia duradera/redactada, no solo cachés
locales o artefactos Actions temporales; no marques `pass` sin ejecutar el ensayo.

## Último registro conocido: 2026-10-25

Validación del working tree basado en `fad8ad8`, **no una release**:

- Fedora 44 estable, base x86_64
  `sha256:5e7fcb515bdfbe6e6f83e322ab221eefada34db7d12773a054f2b1b11160cdd6`.
  Bootc 1.17.1, OSTree 2026.4, Niri 26.04 y kernel 7.2.11-200.fc44.
- Pasaron 100 unit tests, Niri, ShellCheck/actionlint, construcción y 14 checks
  lint bootc (un skip upstream). El repacking comparó 92,529 rutas y produjo
  `3c40558200daed66f0c020d32f0ec03dbdb309de2bb84db19f48449c8f85d41a`
  (128 capas; 2,122,506,663 bytes gzip). No implica ahorro garantizado por actualización.
- Pasaron Kitty/Niri anidado, Flathub offline, pausa del updater, unidades y
  regresiones reales tmpfs Anaconda 44.30-2/OSTree. El cliente offline reprodujo
  el error de default inseguro y pasó ese precheck con la política estricta;
  después falló por DNS, como se esperaba sin red.
- **Pendientes:** ISO privilegiada/fresh install, Secure Boot, GDM, hardware,
  actualización/rollback bootc con registro real y restauración de backup.
  No se publicó, firmó ni promovió una imagen. La ISO del 19 de octubre quedó
  intacta y no representa estos cambios. Logs locales: `/tmp/opencode/gniri-*.log`.

Los diagnósticos antiguos y sus detalles permanecen en el historial Git, no como
guías vigentes ni evidencia para futuros candidatos.

## Validación local de las correcciones: 2026-10-28

Working tree basado en `7f18449`, con cambios locales todavía sin publicar:

- `GNIRI_STRICT_CHECKS=1 make check`: 155 tests, 154 aprobados y uno omitido
  por falta de Niri local; ShellCheck/actionlint aprobados. Incluye avance de
  versión Fedora, rechazo de retrocesos, canales, resolución de ISO, preflight
  de rebase y controles de promoción.
- Regresión real de OSTree sobre tmpfs: origen firmado guardado/leído antes
  del arranque, kernel arguments/fstab preservados e idempotencia con `/boot`
  separado y sin separar. Se reprodujo el fallo esperado de `/boot` de sólo
  lectura sin perder `fstab`; no se montaron discos del anfitrión.
- Imagen **derivada para validar configuración**, aplicando los cambios al
  digest `97722614446398e2d5f09917f9fb3700ac04fe293b97fc5ffc04cfd696a686b9`
  ya descargado: validadores de imagen y 14 checks bootc aprobados, un skip
  upstream. Se corrigió la regeneración de tmpfiles para no perder reglas
  anteriores de `/var`. Esto reutiliza paquetes existentes, no equivale a una
  construcción fresca desde el canal Fedora.
- En esa imagen derivada pasaron Flathub de usuario offline, el precheck real
  de política estricta y las regresiones de transporte con aceptación de la
  firma correcta y rechazo de unsigned/wrong-key, errores de firma, auth y
  políticas debilitadas. Los rechazos impresos son resultados negativos esperados.
- El build fresco resolvió `quay.io/fedora/fedora-bootc:latest`, verificó Fedora
  44 estable y alcanzó DNF, pero la política de red bloqueó sus mirrors.
  Cosign/GitHub quedaron bloqueados por los dominios TUF/API. Se guardaron los
  destinos necesarios en el borrador del entorno; no se desactivó verificación.
- **Pendientes:** build fresco e ISO, verificación remota de firmas/protecciones,
  GDM/sesiones arrancadas, migración desde Dakota con cuenta existente, Secure
  Boot, actualización/rollback y hardware. No se promovió ni modificó un tag
  remoto y no se generó un registro de aprobación de producción.
