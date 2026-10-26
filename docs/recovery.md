# Copias de seguridad y recuperación

**Rollback del sistema no es una copia de tus datos.** `/var`, los hogares,
configuración persistente y discos de máquinas virtuales pueden sobrevivir y
haber sido modificados por la versión nueva. No se restauran por seleccionar
otro kernel o deployment.

## Antes de usar el equipo principal

1. Elige un destino separado y cifrado; no la misma unidad que vas a instalar.
   Verifica su ruta con `findmnt`/`lsblk`. Guarda copias fuera del equipo y prueba
   que puedes descifrarlas con un medio de recuperación independiente.
2. Cierra sesión y apaga las VM de libvirt antes de copiar sus discos. Incluye
   los pools personalizados, XML de dominios/redes y estado de TPM/NVRAM, no
   solo `/var/lib/libvirt/images`. No copies una VM activa como si fuera una
   imagen consistente; utiliza un mecanismo de backup/snapshot soportado.
3. Conserva `/var/home` (o el destino real de `/home`), dotfiles, documentos,
   datos Flatpak de usuario y los datos de aplicaciones/containers que necesitas.
   Incluye `/etc` para **revisión selectiva**, no para sobrescribir todo el nuevo
   sistema. Tailscale y otros servicios guardan secretos bajo `/var/lib`: protege
   el archivo y detén el servicio o usa un mecanismo consistente al respaldarlo.
4. Usa una herramienta que preserve propietarios, permisos, ACL, xattrs y enlaces.
   GNU tar incluido admite `--acls --xattrs --selinux --numeric-owner`; crea
   archivos con `umask 077`. Verifica la política de exclusiones, checksums y
   espacio del destino. No hay un comando genérico de borrado/restauración aquí
   porque las rutas y pools dependen del equipo.
5. Restaura una copia en una VM/disco vacío distinto: comprueba ownership,
   enlaces Stow, apertura de archivos y arranque de una VM con TPM. Usa
   `restorecon` sobre rutas revisadas en el destino si corresponde. Confirma
   que el sistema sigue Enforcing. Anota la prueba y su resultado.

## Si una actualización falla

- Si todavía no reiniciaste, consulta `gniri-stage-update --status`, `bootc status`
  y el journal. Una descarga rechazada no debe cambiar el deployment arrancado.
  No borres `/ostree`, `/sysroot` ni los almacenes de contenedores para hacer sitio.
- Detén timer **y servicio** para cancelar reintentos. Crea el marcador de pausa
  descrito en [usage.md](usage.md), después prepara `bootc rollback` y reinicia
  manualmente. Conserva la pausa hasta que otro digest haya pasado validación.
- Si no puedes entrar al escritorio, usa una consola de texto o selecciona el
  deployment anterior desde GRUB. Tras arrancarlo, detén inmediatamente el timer
  y servicio; una versión antigua puede no conocer el marcador nuevo. No vuelvas
  a preparar el digest fallido. Si GRUB tampoco funciona, usa el medio Fedora
  firmado de recuperación, inspecciona discos sin formatear y recupera desde
  copia. No desactives SELinux/Secure Boot como solución permanente.
- Si el disco está lleno, identifica el filesystem afectado y datos prescindibles
  con `df`, `findmnt` y `du`. Conserva una versión recuperable y una copia antes
  de limpiar datos. Un fallo de escritura exige comprobar tanto `/boot` como
  `/var` y el destino raíz; no remountes `/usr` escribible.
- Ensaya cortes de energía/interrupciones y falta de espacio solo en discos
  desechables. Comprueba que el deployment anterior sigue arrancando y que los
  datos, claves y máquinas virtuales siguen intactos.

## Rotación de confianza

Conserva la clave de firma fuera del repositorio y de las copias públicas.
Una rotación necesita un despliegue de transición verificable por la confianza
anterior antes de retirar esa clave; ensáyala en VM. Si se pierde o compromete
la única clave confiada, no resuelvas el problema aceptando cualquier firma:
prepara un procedimiento de recuperación autenticado y explícito.

Estos pasos son requisitos de validación; su documentación no significa que
se hayan ejecutado con los datos o hardware del usuario.
