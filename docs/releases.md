# Canal estable y promoción

## Actualizaciones sin seleccionar versiones de Fedora

`make build` consulta el manifiesto oficial de
`quay.io/fedora/fedora-bootc:latest`, selecciona Linux x86_64 y construye desde
ese digest. El instalador usa la base grabada en los metadatos del payload,
no el `latest` que exista el día de generar la ISO. Los fondos se seleccionan
desde `VERSION_ID`; no hay que editar `f45`, `f46`, etc.

Esto sigue las **versiones estables de Fedora**, no Rawhide. El 25 de octubre
de 2026 `latest` corresponde a Fedora 44, mientras `rawhide` corresponde a
Fedora 46 en desarrollo. «Everything» es una colección/árbol de paquetes,
no un canal rolling con mayor estabilidad. Seguir `latest` evita gestionar el
número manualmente, pero no elimina el mantenimiento de GNOME, paquetes o
parches de Anaconda cuando cambia upstream. Una incompatibilidad debe detener
la construcción/promoción, nunca desactivar Secure Boot o SELinux.

Canales oficiales: [etiquetas de Fedora bootc](https://quay.io/repository/fedora/fedora-bootc?tab=tags).

El Containerfile conserva un digest de respaldo para construcciones directas;
**el flujo soportado usa Make o `scripts/build-image.py`**, que resuelve el
canal cada vez. Renovate puede actualizar herramientas/acciones y ese respaldo;
no decide la promoción de Gniri. `REFRESH=1` vuelve a ejecutar las transacciones
RPM sin borrar las cachés de descargas. CI siempre utiliza construcción fresca.

El sistema instalado sigue `ghcr.io/OWNER/gniri:stable`, no la base Fedora.
Una actualización de Fedora solo llega dentro de una imagen Gniri promovida.
No se ejecuta ningún rebase del anfitrión al construir este repositorio. Una
instalación antigua Fedora 45 no debe degradarse a 44 sin una evaluación
explícita: esperar a que el canal estable alcance esa versión o reinstalar con
copias verificadas. Prueba las transiciones entre versiones como cualquier otra
actualización, con datos de prueba y rollback.

## Candidato → pruebas → stable

1. Configura las claves según [trust/README.md](../trust/README.md), haz público
   el paquete GHCR y crea un entorno GitHub **`stable` con revisores obligatorios**.
   Las reglas de protección se configuran en GitHub; YAML por sí solo no las activa.
2. **Build and publish Gniri** ejecuta validadores obligatorios, construcción
   fresca, repacking, Kitty/Niri y Flatpak sin red. Publica un candidato firmado
   `sha-COMMIT-RUN_ID-ATTEMPT`; **nunca escribe `:stable`**.
3. El cliente `skopeo` de la imagen verifica el candidato con la política estricta.
   CI genera dos manifiestos distintos y únicos: uno sin firma y otro firmado
   con una clave efímera incorrecta. Ambos deben ser accesibles anónimamente y
   rechazados por firma, no por DNS/autenticación. Esas claves no son claves
   Secure Boot y nunca se incorporan a la imagen. Las etiquetas `policy-test-*`
   son fixtures negativos, no versiones instalables; pueden retirarse
   deliberadamente tras archivar los resultados, sin borrar firmas de releases.
4. Descarga `gniri-candidate-inventory`: incluye inventarios, `build.json`, digest
   y una plantilla `validation.json` con todos los resultados **untested**.
5. Genera la ISO con **Build installer ISO**, proporcionando `payload_digest`.
   Esto permite probar el primer candidato aunque `stable` todavía no exista.
   El workflow ejecuta además los regresores reales Anaconda/OSTree. También
   puedes usar `make iso-published ... REFRESH=1`; ambos verifican Cosign antes
   de descargar el payload. El instalador apunta al futuro `:stable`.
6. En una VM desechable de validación de candidatos, desactiva el timer de
   actualizaciones antes de permitir acceso al registro: no debe cambiarse al
   `stable` anterior durante las pruebas. Completa [testing.md](testing.md),
   incluida actualización firmada y rechazos usando el helper real de bootc,
   Secure Boot con certificados Fedora, escritorios y hardware físico.
7. Archiva logs redactados, configuración de VM, inventarios, `build.json`, ISO
   y checksum en almacenamiento duradero. Los artefactos Actions de 30 días no
   son un archivo de releases. Para distribución pública publica también un
   checksum autenticado con una firma verificable y documenta su clave.
8. Completa los resultados y URLs HTTPS de evidencia. Guarda el JSON revisado
   como `release-evidence/NOMBRE.json` en un commit/PR, sin secretos. No marques
   `pass` si el test no se realizó. El digest, commit y SHA-256 de ISO deben
   corresponder a los artefactos realmente probados.
9. Ejecuta **Promote tested candidate to stable** desde `main` indicando esa ruta.
   El gate rechaza datos incompletos u otro digest/commit. Tras la revisión del
   entorno protegido, se verifica firma/revisión OCI y se copia el mismo digest
   a `stable`, sin reconstruir. La plantilla no es una prueba criptográfica de
   los ensayos: el revisor debe leer la evidencia.

La programación semanal ahora produce **candidatos**, no actualizaciones
automáticamente aprobadas. No habrá una nueva actualización hasta completar
la promoción. Los clientes conservan domingo 10:00, reintentos limitados y
reinicio exclusivamente manual.

## Desarrollo local frente a instalación mantenida

`make iso` sigue funcionando sin cuenta/registro, pero instala
`localhost/gniri:development`: no tiene origen de actualizaciones. Úsala en VM,
no como instalación permanentemente mantenida. Para el equipo principal usa
la ISO de un digest firmado **que ya haya pasado las pruebas**.

Una instalación local antigua no contiene necesariamente la clave o política
de registro. No basta con añadir `--enforce-container-sigpolicy`: eso no crea
confianza en una clave. La ruta recomendada es copia/restauración verificada
y reinstalación desde la ISO publicada. Si necesitas migrar in-place, primero
ensaya exactamente ese sistema en una copia de disco desechable:

- Obtén `trust/cosign.pub` por un canal autenticado y comprueba su fingerprint
  de forma independiente; no confíes solo en una clave descargada del registro.
- Crea una política temporal root-owned, `default: reject`, con un único ámbito
  Docker para el repositorio Gniri, `sigstoreSigned`, esa clave y `matchRepository`.
  Configura también `use-sigstore-attachments: true` para ese repositorio.
- Verifica el digest elegido con Cosign y el cliente containers/image. Desde
  esa política, ensaya `bootc switch --enforce-container-sigpolicy` al origen
  autorizado. No reutilices una política `insecureAcceptAnything` como bootstrap.
- Comprueba el digest realmente preparado antes de reiniciar; conserva el
  deployment anterior. Tras arrancar, el helper debe usar la política inmutable
  de la nueva imagen. Verifica actualización/rechazo/rollback y elimina los
  archivos temporales solo cuando dejen de ser necesarios.

Esto es un procedimiento de evaluación, no una migración ya validada ni un
script automático contra el sistema del usuario.
