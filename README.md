# Gniri

Sistema personal **Fedora 44 + bootc**, con **GNOME y Niri** seleccionables
desde GDM. Sin navegador, extensiones GNOME ni aplicaciones Flatpak
preinstaladas; únicamente Flathub de usuario.

Usa **OSTree con composefs**, conservando la cadena Secure Boot de Fedora:
shim, GRUB y kernel oficial, sin UKI propio ni backend composefs nativo.
SELinux es permisivo solo en la ISO instaladora; Gniri instalado debe usar Enforcing.

Incluye Kitty, Waybar, Fuzzel, Mako, Zathura, Fastfetch, vi, Zsh/Starship,
JetBrainsMono Nerd Font, Tailscale, Podman y QEMU/KVM con virt-manager.
Preparado para AMD, Wacom y controles de juegos con el kernel oficial Fedora.

Niri tiene [un único archivo básico](system_files/etc/niri/config.kdl):
`Super+Enter` abre Kitty y `Super+D` el lanzador. Tus dotfiles tienen prioridad;
no se copian configuraciones personales a la cuenta ni se imponen temas.

Las actualizaciones se preparan **los domingos a las 10:00, hora local**, con
hasta 30 minutos de retraso aleatorio y recuperación si el equipo estaba apagado.
**Nunca se reinicia automáticamente.**

```sh
make check
make build
make iso    # Local: no requiere cuenta GitHub ni publicar la imagen.
```

> **En desarrollo:** no instalar en el equipo principal hasta probar la ISO,
> Secure Boot, actualizaciones y rollback en una VM.

- [Construcción, publicación e ISO](docs/building.md)
- [Paquetes incluidos](docs/packages.md) · [uso y recuperación](docs/usage.md)
- [Dotfiles](docs/dotfiles.md) · [revisión técnica y fuentes](docs/architecture.md)
- [Validación](docs/validation.md) · [pruebas pendientes](docs/testing.md)
