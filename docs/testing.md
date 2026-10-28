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

`check-installer` ejecuta tareas reales Anaconda/OSTree sobre tmpfs: layouts de
home/var/EFI y `/boot`, readback de argumentos, preservación de `fstab` tras fallo
e idempotencia. No usa particionador ni discos. `label=disable` afecta solo al
contenedor de prueba, no al modo SELinux del sistema instalado.

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

El pipeline de `main` genera después la ISO del digest firmado y adjunta un
`validation.json` con checksum, revisión y run/intento exactos, **sin marcar ensayos
como aprobados**. Usa ese archivo para la evidencia revisada. La promoción descarga
la ISO probada y rechaza otros bytes, metadatos, runs fallidos o procedentes de PR/forks.
Los unit tests prueban estas guardas y el particionado/reensamblado de assets con
bytes simulados; no crean por sí solos una release ni validan un arranque.

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
