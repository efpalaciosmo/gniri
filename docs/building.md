# Construcción, publicación e ISO

## Imagen local

Requisitos: Linux x86_64, Podman, Make, Python 3, Internet y espacio para varios
GB de descargas, cachés e imágenes. No se instala ni se modifica el anfitrión.

```sh
make check
make build
```

Resultado: `localhost/gniri:development`, sin cuentas ni credenciales y sin
actualizaciones desde un registro. No es un contenedor de aplicación: se
distribuye para instalarlo como sistema bootc.

**`make build` no genera una ISO:** termina al guardar la imagen de Podman.
Para obtener el archivo instalador hay que ejecutar `make iso`.

Los manifiestos RPM y las descargas caras se procesan antes que los metadatos
y el overlay. Las capas y los cachés Podman se reutilizan localmente; los cachés
de descarga no se incorporan al sistema final. No limpies el almacenamiento de
Podman después de cada construcción si quieres reutilizarlos.

Después de construir, `make build` reorganiza la imagen con Chunkah fijado por
versión y digest. La herramienta se ejecuta sin red; la primera descarga de su
contenedor sí necesita conexión. La imagen se importa y pasa lint bootc, revisión
de su configuración OCI y comparación completa del contenido, permisos,
propietarios, enlaces y atributos. La etiqueta se sustituye solo al terminar
correctamente. Se mantienen 128 capas como máximo y el backend instalado
OSTree con composefs. Se retira únicamente el repositorio OSTree embebido
heredado de la construcción y sus dos etiquetas, siguiendo el contrato upstream.
La comparación acepta el modo raíz 0555 de la imagen importada y la reorganización
de hardlinks de archivos idénticos en `/usr` inmutable. Rechaza cambios de datos,
otros permisos o atributos y nuevos alias entre archivos de configuración mutable.
Separar hardlinks antiguos se admite: bootc copia `/etc` al desplegarlo.

Para diagnosticar la construcción sin esa etapa:

```sh
make build RECHUNK=0
```

Para conservar una salida OCI y su informe, sin sustituir la etiqueta original:

```sh
python3 scripts/rechunk-image.py localhost/gniri:development \
  --tag localhost/gniri:chunked --output .cache/rechunk-comparison
```

La salida debe ser un directorio nuevo. Los archivos temporales predeterminados
van a `.cache/` en disco, no a `/tmp` en RAM. Las firmas se generan después de
la reorganización; CI firma y publica el digest final. La primera actualización
desde imágenes antiguas puede necesitar descargar todas las capas nuevas.
Véanse las [mediciones y pruebas](validation.md); no hay un ahorro fijo garantizado
para todas las actualizaciones.

Base y constructor ISO fijados por digest; descargas upstream fijadas por
versión y SHA-256. Los RPM siguen los repositorios vivos de Fedora 45: no hay
reproducibilidad bit a bit. Renovate puede proponer actualizaciones de digest
y de acciones, pero las versiones/checksums en `build/upstream.env` requieren
revisión explícita.

## ISO totalmente local, sin cuenta ni publicación

Desde la raíz del repositorio, como usuario normal:

```sh
make iso
```

`make iso-local` es equivalente. Construye `localhost/gniri:development`,
transfiere la imagen al almacenamiento de Podman con privilegios y genera la
ISO con el payload local embebido. Pedirá `sudo` para esas operaciones.
**No necesitas GitHub Actions, cuenta GitHub, publicar en GHCR, Cosign ni
claves propias de firma para esta prueba local.**

Podman de usuario y `sudo podman` tienen almacenes separados; la receta los
conecta mediante un archivo OCI transmitido por una tubería, sin guardar otra
copia intermedia de varios GB en disco para esa transferencia. No intenta descargar `localhost/gniri` de un
registro ni cambia permisos en el repositorio completo.

Para componer el instalador, se exporta además un **directorio OCI** temporal
bajo `output/`, en el disco de construcción, y se incorpora al squashfs de la
ISO. Ese directorio de preparación se elimina al terminar, incluso si falla
la construcción. Necesitas espacio adicional en disco durante esta fase.
Anaconda lee sus blobs directamente mediante `oci:`, sin reconstruirlos en el
`/var/tmp` de la sesión live. No hay que ampliar `/run`, cambiar sus límites ni
asignar 10–12 GB de RAM para alojar una copia temporal de la imagen.

La ISO se publica siempre como **`output/iso/gniri-x86_64.iso`**, junto con
`output/iso/SHA256SUMS`. El nombre incluye la arquitectura del sistema anfitrión
soportado por Gniri (x86_64; no se ofrecen ISO ARM). Al terminar se muestra su
ruta absoluta. Para verificarla desde la raíz del proyecto:

```sh
ls -lh output/iso/gniri-x86_64.iso
(cd output/iso && sha256sum --check SHA256SUMS)
```

El constructor escribe primero en un directorio nuevo y solo publica el archivo
si hay exactamente una ISO no vacía; una ISO anterior no puede hacer pasar una
construcción sin salida. Su registro se guarda en **`output/iso-build.log`**.
Si `make iso` falla en esa fase, revisa:

```sh
tail -n 80 output/iso-build.log
```

Si ese registro no existe, el proceso no llegó al constructor ISO: revisa el
error de `make`, la construcción del contenedor o la autenticación de `sudo`.

**Local no significa construcción sin Internet:** se descargan la base Fedora,
RPM y herramientas públicas, incluido el contenedor de `image-builder` alojado
en GHCR. No requiere autenticarse ni subir tu imagen. La instalación desde la
ISO usa el payload incluido y está diseñada para funcionar sin red; el nuevo
transporte OCI necesita una prueba completa en VM. Una construcción completamente desconectada no es un
flujo soportado todavía.

Esta ISO de desarrollo no tiene un origen publicado del que descargar futuras
actualizaciones; el actualizador de Gniri omite las comprobaciones de registro.
Eso es independiente de Secure Boot: se conservan shim, GRUB y kernel Fedora,
sin desactivarlo ni generar claves de prueba.

El entorno **instalador** usa SELinux activo en modo **permisivo**
(`selinux=1 enforcing=0`), según la integración Anaconda/bootc. Esto no desactiva
Secure Boot y no cambia el payload de escritorio: el Kickstart solicita
`selinux --enforcing` para el sistema instalado. La construcción de Gniri
comprueba su configuración Enforcing y rechaza argumentos que la debiliten.
Después de instalar, verifica `getenforce`: debe devolver `Enforcing`.

Si la ISO anterior se congela con denegaciones SELinux de `systemd[1]`, puedes
confirmar el diagnóstico sin regenerarla: pulsa `e` sobre `Install Gniri` en
GRUB, añade `selinux=1 enforcing=0` al final de la línea que empieza por `linux`
y arranca con `Ctrl+X`. Es un cambio temporal para el instalador, no una solución
para un sistema ya instalado. La receta nueva incorpora estos argumentos al
generar otra ISO; la ISO existente no se modifica.

### Si falla DNS dentro del contenedor

Si DNF muestra `Could not resolve host` para todos los repositorios, comprueba
primero que el anfitrión tiene conexión y resuelve esos nombres:

```sh
getent hosts mirrors.fedoraproject.org fedoraproject-updates-archive.fedoraproject.org
```

Si funciona en el anfitrión pero falla durante la construcción —en particular
en la fase que usa `sudo podman`— prueba:

```sh
make iso BUILD_NETWORK=host
```

La opción se transmite también a través de `sudo`, tanto a la construcción del
instalador como al contenedor `image-builder`. Usa la red del anfitrión en vez
de la red privada de Podman. Es una opción de diagnóstico/recuperación para
construcciones de confianza, no el valor por defecto: reduce el aislamiento de
red de esos contenedores. No modifica `/etc/resolv.conf`, no impone DNS públicos
ni desactiva TLS, firmas RPM o repositorios.

Si tampoco funciona, compara la resolución dentro de un contenedor rootful
con la del anfitrión antes de cambiar repositorios o paquetes. Una caché de
paquetes no sustituye la conectividad necesaria para renovar metadatos.

## Publicación opcional: GHCR y firma

1. Crear el repositorio GitHub y habilitar Actions y GHCR.
2. Ejecutar `cosign generate-key-pair` y proteger la clave privada.
3. Añadir **solo** `trust/cosign.pub` al repositorio.
4. Crear los secretos GitHub `COSIGN_PRIVATE_KEY` y `COSIGN_PASSWORD`.
5. Ejecutar **Build and publish Gniri** desde `main`.
6. Hacer público `ghcr.io/<propietario-en-minúsculas>/gniri` para que el sistema
   pueda actualizarse sin guardar credenciales GHCR.

Las pull requests y ramas de prueba no publican. En `main` hay construcción
por cambios de código, ejecución manual y programación semanal: **sábado
06:20 UTC**, antes de la ventana dominical de los equipos. La firma se verifica
antes de actualizar `stable`. Los relojes de publicación y del equipo son
independientes: publicar una imagen no obliga a descargarla inmediatamente.

Las ejecuciones programadas usan `--no-cache` para renovar los RPM aunque el
digest base no haya cambiado. Los runners efímeros no conservan cachés entre
trabajos. Consultar [trust/README.md](../trust/README.md) para las claves y la
distinción entre firmas OCI y Secure Boot.

## ISO desde una imagen publicada

Después de publicar una imagen firmada, ejecutar **Build installer ISO** en
GitHub Actions. Crea una ISO x86_64 y SHA-256 como artefactos durante siete días;
no publica una release. La generación sigue siendo manual.

O generar localmente una ISO de esa versión publicada:

```sh
make iso-published \
  PAYLOAD_REF=ghcr.io/owner/gniri@sha256:DIGEST \
  TARGET_REF=ghcr.io/owner/gniri:stable
```

Ambos caminos usan `image-builder` con privilegios y `bootc-generic-iso`, no la acción
obsoleta `bootc-image-builder-action`. Anaconda vive en un contenedor instalador
separado, nunca en la imagen de escritorio. Para las imágenes publicadas el
payload se fija por digest y las actualizaciones apuntan a `stable`. La receta
local, en cambio, incorpora `localhost/gniri:development` sin publicar nada.

Cuenta, contraseña, discos y particionado se deciden interactivamente.
**No se incluye borrado automático.** No se impone cifrado ni Btrfs.
La cuenta debe crearse durante la instalación; no hay contraseña predeterminada.

La llamada al constructor incluye `--bootc-default-fs ext4` porque image-builder
exige ese metadato incluso para `bootc-generic-iso`. Es un respaldo para leer
la imagen instaladora, no una instrucción de particionado: no se añade
`autopart`, `--fstype` ni una configuración equivalente al Kickstart o al
payload. El sistema de archivos del disco instalado sigue eligiéndose en Anaconda.

**Pendiente:** generar y arrancar la ISO, comprobar Secure Boot con certificados
Fedora y completar instalación, actualización y rollback. Un workflow válido no
demuestra que su ISO arranque. Consultar [testing.md](testing.md).
