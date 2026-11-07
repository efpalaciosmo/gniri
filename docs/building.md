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
`packages/hardware-platform.txt` se instala tanto en el escritorio como en el
instalador; ambos validan paquetes e infraestructura del kernel sin acceder al
hardware anfitrión ni exigir modelos o blobs de dispositivos concretos.
La [política de hardware](hardware.md) distingue estos checks de las pruebas físicas.

La finalización elimina el marcador temporal `/run/systemd/systemd-units-load`
y su directorio si queda vacío. No borra contenido desconocido de `/run/systemd`:
`bootc container lint --fatal-warnings` sigue siendo obligatorio.

Las transacciones omiten documentación RPM (`tsflags=nodocs`), conservando licencias.
No se incluye la pila de virtualización del host: QEMU, libvirt, virt-manager,
firmware de invitados ni TPM virtual. También se retiran emuladores QEMU/binfmt
heredados de la base; Podman/Distrobox siguen disponibles para la arquitectura nativa.
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

`make iso` resuelve `quay.io/efpalaciosmo/gniri:stable` a un digest y verifica su
firma antes de generar el instalador. `UPDATE_REF` permite elegir otro
repositorio Quay.io terminado en `:stable`. Requiere Skopeo, Cosign y la clave pública
de un checkout confiable; no necesita credenciales si el paquete es público.
Se conservan el origen Quay.io y la exigencia de firma desde el primer arranque.

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
Las firmas OCI autentican la imagen y las actualizaciones; no sustituyen Secure Boot.
GitHub sigue alojando el código, Actions y los artefactos ISO; las imágenes y sus
firmas se publican en **Quay.io**. `GITHUB_TOKEN` no autentica en Quay.

1. Crea el repositorio **público** `quay.io/NAMESPACE/gniri` en tu usuario u
   organización de Quay. Su visibilidad es independiente de la del repositorio GitHub.
   Las instalaciones necesitan lectura anónima para actualizarse; no se incluyen
   credenciales de CI en la imagen ni en la ISO.
2. Crea un robot en Quay y concédele **Write** sobre ese repositorio, para publicar
   imágenes, firmas y fixtures negativos de la prueba de políticas.
3. En GitHub → **Settings → Secrets and variables → Actions**, añade los secretos
   `QUAY_USERNAME` (nombre completo `NAMESPACE+ROBOT`) y `QUAY_TOKEN` (token del robot).
   No uses el login de GitHub ni un PAT. Los tres workflows usan estas credenciales;
   generar una ISO no necesita la clave privada de firma.
4. Si el namespace de Quay difiere del propietario GitHub en minúsculas, añade la
   variable Actions `QUAY_NAMESPACE`. Todos los workflows y las herramientas de
   promoción/release resuelven `quay.io/NAMESPACE/gniri` con la misma regla.
   Para herramientas locales, exporta `QUAY_NAMESPACE`; para `make iso`, usa
   `UPDATE_REF=quay.io/NAMESPACE/gniri:stable` si no es el namespace predeterminado.

Conserva `COSIGN_PRIVATE_KEY`, `COSIGN_PASSWORD` y `trust/cosign.pub`; cambiar de
registro no requiere rotar la clave. No configures las credenciales Quay solo en
el entorno `stable`: también las necesitan el build y la validación previa a la
aprobación. Las PR no reciben estos secretos. El helper `scripts/setup-github.py`
comprueba su presencia, pero no crea robots ni cambia la configuración de Quay.
Para una descarga privada manual, usa `docker login quay.io -u 'NAMESPACE+ROBOT'`
(o `podman login`) con un token de lectura como contraseña; esto no configura las
credenciales del updater instalado.

Los Actions están fijados por SHA. Dependabot propone sus actualizaciones
semanalmente; Renovate gestiona las imágenes OCI y herramientas fijadas en
scripts. Protege `main` con revisión y checks requeridos de sintaxis/tests e imagen.

## Pipeline de imagen en Quay.io

[`.github/workflows/build.yml`](../.github/workflows/build.yml) contiene el job
de candidatos `build`. Se ejecuta por cambios
de código en `main`, por pull requests, manualmente sin parámetros y los sábados
a las **05:00 de Bogotá (10:00 UTC)**. GitHub puede retrasar el inicio programado
durante períodos de alta carga.

```text
PR → build: checks + construcción y regresiones de imagen
main / sábado / ejecución manual → build: checks + construcción y regresiones
                                        → firma por digest → Quay.io :latest
                                        → inventarios y tamaños en Actions
```

Las PR no publican ni usan secretos de firma. Desde `main`, el mismo job renueva
las transacciones RPM, construye, repackea y valida Ghostty/Niri, Flatpak y
políticas de firmas. Publica un candidato inmutable
`sha-COMMIT-RUN_ID-ATTEMPT`, lo firma y verifica en Quay.io; después actualiza `:latest`
al mismo digest. Este workflow no modifica `stable`, no construye ISOs ni crea Releases.

El resumen incluye el comando de descarga, digest y tamaños. El artefacto
`gniri-candidate-inventory-ATTEMPT` contiene inventarios de paquetes/lanzadores,
metadatos, digest e `image-size.json`: tamaño sin comprimir y bytes gzip de las
capas. Se conserva 30 días; los blobs OCI temporales se descartan tras validarlos.

```sh
docker pull quay.io/efpalaciosmo/gniri:latest
# También: podman pull quay.io/efpalaciosmo/gniri:latest
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

### Generar una ISO desde GitHub

El workflow manual [Build installer ISO](../.github/workflows/iso.yml) genera una
ISO desde una imagen Quay.io ya firmada, sin reconstruir el escritorio, publicar una
Release ni modificar `latest` o `stable`:

1. Publica primero una imagen con **Build and publish image**. El robot de Quay debe
   tener acceso al repositorio de imagen; `trust/cosign.pub` debe corresponder
   a la firma. No se necesitan secretos de firma para generar la ISO.
2. Abre **Actions → Build installer ISO → Run workflow**.
3. Elige `stable` (predeterminado) o `latest` para probar candidatos. Si todavía
   no hay una promoción revisada a `stable`, usa `latest`. Opcionalmente indica un
   digest `sha256:…` firmado del mismo repositorio; si está vacío se resuelve el
   canal una sola vez. El canal elegido queda como origen de actualizaciones de
   la instalación, incluso si indicas un digest.
4. Descarga el artefacto `gniri-iso-CANAL-RUN_ID-ATTEMPT` desde el resumen de la
   ejecución. Contiene `gniri-x86_64.iso`, `SHA256SUMS` y `build.json`; se conserva
   **7 días**. Extráelo y ejecuta `sha256sum --check SHA256SUMS` antes de grabarlo.

El workflow verifica la firma antes de descargar el payload, reutiliza su base
resuelta y ejecuta las regresiones de montajes/finalización del instalador. El
log `gniri-iso-log-…` se conserva también si falla la generación. No requiere un
runner propio: usa Ubuntu x86_64 alojado en GitHub con Podman privilegiado. Las
comprobaciones de contenedor y checksum no sustituyen las pruebas de arranque,
instalación, Secure Boot ni la evidencia revisada para promover `stable`. El
checksum del artefacto no lleva una firma independiente de Release.

Las herramientas locales de ISO siguen disponibles. Para crear una ISO de un
candidato publicado y firmado, usa su digest exacto:

```sh
make iso-published REFRESH=1 \
  PAYLOAD_REF=quay.io/owner/gniri@sha256:DIGEST \
  TARGET_REF=quay.io/owner/gniri:stable
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

### Cambio de GHCR a Quay.io

Las instalaciones e ISOs existentes conservan su origen GHCR: este cambio de
código no las migra automáticamente. No basta sustituir el hostname en una
política ni desactivar la verificación. Se recomienda copia/restauración verificada
y reinstalación desde una ISO nueva con origen Quay.io.

Las firmas están ligadas al repositorio (`matchRepository`): copiar blobs o tags
desde GHCR no basta. Toda imagen trasladada debe verificarse en el origen y
firmarse de nuevo para su referencia Quay con la clave confiable existente.
La promoción sigue necesitando un `:stable` previo firmado en Quay para comprobar
la versión y detectar cambios durante la revisión. Si se migra ese baseline,
solo puede ser el digest `stable` ya revisado, conservado sin reconstrucción y
verificado/firmado en el destino; no un candidato sin aprobar. Hasta disponer de
ese baseline, prueba candidatos con `latest`; no se omite el gate de promoción.
Ese baseline histórico no es una imagen migrada para instalar: genera la nueva
ISO `stable` solo después de promover un candidato construido para Quay, con su
política y referencia de actualización correctas.
Las imágenes externas del constructor (`ghcr.io/osbuild/image-builder-cli`) no
cambian de registro porque no son publicaciones de Gniri.

### Política de firma

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
