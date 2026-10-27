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

## GitHub: configuración inicial

La configuración del entorno se puede aplicar sin usar el dashboard, con Python 3
y GitHub CLI autenticado como administrador del repositorio. Revisa primero el
contenido **y todo el historial** antes de autorizar que se hagan públicos; por
ejemplo, escanéalos con Gitleaks. Después ejecuta:

```sh
python3 scripts/setup-github.py --repository efpalaciosmo/gniri \
  --reviewer efpalaciosmo --make-public
```

El script comprueba que ya existan los secretos de firma, hace público el
repositorio solo con autorización explícita, crea/configura `stable` con ese
revisor y limita deployments a la rama `main`. Verifica el resultado por API;
se puede repetir sin `--make-public` una vez público. No genera ni rota claves,
no borra políticas inesperadas ni aprueba deployments. Para un mantenedor único
permite aprobar manualmente sus propios runs; no realiza aprobación automática.
Los revisores obligatorios en repositorios privados no están disponibles con
GitHub Free/Pro/Team, de ahí el repositorio público para este flujo.

Requisitos que comprueba o utiliza la configuración:

1. Genera claves con `cosign generate-key-pair`. Guarda la privada fuera del
   repositorio; en `trust/` conserva **solo material público** (`cosign.pub`).
   En **Settings → Secrets and variables → Actions**, configura `COSIGN_PRIVATE_KEY`
   (contenido cifrado) y `COSIGN_PASSWORD`. Se usan para candidatos y para firmar
   checksums en promoción. `GITHUB_TOKEN` lo proporciona Actions; no necesitas un PAT.
   Si ambos secretos ya existen, consérvalos: no generes otro par para repetir el
   setup. Las firmas OCI autentican actualizaciones, no sustituyen Secure Boot.
2. Haz público `ghcr.io/OWNER/gniri` para permitir actualizaciones sin credenciales
   en el equipo. En la configuración del paquete, permite al repositorio acceso
   Actions de lectura/escritura. CI puede validar candidatos privados, pero la
   promoción exige acceso anónimo al payload antes de actualizar `stable`.
   **Excepción de automatización:** la API documentada de GitHub no permite cambiar
   la visibilidad de paquetes. Si falla el acceso anónimo, debes hacer una vez
   **Package settings → Change visibility → Public** en
   `https://github.com/users/OWNER/packages/container/gniri/settings`. Hacer público
   el repositorio no hace público el paquete; esta última operación es irreversible.
3. `scripts/setup-github.py` configura **`stable` con revisor obligatorio y solo
   `main`**. El YAML por sí solo no crea estas protecciones. No ejecutes promociones
   si el script no confirma el resultado. No necesita un token administrador
   adicional en Actions: el bootstrap usa tu sesión local de `gh`.
4. Protege `main` con revisión de PR y checks requeridos de sintaxis/tests e imagen.
   Permite los Actions fijados por SHA que usan los workflows. Solo promoción
   necesita `contents: write` para Releases; el resto conserva permisos mínimos.
   Es recomendable activar inmutabilidad de Releases en GitHub.

Dependabot propone actualizaciones de Actions semanalmente; sus referencias
siguen fijadas por SHA. Renovate queda a cargo de imágenes OCI y herramientas
fijadas en scripts, sin duplicar las PR de Actions. No hay S3 ni otro almacén de
artefactos externo: imágenes en GHCR, candidatos/logs en Actions y versiones en Releases.

## Pipeline de candidatos y releases

```text
PR → checks + imagen local (sin publicar ni usar secretos de firma)
main / sábado / ejecución manual → imagen firmada por digest
                                → ISO x86_64 + regresiones de instalador
                                → artefactos Actions + validation.json sin aprobar
pruebas reales → PR de evidencia → aprobación del entorno stable
              → verificar ISO descargada → firmar checksums → Release borrador
              → promover el mismo digest a stable → publicar GitHub Release
```

1. **Build and publish Gniri**, desde `main`, construye fresco, valida, repackea y
   publica el candidato firmado `sha-COMMIT-RUN_ID-ATTEMPT`; **no escribe `:stable`**.
   Se ejecuta por cambios de código, manualmente y los sábados a las 06:20 UTC.
   Las pull requests no publican. CI comprueba el cliente real contra imágenes
   firmadas, sin firma y con clave incorrecta; `policy-test-*` no son versiones instalables.
2. Tras un build publicable correcto, el mismo run llama **Build installer ISO**
   con **ese digest exacto**, sin resolver una etiqueta mutable. Usa otro runner
   para no conservar simultáneamente el almacenamiento de ambas construcciones.
   Incluye verificaciones Cosign y regresiones reales de montajes/finalización.
3. En la página del run descarga `gniri-installer-x86_64-ATTEMPT`: contiene ISO,
   `SHA256SUMS`, `build.json` y `validation.json`. Este último registra digest,
   revisión, checksum y `candidate_run_id`/`candidate_run_attempt`; todos los
   resultados de pruebas siguen siendo `untested`. También están disponibles
   `gniri-candidate-inventory-ATTEMPT` y `gniri-iso-logs-ATTEMPT`.
   Cada reejecución usa nombres distintos; no mezcles artefactos de intentos diferentes.
4. **Build installer ISO** sigue disponible manualmente desde `main` para generar
   una ISO de otro candidato: `payload_digest` es obligatorio y debe ser el digest
   exacto de un candidato firmado creado por **Build and publish Gniri**. No hay
   fallback a `stable`: puede seguir apuntando a una imagen antigua sin los metadatos
   de base resuelta que necesita el instalador. Si falta esa base, construye un
   candidato nuevo; reejecutar la ISO con el digest antiguo no lo modifica. No se
   debe promover a `stable` para poder construir la ISO de un candidato.
   También registra su propio run/intento y puede proporcionar una ISO
   revisada para promoción. La alternativa local, no apta para esta promoción
   basada en artefactos Actions, es:

   ```sh
   make iso-published REFRESH=1 \
     PAYLOAD_REF=ghcr.io/owner/gniri@sha256:DIGEST \
     TARGET_REF=ghcr.io/owner/gniri:stable
   ```

   Los flujos verifican Cosign antes de descargar el payload. El flujo local publicado
   requiere Cosign en el `PATH` de root. El instalador apunta al futuro `:stable`;
   desactiva las actualizaciones en la VM de candidatos antes de darle acceso al registro.
5. Completa las [pruebas](testing.md) con la ISO descargada. No se pueden demostrar
   Secure Boot, sesiones reales ni hardware simplemente construyendo en un runner.
   Conserva logs redactados y evidencia duradera, por ejemplo adjuntos de una issue
   GitHub pública; no uses solo URLs de logs/artefactos Actions que caducan.
6. Completa el `validation.json` de **esa ISO**, guarda el resultado revisado en
   `release-evidence/NOMBRE.json` mediante
   commit/PR. Solo resultados realmente obtenidos para ese digest, revisión e ISO,
   con URLs HTTPS duraderas. Conserva su run/intento exactos. No incluyas claves,
   credenciales, datos personales ni discos VM. Los artefactos Actions caducan a los
   30 días (o antes si la política del repositorio impone menos); promueve antes de
   que caduquen. Si reconstruyes o reejecutas, vuelve a comprobar la nueva ISO y evidencia.
7. Ejecuta **Promote tested candidate to stable** desde `main`, indicando esa ruta.
   Tras el gate y aprobación, descarga el artefacto del run/intento revisados. Exige
   un run correcto de `main` en este repositorio y comprueba SHA-256 real de ISO,
   metadatos, revisión de instalador y payload frente a la evidencia. No reconstruye.
   Firma el manifiesto de checksums con Cosign y sube todos los assets a un borrador
   `gniri-RUN_ID-ATTEMPT`; solo después copia **el mismo digest** a `:stable`, verifica
   el resultado y publica la Release como latest. El revisor debe leer la evidencia:
   un JSON no prueba criptográficamente los ensayos.

Una promoción fallida puede dejar un borrador. Reejecutar permite completar sus
assets únicamente si conserva la misma revisión y sigue sin publicar; nunca
sobrescribe una Release publicada. No existe una transacción atómica entre GHCR
y Releases: si falla publicar después de promover, `stable` ya puede apuntar al
candidato aprobado y el borrador puede completarse reejecutando la promoción.
No hay actualización nueva hasta promover un candidato.

## Descargar y verificar una Release

Las Releases conservan ISO, metadatos y evidencia más allá de la retención de Actions.
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
