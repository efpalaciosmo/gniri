# Gniri

Sistema personal **Fedora estable + bootc**, con **GNOME y Niri** seleccionables
desde GDM. Sin navegador, extensiones GNOME ni aplicaciones Flatpak
preinstaladas; únicamente Flathub de usuario.

Usa **OSTree con composefs**, conservando la cadena Secure Boot de Fedora:
shim, GRUB y kernel oficial, sin UKI propio ni backend composefs nativo.
SELinux es permisivo solo en la ISO instaladora; Gniri instalado debe usar Enforcing.

Incluye Ghostty, Waybar/Fuzzel/Mako, Zathura, vi/Vim, Zsh/Starship, Tailscale,
Podman/Distrobox; no incluye QEMU, libvirt ni virt-manager en el host.
Las aplicaciones adicionales se instalan con Flatpak. Usa drivers Fedora para AMD/Intel,
PipeWire, OpenVPN, TuneD y zram. Los [manifiestos](packages/) y la
[lista de lanzadores](packages/visible-applications.allow) definen los paquetes;
cada imagen guarda inventarios efectivos en `/usr/share/gniri/`.

Niri tiene [un único archivo básico](system_files/etc/niri/config.kdl):
`Super+Enter` abre Ghostty y `Super+D` el lanzador. Tus dotfiles tienen prioridad;
no se copian configuraciones personales a la cuenta ni se imponen temas.

Las actualizaciones se preparan **los domingos a las 10:00, hora local**, con
hasta 30 minutos de retraso aleatorio y recuperación si el equipo estaba apagado.
**Nunca se reinicia automáticamente.**

Cada construcción resuelve el canal oficial `fedora-bootc:latest` a un digest.
La referencia completa es `quay.io/fedora/fedora-bootc:latest`: es una base
arrancable, a diferencia del contenedor de aplicaciones `fedora:latest`.
El digest fija **ese build**, no el número de versión para los builds siguientes.
No necesitas cambiar números de Fedora: Gniri sigue las versiones estables,
no Rawhide. Los equipos siguen `gniri:stable`; los candidatos solo se promueven
después de revisar pruebas de esa imagen. Esto no convierte Fedora en una
distribución rolling ni garantiza transiciones de versión sin mantenimiento.

```sh
make check
make build
make build REFRESH=1  # Renueva también los RPM aunque la base no haya cambiado.
make iso    # Instalador del stable publicado y verificado; origen GHCR permanente.
# Para desarrollo sin actualizaciones de registro: make iso-local
```

`make build` solo crea la imagen de Podman. `make iso` genera
**`output/iso/gniri-x86_64.iso`** y muestra su ruta al terminar.
Los builds locales reutilizan capas y omiten repacking para iterar más rápido.
`RECHUNK=1` reorganiza y valida las capas OCI; CI lo activa para candidatos firmados.

En GitHub, **Build and publish image** publica una imagen firmada en GHCR por cambios
en `main` y **cada sábado a las 05:00 de Bogotá (10:00 UTC)**. Puedes descargarla:

```sh
docker pull ghcr.io/efpalaciosmo/gniri:latest
# También: podman pull ghcr.io/efpalaciosmo/gniri:latest
```

Si el paquete es privado, ejecuta antes `docker login ghcr.io -u efpalaciosmo`
(o `podman login`) y usa como contraseña un token clásico de GitHub con
[`read:packages`](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).
Para descargas sin credenciales, la [configuración inicial](docs/building.md#github-configuración-inicial)
explica cómo hacer público el paquete.

`latest` es el candidato más reciente; las instalaciones siguen el canal revisado
`stable`. [`build.yml`](.github/workflows/build.yml) construye y firma candidatos.
[`promote.yml`](.github/workflows/promote.yml) promueve un digest ya probado,
sin reconstruirlo, tras validar evidencia y obtener revisión en el entorno
protegido `stable`. No permite bajar de versión mayor de Fedora.
Para generar una ISO en GitHub, abre **Actions → Build installer ISO → Run workflow**
y elige `stable` o `latest` (pruebas de candidatos). Descarga el artefacto
`gniri-iso-…` desde la ejecución; incluye ISO, `SHA256SUMS` y metadatos y se conserva
7 días. Requiere una imagen firmada ya publicada en el canal elegido; no promueve
`stable`. También puedes usar `make iso-candidate PAYLOAD_REF=...` localmente para
probar el candidato siguiendo `latest` sin cambiar el canal de producción.
La [guía de construcción](docs/building.md#github-configuración-inicial) describe
secretos, etiquetas e inventarios de la imagen.

> **En desarrollo:** no instalar en el equipo principal hasta probar la ISO,
> Secure Boot, actualizaciones y rollback en una VM.
> `make iso-local` es para desarrollo y no proporciona actualizaciones de registro.
> `make iso` exige un `stable` publicado con metadatos válidos. Una etiqueta o
> una firma no sustituye la validación de instalación, GDM y actualización/rollback.

- [Construcción, ISO, firmas y publicación](docs/building.md)
- [Uso, dotfiles, hardware y recuperación](docs/usage.md)
- [Pruebas, evidencia y límites de validación](docs/testing.md)
