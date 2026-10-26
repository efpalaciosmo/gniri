# Gniri

Sistema personal **Fedora estable + bootc**, con **GNOME y Niri** seleccionables
desde GDM. Sin navegador, extensiones GNOME ni aplicaciones Flatpak
preinstaladas; únicamente Flathub de usuario.

Usa **OSTree con composefs**, conservando la cadena Secure Boot de Fedora:
shim, GRUB y kernel oficial, sin UKI propio ni backend composefs nativo.
SELinux es permisivo solo en la ISO instaladora; Gniri instalado debe usar Enforcing.

Incluye Kitty, Waybar/Fuzzel/Mako, Zathura, vi/Vim, Zsh/Starship, Tailscale,
Podman/Distrobox y QEMU/KVM con virt-manager. Usa drivers Fedora para AMD/Intel,
PipeWire, OpenVPN, TuneD y zram. Los [manifiestos](packages/) y la
[lista de lanzadores](packages/visible-applications.allow) definen los paquetes;
cada imagen guarda inventarios efectivos en `/usr/share/gniri/`.

Niri tiene [un único archivo básico](system_files/etc/niri/config.kdl):
`Super+Enter` abre Kitty y `Super+D` el lanzador. Tus dotfiles tienen prioridad;
no se copian configuraciones personales a la cuenta ni se imponen temas.

Las actualizaciones se preparan **los domingos a las 10:00, hora local**, con
hasta 30 minutos de retraso aleatorio y recuperación si el equipo estaba apagado.
**Nunca se reinicia automáticamente.**

Cada construcción resuelve el canal oficial `fedora-bootc:latest` a un digest.
No necesitas cambiar números de Fedora: Gniri sigue las versiones estables,
no Rawhide. Los equipos siguen `gniri:stable`; los candidatos solo se promueven
después de revisar pruebas de esa imagen. Esto no convierte Fedora en una
distribución rolling ni garantiza transiciones de versión sin mantenimiento.

```sh
make check
make build
make build REFRESH=1  # Renueva también los RPM aunque la base no haya cambiado.
make iso    # Local: no requiere cuenta GitHub ni publicar la imagen.
```

`make build` solo crea la imagen de Podman. `make iso` genera
**`output/iso/gniri-x86_64.iso`** y muestra su ruta al terminar.
La construcción reorganiza y valida las capas OCI para reducir tamaño y
descargas de actualización; `RECHUNK=0` permite omitir esa etapa al diagnosticar.

> **En desarrollo:** no instalar en el equipo principal hasta probar la ISO,
> Secure Boot, actualizaciones y rollback en una VM.
> `make iso` es para desarrollo y no proporciona actualizaciones de registro.
> Para el equipo principal, usar una imagen publicada, firmada y validada.

- [Construcción, ISO, firmas y publicación](docs/building.md)
- [Uso, dotfiles, hardware y recuperación](docs/usage.md)
- [Pruebas, evidencia y límites de validación](docs/testing.md)
