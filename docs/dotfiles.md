# Configuración personal separada del sistema

La imagen ya no contiene una copia de tus dotfiles, temas, wallpapers,
scripts de menús o configuración de otras aplicaciones. Tampoco hay un
importador ni un servicio que copie archivos al directorio personal.
`~/tmp/dotfiles` no se ha modificado.

## Respaldo mínimo de Niri

[`/etc/niri/config.kdl`](../system_files/etc/niri/config.kdl) es un único archivo
en inglés: Kitty, Fuzzel, Files, Waybar/Mako sin personalizar, agente polkit,
bloqueo/idle y atajos básicos. No contiene includes, rutas a scripts personales,
temas ni monitores fijados. GNOME también conserva su apariencia de Fedora.

Niri da prioridad a `$XDG_CONFIG_HOME/niri/config.kdl` o
`~/.config/niri/config.kdl`; solo usa `/etc/niri/config.kdl` si no existe el
archivo del usuario. No hace falta modificar la sesión, envolver el ejecutable
ni crear archivos durante el primer login.

Para partir del respaldo:

```sh
mkdir -p ~/.config/niri
# Solo si no tienes ya una configuración:
cp --no-clobber /etc/niri/config.kdl ~/.config/niri/config.kdl
```

O enlaza tus dotfiles con Stow según las instrucciones de tu repositorio.
El antiguo playbook de CachyOS **no debe ejecutarse** para instalar paquetes
en Gniri; usa únicamente el mecanismo de enlaces que hayas revisado.

Waybar, Fuzzel, Mako, Kitty, GTK, Zathura y Starship utilizan los valores
de sus paquetes hasta que aportes tu propia configuración. Los portales
siguen usando el archivo de integración suministrado por el RPM de Niri.
Si ejecutas una configuración propia, esta controla también sus procesos de
inicio y bloqueo; no se mezclan con los del respaldo del sistema.

**Si probaste la versión anterior:** los archivos que aquella versión copió a
tu cuenta no se borran ni se sobrescriben. Revísalos al migrar a tus dotfiles;
eliminar la copia de la imagen no autoriza a borrar datos de usuario.

Fuente: [carga y precedencia oficiales de Niri](https://niri-wm.github.io/niri/Configuration%3A-Introduction.html#loading).
