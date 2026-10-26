# Construcción y publicación

## Base y paquetes

El flujo soportado (`make` / `scripts/build-image.py`) resuelve el canal oficial
[`fedora-bootc:latest`](https://quay.io/repository/fedora/fedora-bootc?tab=tags)
a un digest Linux x86_64 en cada construcción. Sigue Fedora estable, no Rawhide:
no hay que editar números de versión. El instalador reutiliza la base grabada
en el payload; no resuelve otro `latest`. Esto no garantiza transiciones sin
mantenimiento ni autoriza degradar una instalación desde una versión más nueva.

Se conserva OSTree con composefs, raíz física de solo lectura y estado persistente
en `/etc` y `/var`. La cadena firmware → shim → GRUB → kernel es la de Fedora;
no hay UKI propio ni backend composefs nativo. `enabled=yes` no autentica por sí
solo todo el filesystem. La compatibilidad Secure Boot necesita pruebas reales.

Los [manifiestos RPM](../packages/) omiten grupos de escritorio y dependencias
débiles. Los fondos se eligen desde `VERSION_ID`; los lanzadores se validan contra
[su lista](../packages/visible-applications.allow). Tailscale usa su repositorio
oficial; [las descargas upstream](../build/upstream.env) tienen versión/checksum
fijos. Los RPM siguen repositorios vivos: no hay reproducibilidad bit a bit.

## Construcción local

Desde la raíz del repositorio: Linux x86_64, Podman, Make, Python 3, Internet y
espacio para imágenes, cachés y staging de varios GB. La ISO requiere `sudo` y
`flock` (util-linux). No se instala ni se rebasa el sistema del anfitrión.

```sh
make check
make build              # Solo imagen: localhost/gniri:development.
make iso                # Construye la imagen y genera la ISO local; pide sudo.
```

| Opción | Uso |
| --- | --- |
| `REFRESH=1` | Reejecuta transacciones RPM sin borrar cachés de descarga; usar para releases. |
| `RECHUNK=0` | Omite el repacking solo para diagnóstico. |
| `BUILD_NETWORK=host` | Diagnóstico de DNS en contenedores; reduce aislamiento, no cambia el firewall. |

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

`make iso` (`make iso-local`) no requiere GitHub, publicación ni Cosign, pero
instala una imagen **de desarrollo sin origen de actualizaciones**. Para uso
permanente usa una imagen publicada, firmada y [validada](testing.md).

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

## Firmas y publicación

1. Genera claves con `cosign generate-key-pair`. Guarda la privada fuera del
   repositorio; en `trust/` conserva **solo material público** (`cosign.pub`).
   Configura los secretos GitHub `COSIGN_PRIVATE_KEY` (contenido cifrado) y
   `COSIGN_PASSWORD`. Las firmas OCI autentican actualizaciones, no sustituyen Secure Boot.
2. Haz público `ghcr.io/OWNER/gniri` para permitir actualizaciones sin credenciales
   en el equipo. Crea el entorno GitHub **`stable` con revisores obligatorios**:
   el YAML no configura por sí solo las reglas de protección.
3. **Build and publish Gniri**, desde `main`, construye fresco, valida, repackea y
   publica el candidato firmado `sha-COMMIT-RUN_ID-ATTEMPT`; **no escribe `:stable`**.
   Se ejecuta por cambios de código, manualmente y los sábados a las 06:20 UTC.
   Las pull requests no publican. CI comprueba el cliente real contra imágenes
   firmadas, sin firma y con clave incorrecta; `policy-test-*` no son versiones instalables.
4. Descarga `gniri-candidate-inventory`: contiene inventarios, metadatos, digest y
   `validation.json` con resultados `untested`. Genera su ISO con **Build installer
   ISO**, indicando `payload_digest`; vacío selecciona el `stable` actual. O usa:

   ```sh
   make iso-published REFRESH=1 \
     PAYLOAD_REF=ghcr.io/owner/gniri@sha256:DIGEST \
     TARGET_REF=ghcr.io/owner/gniri:stable
   ```

   Ambos verifican Cosign antes de descargar el payload. El flujo local publicado
   requiere Cosign en el `PATH` de root. El instalador apunta al futuro `:stable`;
   desactiva las actualizaciones en la VM de candidatos antes de darle acceso al registro.
5. Completa las [pruebas](testing.md), archiva logs redactados, ISO, checksum y
   metadatos de forma duradera. Los artefactos ISO de Actions caducan a los 30 días;
   no son releases. Para distribución pública, autentica también los checksums.
6. Guarda el JSON completo y revisado en `release-evidence/NOMBRE.json`, mediante
   commit/PR. Solo resultados realmente obtenidos para ese digest, revisión e ISO,
   con URLs HTTPS duraderas. No incluyas claves, credenciales, datos personales ni discos VM.
7. Ejecuta **Promote tested candidate to stable** desde `main`, indicando esa ruta.
   Tras el gate y aprobación se verifican firma/revisión OCI y se copia **el mismo
   digest**, sin reconstruir. El revisor debe leer la evidencia: un JSON no prueba
   criptográficamente los ensayos. No hay actualización nueva hasta promover un candidato.

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
