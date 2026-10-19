# Revisión técnica

Revisión de documentación upstream: 2026-10-18. Se distingue entre usar
interfaces actuales y cambiar a una arquitectura distinta solo por ser nueva.

| Área | Decisión y motivo |
| --- | --- |
| Base | Tag oficial Fedora 45 bootc fijado por digest, solicitado por el usuario; selección explícita de RPM sin Workstation ni Silverblue. |
| Despliegue | Backend OSTree con composefs activado, tal como lo suministra Fedora; no backend composefs nativo. |
| Construcción | Containerfile + Podman/DNF5 y cachés de descarga. Es el flujo directo de derivación bootc; no hace falta añadir mkosi/BuildStream para esta composición. |
| Configuración | Respaldo nativo `/etc/niri/config.kdl`; dotfiles exclusivamente del usuario. Se eliminan el importador, copia en login, temas y overrides GNOME. |
| Actualización | Timer systemd upstream con calendario dominical y `bootc upgrade` sin `--apply`. Calendarios persistentes recuperan ejecuciones perdidas. |
| Publicación | GHCR, digest inmutable, Cosign y política de firmas en el equipo; no basta con firmar en CI. |
| ISO | `image-builder build ... bootc-generic-iso`, con Anaconda separado y payload embebido; la interfaz antigua `anaconda-iso` y su acción están obsoletas. |
| Virtualización | Daemons modulares libvirt y sockets UNIX; autorización explícita de una sola cuenta, no grupo `input` ni apertura TCP. |
| Seguridad | Kernel Fedora y SELinux Enforcing en Gniri; solo el entorno ISO usa SELinux permisivo siguiendo Anaconda/bootc. Sin akmods. Secure Boot sigue pendiente de prueba. |

## Mejoras aplicadas en esta revisión

- Un solo archivo de Niri y ningún aprovisionamiento de dotfiles.
- Fastfetch añadido; `vi` ya estaba mediante `vim-minimal`, sin otro Vim.
- Actualización del equipo semanal: domingo 10:00 local, retraso máximo de
  30 minutos y recuperación con `Persistent=true`, sin disparador al arrancar.
- Publicación programada semanal el sábado 06:20 UTC. Cambios de código y
  ejecuciones manuales aún pueden generar imágenes; el equipo sigue su timer.
- Metadatos OCI y lista de iconos después de las operaciones costosas: cambiar
  el repositorio/origen de una imagen no invalida la instalación de paquetes.
- No se asigna una URL GitHub ficticia a las construcciones locales; CI aporta
  el repositorio real. Solo `main` puede actualizar `stable`.
- `make iso` funciona sin publicación: transfiere la imagen de desarrollo entre
  los almacenes Podman de usuario/root y la incorpora al instalador. El modo
  publicado sigue separado en `make iso-published` y en GitHub Actions.

## Decisión: OSTree con composefs y Secure Boot de Fedora

Se elige explícitamente **OSTree con composefs**, no el backend nativo
composefs-rs de bootc. La base comprobada ya contiene:

```ini
# /usr/lib/ostree/prepare-root.conf
[composefs]
enabled = yes
[sysroot]
readonly = true
```

Se hereda sin duplicarlo ni modificar el initramfs. Las validaciones comprueban
la configuración efectiva, kernel no unificado y presencia de bootupd, shim y
GRUB Fedora. No se crea `/usr/lib/composefs/setup-root-conf.toml`, no se genera
un UKI ni se cambia a systemd-boot. Se mantienen `/etc` y `/var` persistentes.

Secure Boot conserva la cadena **firmware → shim → GRUB → kernel Fedora**;
no se reemplazan las claves UEFI de fábrica ni se requiere una clave propia
para un UKI personalizado. Esto mantiene el diseño compatible, pero su arranque
debe verificarse en la ISO y en el equipo. `enabled=yes` no equivale a una imagen
sellada: no exige fs-verity ni autentica el sistema de archivos completo mediante
un UKI firmado. No se activa `enabled=verity` ni `enabled=signed` sin una decisión
independiente, pues cambian requisitos de instalación y verificación.

La migración al backend nativo queda aplazada hasta revisar su integración con
el instalador, Secure Boot y recuperación. Upstream actual lo declara soportado,
pero no existe una migración in-place desde OSTree; hoy podría requerir
reinstalar. No se prometerá una migración automática futura. La versión actual
de nuestra imagen es 1.16.13; upstream 1.17.1 tiene documentación y correcciones
posteriores, por lo que no se deben confundir sus interfaces y garantías.

Cosign 3 permite formatos nuevos, pero containers/image no reconoce todos de
igual manera. Se conserva explícitamente el formato compatible con su política
`sigstoreSigned`; se debe probar la verificación en el propio cliente bootc.
El usuario ya generó e instaló ISO de Gniri en QEMU. Se han identificado y
corregido problemas del instalador; eso no sustituye la validación completa de
la receta actual ni demuestra que la migración a Fedora 45 esté lista para el
equipo principal. Véase el registro de validación y sus límites.

El ejemplo actual de image-builder aún usa `interactive-defaults.ks`; Anaconda
documenta su reemplazo futuro por archivos de configuración. No se inventa una
API alternativa para seleccionar el payload mientras el contrato publicado
del constructor siga usando ese archivo. Es un punto a revisar al actualizar
el instalador, no un motivo para afirmar que la ISO ya está probada.

El primer arranque de la ISO mostró un bloqueo fatal de PID 1 por SELinux.
Con aprobación del usuario, la receta diferencia los dos entornos: Anaconda
arranca con SELinux activo pero permisivo (`selinux=1 enforcing=0` y configuración
permisiva antes de generar su initramfs); el payload separado conserva Enforcing
y el Kickstart solicita `selinux --enforcing` al instalar. Esto no cambia las
claves, el kernel firmado ni el estado de Secure Boot. No se propagan argumentos
permisivos al payload. La comprobación de `getenforce` tras instalar sigue siendo
un requisito, no algo demostrado por las pruebas estáticas.

## Fuentes primarias

- [Derivar imágenes Fedora bootc](https://docs.fedoraproject.org/en-US/bootc/building-from-scratch/)
- [Actualización y rollback bootc](https://bootc.dev/bootc/bootc-upgrades.7.html)
- [Composefs dentro de OSTree recomendado por bootc](https://bootc.dev/bootc/bootc-filesystem.7.html)
- [Configuración e integridad de composefs en OSTree](https://ostreedev.github.io/ostree/composefs/)
- [Backend composefs: soporte y límites](https://bootc.dev/bootc/bootc-composefs.7.html)
- [systemd.timer: calendarios y persistencia](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
- [Precedencia de configuración Niri](https://niri-wm.github.io/niri/Configuration%3A-Introduction.html)
- [Migración a image-builder](https://github.com/osbuild/image-builder/blob/main/doc/20-advanced/20-bootc/50-migration.md)
- [Contrato actual de las ISO](https://github.com/osbuild/image-builder/blob/main/doc/20-advanced/20-bootc/10-isos.md)
- [Configuración Anaconda y transición de interactive-defaults.ks](https://anaconda-installer.readthedocs.io/en/latest/developer/configuration-files.html)
- [Integración Anaconda/bootc y su entorno SELinux permisivo](https://github.com/rhinstaller/anaconda/blob/main/pyanaconda/modules/payloads/payload/rpm_ostree/installation.py)
- [Arquitectura de libvirt](https://libvirt.org/daemons.html)

Los archivos NIRI.md y CACHE_GUIDANCE.md aportados son referencias de otros
proyectos; no describen la implementación actual de Gniri.
