# Construcción y publicación

## Base y paquetes

El flujo soportado (`make` / `scripts/build-image.py`) resuelve el canal oficial
[`fedora-bootc:latest`](https://quay.io/repository/fedora/fedora-bootc?tab=tags)
a un digest Linux x86_64 en cada construcción. Sigue Fedora estable, no Rawhide:
no hay que editar números de versión. El instalador reutiliza la base grabada
en el payload; no resuelve otro `latest`. Esto no garantiza transiciones sin
mantenimiento ni autoriza degradar una instalación desde una versión más nueva.

`fedora:latest` es un contenedor de aplicaciones, no la base arrancable elegida.
No se fija `:44`, `:45` ni otro número: el siguiente build vuelve a resolver
`quay.io/fedora/fedora-bootc:latest`. Antes de instalar paquetes se verifica
`ID=fedora`, `RELEASE_TYPE=stable` y una versión numérica. Esa versión se conserva
en el label OCI y en `build.json`; las promociones y las actualizaciones la
comprueban para rechazar retrocesos. El paso a la siguiente Fedora se distribuye
cuando el candidato correspondiente supera las pruebas y la revisión de `stable`.

Se conserva OSTree con composefs, raíz física de solo lectura y estado persistente
en `/etc` y `/var`. La cadena firmware → shim → GRUB → kernel es la de Fedora;
no hay UKI propio ni backend composefs nativo. `enabled=yes` no autentica por sí
solo todo el filesystem. La compatibilidad Secure Boot necesita pruebas reales.

Los [manifiestos RPM](../packages/) omiten grupos de escritorio y dependencias
débiles. Los fondos se eligen desde `VERSION_ID`; los lanzadores se validan contra
[su lista](../packages/visible-applications.allow). Tailscale usa su repositorio
oficial; Ghostty usa el COPR `scottames/ghostty`, limitado a ese paquete y con
verificación de firmas RPM. [Las descargas upstream](../build/upstream.env) tienen versión/checksum
fijos. Los RPM siguen repositorios vivos: no hay reproducibilidad bit a bit.

Las transacciones omiten documentación RPM (`tsflags=nodocs`), conservando licencias.
QEMU usa emuladores `-core` y módulos explícitos para KVM x86_64, ARM, SPICE,
OpenGL, audio PipeWire y USB. No instala los metapaquetes que exigen todos los
backends de almacenamiento y todas las interfaces. Del binfmt heredado conserva
ARM/AArch64 para contenedores; elimina emuladores de las otras arquitecturas.
Se conservan firmware, microcódigo y traducciones del escritorio.

## Construcción local

Desde la raíz del repositorio: Linux x86_64, Podman, Make, Python 3, Internet y
espacio para imágenes, cachés y staging de varios GB. La ISO requiere `sudo` y
`flock` (util-linux). No se instala ni se rebasa el sistema del anfitrión.

```sh
make check
make build              # Solo imagen: localhost/gniri:development.
make iso-local          # ISO de desarrollo sin actualizaciones de registro.
make iso                # ISO del stable firmado publicado; necesita Skopeo y Cosign.
```

| Opción | Uso |
| --- | --- |
| `REFRESH=1` | Reejecuta transacciones RPM sin borrar cachés de descarga; usar para releases. |
| `RECHUNK=1` | Activa el repacking validado; CI lo conserva para candidatos firmados. |
| `BUILD_NETWORK=host` | Diagnóstico de DNS en contenedores; reduce aislamiento, no cambia el firewall. |

Los builds locales omiten el repacking por defecto para acelerar iteraciones.
Chunkah se fija por digest y corre sin red. Antes de sustituir la etiqueta se
comprueban lint bootc, configuración OCI, contenido, permisos, propietarios,
enlaces y xattrs. Se admiten el modo raíz 0555 y deduplicación inmutable de `/usr`,
no nuevos aliases de configuración mutable. Las firmas se generan **después**.
No hay ahorro de descarga garantizado; cambiar de layout puede descargar todo.
Para conservar un informe sin sustituir la imagen original:

```sh
python3 scripts/rechunk-image.py localhost/gniri:development \
  --tag localhost/gniri:chunked --output .cache/rechunk-comparison
```

El directorio de salida debe ser nuevo. No limpies Podman entre construcciones
si quieres reutilizar capas y cachés.

## ISO e instalación

`make iso` resuelve `ghcr.io/efpalaciosmo/gniri:stable` a un digest y verifica su
firma antes de generar el instalador. `UPDATE_REF` permite elegir otro
repositorio GHCR terminado en `:stable`. Requiere Skopeo, Cosign y la clave pública
de un checkout confiable; no necesita credenciales si el paquete es público.
Se conservan el origen GHCR y la exigencia de firma desde el primer arranque.

`make iso-local` instala deliberadamente `localhost/gniri:development` y no tiene
actualizaciones de registro. Se reserva para desarrollo; publicar una imagen
posteriormente no cambia el origen de una instalación existente.

Podman de usuario y root tienen almacenes separados: la receta transfiere el
payload por una tubería y exporta un directorio OCI temporal en disco. Anaconda
lee los blobs embebidos directamente, sin reconstruirlos en el `/var/tmp` live.
El instalador está separado del escritorio y usa `image-builder bootc-generic-iso`.
El staging se elimina al terminar y las construcciones ISO concurrentes se bloquean.

Salidas: `output/iso/gniri-x86_64.iso`, `SHA256SUMS` y `build.json`. Los metadatos
registran payload, base, constructor y revisiones del payload/instalador; **no
certifican preparación para producción**. Una ejecución sin una única ISO nueva
no se acepta por encontrar un archivo antiguo.

```sh
(cd output/iso && sha256sum --check SHA256SUMS)
tail -n 80 output/iso-build.log
```

Si no hay log, el fallo ocurrió antes del constructor: revisa Make, Podman o sudo.
Para DNS, compara resolución en anfitrión y contenedor; prueba
`make iso BUILD_NETWORK=host` solo si el anfitrión resuelve correctamente.
No desactives TLS, firmas RPM ni el firewall para resolverlo.

La instalación está diseñada para funcionar sin red; construir sí necesita
descargas. Cuenta, contraseña, discos y particionado se eligen interactivamente:
no hay borrado automático, contraseña predeterminada ni filesystem/cifrado impuesto.
`--bootc-default-fs ext4` es metadato del constructor, no una orden de particionado.
SELinux es permisivo **solo en el instalador**; el destino solicita Enforcing.

## GitHub: configuración inicial

El workflow de imagen necesita los secretos Actions `COSIGN_PRIVATE_KEY` y
`COSIGN_PASSWORD`, además de la clave pública correspondiente en `trust/cosign.pub`.
Conserva las claves existentes; no las regeneres para repetir una construcción.
`GITHUB_TOKEN` lo proporciona Actions con permiso `packages: write`; no necesitas
un PAT para publicar desde CI. Las firmas OCI autentican la imagen y las
actualizaciones; no sustituyen Secure Boot.

En la configuración del paquete GHCR, permite al repositorio acceso Actions de
lectura/escritura. Para descargar un paquete privado, inicia sesión con
`docker login ghcr.io -u OWNER` (o `podman login`) y usa como contraseña un token
clásico con `read:packages`.

Para descargas y actualizaciones sin credenciales, haz público el paquete en
**Package settings → Change visibility → Public**:
`https://github.com/users/OWNER/packages/container/gniri/settings`.
Hacer público el repositorio no hace público el paquete; cambiar la visibilidad
del paquete a pública es irreversible. La API documentada de GitHub no permite
automatizar ese cambio.

Los Actions están fijados por SHA. Dependabot propone sus actualizaciones
semanalmente; Renovate gestiona las imágenes OCI y herramientas fijadas en
scripts. Protege `main` con revisión y checks requeridos de sintaxis/tests e imagen.

## Pipeline de imagen en GHCR

[`.github/workflows/build.yml`](../.github/workflows/build.yml) contiene el job
de candidatos `build`. Se ejecuta por cambios
de código en `main`, por pull requests, manualmente sin parámetros y los sábados
a las **05:00 de Bogotá (10:00 UTC)**. GitHub puede retrasar el inicio programado
durante períodos de alta carga.

```text
PR → build: checks + construcción y regresiones de imagen
main / sábado / ejecución manual → build: checks + construcción y regresiones
                                        → firma por digest → GHCR :latest
                                        → inventarios y tamaños en Actions
```

Las PR no publican ni usan secretos de firma. Desde `main`, el mismo job renueva
las transacciones RPM, construye, repackea y valida Ghostty/Niri, Flatpak y
políticas de firmas. Publica un candidato inmutable
`sha-COMMIT-RUN_ID-ATTEMPT`, lo firma y verifica en GHCR; después actualiza `:latest`
al mismo digest. Este workflow no modifica `stable`, no construye ISOs ni crea Releases.

El resumen incluye el comando de descarga, digest y tamaños. El artefacto
`gniri-candidate-inventory-ATTEMPT` contiene inventarios de paquetes/lanzadores,
metadatos, digest e `image-size.json`: tamaño sin comprimir y bytes gzip de las
capas. Se conserva 30 días; los blobs OCI temporales se descartan tras validarlos.

```sh
docker pull ghcr.io/efpalaciosmo/gniri:latest
# También: podman pull ghcr.io/efpalaciosmo/gniri:latest
```

`:latest` identifica la imagen firmada más reciente. El workflow no actualiza
`:stable`: ese canal requiere evidencia específica revisada y el entorno
protegido `stable`. El workflow manual `promote.yml` valida un registro revisado
de `release-evidence/`, el run exacto de construcción, las firmas de candidato y
stable, la procedencia y la versión de Fedora. El job de publicación necesita
aprobación humana y copia el mismo manifest conservando su digest. Repite las
validaciones tras la aprobación y se detiene si `stable` cambió entretanto.
Las instalaciones que ya siguen `:stable` conservan esa referencia; las de
prueba que siguen `:latest` conservan `:latest`, sin saltar de canal automáticamente.

Las herramientas locales de ISO siguen disponibles. Para crear una ISO de un
candidato publicado y firmado, usa su digest exacto:

```sh
make iso-published REFRESH=1 \
  PAYLOAD_REF=ghcr.io/owner/gniri@sha256:DIGEST \
  TARGET_REF=ghcr.io/owner/gniri:stable
```

El script verifica Cosign antes de descargar el payload y requiere Cosign en el
`PATH` de root. Esa construcción local no promueve el candidato ni publica una
Release. La ISO necesita las [pruebas de arranque e instalación](testing.md).

## Descargar y verificar una Release

Para Releases históricas o preparadas por separado, verifica sus artefactos firmados.
El workflow actual no genera ni publica Releases.
GitHub limita el tamaño de cada asset: las ISOs mayores de 1 GiB se publican en
partes numeradas de hasta 1 GiB. Descarga **todos los assets** de la Release; las
partes individuales no son medios instalables. Usa la clave de un checkout de
confianza obtenido independientemente, no una clave acompañando una descarga sin verificar:

```sh
cosign verify-blob --key /ruta/de/confianza/gniri/trust/cosign.pub \
  --bundle SHA256SUMS.bundle SHA256SUMS
# Solo si hay partes:
cat gniri-x86_64.iso.part-* > gniri-x86_64.iso
sha256sum --check SHA256SUMS
```

El manifiesto firmado cubre ISO reensamblada, partes, metadatos y evidencia.
Verifica antes de escribir medios o instalar. Los enlaces Source code generados
por GitHub no son la ISO.

## Confianza y migración

La política general de contenedores conserva los valores Fedora más la regla
Gniri. El updater usa `/usr/share/gniri/bootc-policy.json`, independiente y con
`default: reject`; el modo estricto de bootc rechaza el default global inseguro
aunque exista una regla firmada por repositorio. Podman/Distrobox no se restringen
fuera del ámbito Gniri. Sigue la [ruta de actualización soportada](usage.md).

Para migrar una instalación local sin confianza de registro, la opción recomendada
es copia/restauración verificada y reinstalación. Una migración in-place exige
ensayo en copia desechable, clave obtenida por canal autenticado/fingerprint
independiente, política temporal root-owned estricta por repositorio con
`sigstoreSigned`/`matchRepository` y `use-sigstore-attachments: true`, verificación
Cosign/containers-image y switch con enforcement. No basta añadir un flag ni
aceptar firmas arbitrarias. La rotación requiere una transición verificable por
la confianza anterior; perder la única clave exige recuperación autenticada.
