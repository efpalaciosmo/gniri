# Revisión de Zirconium y oportunidades para Gniri

Fecha: 2026-10-19. **Conviene completar algunas piezas del escritorio y evaluar
la distribución de capas OCI. No encontré una razón para sustituir nuestra
arquitectura de construcción, arranque o configuración personal.**

Seguimiento: el usuario aprobó audio, energía, Wi-Fi moderno, diagnóstico,
OpenVPN para GNOME, zram y la optimización de capas; se conserva el inglés.
El análisis de ausencias que sigue es la fotografía anterior a esos cambios.
La implementación se documenta en [hardware.md](hardware.md) y sus pruebas y
mediciones en [validation.md](validation.md).

Esta revisión propone cambios; no instala paquetes ni modifica el sistema.
Como todavía no se ha definido el alcance de hardware, prioriza un equilibrio
entre estabilidad, compatibilidad y tamaño, distinguiendo el equipo actual de
otros posibles equipos.

## Alcance y evidencia

- Zirconium local: `f89acfcb2967aeb4c78841bd9dedbcc6fb3aee8a`.
- Gniri local: `b0af250cd526faed510daf111b35de13e7a83e3e`.
- Imagen examinada: `localhost/gniri:development`, ID
  `297328d15ca1f2e89cd9711070ae0eaeb98720fb25f4f62a8de548f1119413b6`,
  creada el 19 de octubre a las 16:56 UTC.
- Base comparada: Fedora bootc 45 con digest
  `4776d2e96e263938a1b54c5c3a4cdd1c2ca723207b063a58ef36e1eda2fc9d61`.
- Se revisaron manifiestos, perfiles, scripts de construcción, unidades y
  presets systemd, configuración de arranque, actualizaciones, ISO y CI.
  Los directorios de submódulos locales estaban vacíos. Se descargó únicamente
  el código de `zdots` fijado por el repositorio, revisión
  `ba17a3aea5ab620471394779d1857788e9f3de33`, y se inspeccionaron su configuración
  Niri y sus ajustes DMS. Los recursos gráficos de `assets` no se descargaron.
- Los paquetes se comprobaron contra las imágenes locales, en contenedores
  desechables, de solo lectura, sin red ni dispositivos del anfitrión.
  La imagen Gniri tiene 1.194 registros RPM; la base, 540. Son inventarios RPM,
  no medidas de memoria ni de procesos activos.
- Evidencia local reproducible en `.cache/zirconium-review/`: inventarios
  `gniri-packages.json`, `base-packages.json` y `image-audit.json`.
  Esta caché no se versiona. Los resultados describen esa imagen concreta;
  una reconstrucción futura puede resolver otras versiones RPM.
- No se construyó ni arrancó Zirconium. Tampoco se instalaron las propuestas
  en Gniri. No se midieron autonomía, latencia, velocidad de red o tiempos
  de arranque. La presencia de un módulo o firmware no prueba su funcionamiento
  físico. Las pruebas previas de Gniri constan en [validation.md](validation.md).

El `PROJECT_SUMMARY.md` no versionado de Zirconium se dejó intacto y no se usó
como prueba de comportamiento. Las conclusiones proceden de los archivos y de
la imagen examinados.

## Diferencia que explica buena parte de los hallazgos

Zirconium declara `WithRecommends=true`, grupos `@core`, `@standard` y
`@base-graphical`, además de listas amplias de paquetes. Gniri parte de una
imagen Fedora bootc ya compuesta y usa `install_weak_deps=False` en sus
transacciones DNF. Eso da control, pero exige declarar expresamente varias
funciones que una instalación Workstation obtiene mediante recomendaciones.

Por tanto, **ausente del manifiesto no significa ausente de la imagen**.
Firmware Realtek, Intel GPU/audio y otras familias ya vienen de nuestra base.
También hay diferencias de nombres: Zirconium pide `nmtui`; Gniri ya incluye
el ejecutable mediante `NetworkManager-tui`. `nm-connection-editor`, UPower,
rtkit y `pipewire-gstreamer` también están instalados.

Referencias de Zirconium: [base](https://github.com/zirconium-dev/zirconium/blob/f89acfcb2967aeb4c78841bd9dedbcc6fb3aee8a/mkosi.profiles/base/mkosi.conf.d/fedora/mkosi.conf.d/base.conf),
[escritorio](https://github.com/zirconium-dev/zirconium/blob/f89acfcb2967aeb4c78841bd9dedbcc6fb3aee8a/mkosi.profiles/base-desktop/mkosi.conf.d/fedora/mkosi.conf.d/base-desktop.conf)
y [aplicaciones](https://github.com/zirconium-dev/zirconium/blob/f89acfcb2967aeb4c78841bd9dedbcc6fb3aee8a/mkosi.conf.d/fedora/mkosi.conf.d/zirconium.conf).
En Gniri: [instalación de paquetes](../build/install-packages.sh).

## Cambios con mayor valor

| Prioridad | Hallazgo comprobado en Gniri | Propuesta y beneficio |
| --- | --- | --- |
| Alta | Falta `alsa-ucm`; no existe `/usr/share/alsa/ucm2`. | Añadir perfiles UCM para ampliar la selección y el enrutamiento de entradas/salidas en hardware que los necesita. |
| Alta para otros equipos | Falta `alsa-sof-firmware`; tampoco hay árbol Intel SOF. | Incluir firmware y topologías SOF para equipos con esos DSP, especialmente portátiles. |
| Alta para Intel Wi-Fi | Existen el módulo `iwlwifi` y NetworkManager Wi-Fi, pero hay cero archivos `iwlwifi*.ucode*`. | Añadir `iwlwifi-mvm-firmware`; considerar DVM e iwlegacy si se quiere cubrir hardware Intel antiguo. |
| Alta para GNOME/portátiles | No están `tuned`, `tuned-ppd` ni `power-profiles-daemon`. | Incorporar un proveedor de perfiles de energía; preferencia inicial: `tuned` + `tuned-ppd`, siguiendo Fedora. |
| Alta para presión de memoria | Está `zram-generator`, pero no hay configuración principal ni fragmentos que creen dispositivos. | Añadir `zram-generator-defaults` y verificar swap comprimida después de arrancar. |
| Media | Faltan `alsa-utils` y `pipewire-utils`. `wpctl` sí existe. | Añadir herramientas para enumerar dispositivos, probar ALSA y observar el grafo y los errores de PipeWire. |
| Media, según uso | Solo hay locales C e inglés; no está `glibc-langpack-es`. | Añadir español si se desea un escritorio o formatos regionales en español. |
| Media | No hay fuente Noto Color Emoji. | Añadir `google-noto-color-emoji-fonts` para una cobertura de emojis más adecuada. |

Estas propuestas no implican que el audio actual esté averiado. WirePlumber
puede usar perfiles ACP para dispositivos sin UCM; UCM aporta descripciones
específicas cuando están disponibles. SOF cubre otro conjunto de hardware y no
es un requisito universal para el audio HDA del equipo actual.
Fuentes: [ALSA en WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/alsa.html),
[UCM en Fedora](https://packages.fedoraproject.org/pkgs/alsa-lib/alsa-ucm/)
y [firmware SOF](https://packages.fedoraproject.org/pkgs/alsa-sof-firmware/alsa-sof-firmware/).

Zirconium incluye también `alsa-firmware` y `alsa-tools-firmware`. Los dejaría
como ampliación condicionada al hardware que se quiera admitir; no todos los
paquetes que contienen la palabra firmware son necesarios para todas las
tarjetas.

Para energía, el propio RPM instalado de `gnome-control-center` recomienda
`ppd-service`, omitido por nuestra política de dependencias débiles.
`tuned-ppd` ofrece la API que utilizan los controles de perfiles de GNOME y la
traduce a TuneD. La recomendación es adoptar esa integración, mantener un perfil
equilibrado y medir antes de cambiar parámetros. No añadir simultáneamente
varios gestores que escriban los mismos controles de energía.
[Diseño de Fedora para TuneD y tuned-ppd](https://fedoraproject.org/wiki/Changes/TunedAsTheDefaultPowerProfileManagementDaemon).

Zirconium configura zram con `min(ram, 8192)`. Preferiría el paquete de valores
predeterminados de Fedora antes que mantener una copia propia. Instalar solo
el generador no crea swap: debe existir al menos una sección de dispositivo.
Esto puede ayudar al usar navegador, contenedores y máquinas virtuales bajo
presión de memoria; el efecto necesita medición y no sustituye la planificación
de RAM de las VM ni configura hibernación.
[Documentación del generador](https://github.com/systemd/zram-generator/blob/main/README.md)
y [valores predeterminados Fedora](https://packages.fedoraproject.org/pkgs/zram-generator/zram-generator-defaults/).

## Wi-Fi y Bluetooth: qué falta y qué ya está

**El equipo donde se hizo la revisión ejecuta CachyOS, no Gniri.** Se leyó su
inventario PCI/USB para identificar hardware, sin cambiar conexiones ni servicios:

| Dispositivo observado | Evidencia en la imagen Gniri | Conclusión |
| --- | --- | --- |
| Realtek RTL8852CE, `10ec:c852` | Módulo `rtw89_8852ce` y firmware solicitado `rtw89/rtw8852c_fw-2.bin` presentes. | Hay soporte básico empaquetado; falta probar conexión y reanudación en Gniri. |
| Ethernet RTL8125, `10ec:8125` | Módulo `r8169` presente. | Probar enlace y tráfico; no hay motivo demostrado para añadir un driver externo. |
| Bluetooth USB IMC Networks, `13d3:3586` | `btusb`, `btrtl` y varios firmware RTL8852 presentes. | Hay piezas relevantes, pero falta comprobar en Gniri qué firmware solicita este adaptador concreto. |
| Radeon 610M, `1002:164e` | `amdgpu`, firmware AMD, Mesa y RADV presentes. | Mantener la pila Fedora y probar aceleración física. |
| Audio HDA AMD/Realtek ALC1220 | `snd_hda_intel` presente. | Probar analógico, micrófono y HDMI; el nombre del módulo no indica que requiera una CPU Intel. |
| Webcam USB | Módulos `uvcvideo` y `snd_usb_audio` presentes. | Probar vídeo, micrófono y permisos desde una aplicación real. |

Nuestra imagen ya incluye `NetworkManager-wifi`, `wpa_supplicant`, `iw`,
`wireless-regdb`, `bluez`, `bluetoothctl`, `btmon`, y firmware Realtek, Atheros,
Broadcom y MediaTek. NetworkManager, Bluetooth, resolved y firewalld están
habilitados en la imagen. Habilitado no equivale a activo en una instalación.

La ausencia Intel sí está confirmada. Las familias MVM, DVM e iwlegacy se
distribuyen como paquetes separados. MVM sería la primera incorporación para
compatibilidad Intel moderna; DVM/iwlegacy dependen del alcance de equipos.
[MVM](https://packages.fedoraproject.org/pkgs/linux-firmware/iwlwifi-mvm-firmware/),
[DVM](https://packages.fedoraproject.org/pkgs/linux-firmware/iwlwifi-dvm-firmware/)
y [iwlegacy](https://packages.fedoraproject.org/pkgs/linux-firmware/iwlegacy-firmware/).

Para auriculares Bluetooth, la imagen contiene `libspa-bluez5.so` y complementos
SBC, AAC, LDAC, LC3 y mSBC, entre otros. No hace falta añadir un segundo servidor
de audio. Hay que probar emparejamiento, reconexión, reproducción A2DP y una
llamada con micrófono en GNOME y Niri. El códec realmente negociado depende
también del dispositivo. WirePlumber usa logind para entregar el audio Bluetooth
a la sesión activa; conservaría esa política en nuestro sistema con GDM.
[Integración Bluetooth oficial de WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html).

`NetworkManager-bluetooth`, ausente, sirve para conexiones de red Bluetooth
PAN/DUN. Lo añadiría si se usa tethering por Bluetooth; no es la solución para
auriculares o teclados.
[Tipos de conexión Bluetooth de NetworkManager](https://www.networkmanager.dev/docs/api/latest/settings-bluetooth.html).

No hay evidencia que justifique parámetros globales para desactivar ahorro
Wi-Fi, autosuspend USB, ASPM, suspensión de audio o cambiar el backend a iwd.
Si aparece un fallo, primero se identifica el dispositivo, error y firmware;
después se ensaya una regla limitada al equipo afectado.

## Integración de escritorio y periféricos

| Función | Lo que aporta Zirconium | Recomendación para Gniri |
| --- | --- | --- |
| Brillo de portátil | `brightnessctl` y atajos multimedia. | Útil si habrá portátiles. El respaldo Niri no tiene atajos de brillo ni silencio de micrófono. Es posible completarlos sin temas ni scripts personales. |
| Brillo de monitor externo | `ddcutil`. | Opcional para monitores DDC/CI; primero comprobar soporte, módulo y permisos I²C. No equivale al brillo de una pantalla interna. |
| Wi-Fi desde Niri | DMS con controles de red. | Gniri ya tiene nm-applet y editor de conexiones. Su autostart no excluye Niri y `niri.service` arranca el target XDG. Verificar que registra el agente de secretos, muestra los diálogos y recuerda contraseñas. |
| Bluetooth desde Niri | DMS con controles Bluetooth. | Validar el flujo de GNOME Settings bajo Niri o elegir una interfaz específica. Instalar BlueZ no garantiza una experiencia gráfica completa. |
| USB y discos | `udiskie`, GNOME Disks, UDisks/LVM. | UDisks y Nautilus ya están. Añadir udiskie solo si se desea montaje automático sin abrir Files; GNOME Disks sería una aplicación opcional. |
| Impresión | CUPS y numerosos drivers. | Tenemos bibliotecas y `cups-pk-helper`, pero falta el servidor CUPS. Añadir un conjunto de impresión según impresora; evitar todos los drivers preventivamente. |
| Cámaras complejas | libcamera y su integración. | La webcam UVC actual puede usar V4L2. `pipewire-plugin-libcamera`/libcamera son candidatos si otro equipo lo requiere. |
| VPN | Plugins OpenVPN, OpenConnect, strongSwan, etc. | Tailscale ya está. Añadir el plugin correspondiente al protocolo real; no instalar todos. |
| Módem/WWAN | NetworkManager WWAN, base de proveedores y usb_modeswitch. | Solo si se usarán módems celulares. Tener `ModemManager-glib` no implica tener el servicio completo. |
| Thunderbolt/USB4 | `bolt`. | Condicionado a docks o periféricos que necesiten autorización. |
| Accesibilidad y otros idiomas | Orca, Fcitx, fuentes y todos los locales. | Seleccionar según necesidad. Español puede resolverse inicialmente con `glibc-langpack-es`, sin añadir todos los idiomas o dos frameworks de entrada. |
| Monitores y convertibles | `kanshi`, `iio-niri`. | Opcionales para perfiles de pantallas o autorrotación; corresponden al hardware y a preferencias del usuario. |

El respaldo de Niri ya tiene bloqueo antes de suspensión, idle, agente polkit,
capturas nativas, portapapeles y atajos de audio. Sus portales son los del RPM
de Niri: GNOME/GTK y el proveedor de secretos GNOME Keyring. No añadiría
`xdg-desktop-portal-wlr` por analogía con otro compositor. La documentación de
Niri detalla los componentes que deben acompañar al compositor.
[Software de integración de Niri](https://niri-wm.github.io/niri/Important-Software.html).

Los sockets de GNOME Keyring y GCR SSH figuran deshabilitados globalmente,
mientras GDM contiene integración PAM con Keyring y existe activación D-Bus
para Secret Service. **Esto no demuestra que las contraseñas estén rotas**.
Antes de copiar los presets de Zirconium, probar desbloqueo del llavero,
persistencia de claves Wi-Fi y, si se usa, agente SSH al entrar por GDM en Niri.

Para vídeo, Gniri ya contiene `radeonsi_drv_video.so`; la ausencia de un RPM
llamado `mesa-va-drivers` no prueba ausencia del driver VA-API. Habría que medir
decodificación real en la aplicación elegida. Para una GPU Intel, falta
`libva-intel-media-driver`. Los códecs de aplicaciones Flatpak se deben evaluar
también dentro de su runtime; no asumir que añadir RPM del anfitrión los resuelve.

## Optimización relevante: capas para actualizaciones más pequeñas

Zirconium construye con mkosi y después pasa la imagen por Chunkah:
[`Justfile`, receta rechunk](https://github.com/zirconium-dev/zirconium/blob/f89acfcb2967aeb4c78841bd9dedbcc6fb3aee8a/Justfile).
Chunkah reorganiza el sistema de archivos en capas basadas en contenido para
favorecer su reutilización entre imágenes. No requiere adoptar mkosi para
considerar esa etapa posterior.
[Diseño de Chunkah](https://github.com/coreos/chunkah).

En nuestra imagen, `podman history` muestra unos **2,55 GB sin comprimir en la
capa de instalación RPM**; el tamaño total reportado por Podman es
4.597.510.959 bytes. No son tamaños de descarga. La base ya tiene varias capas,
pero nuestra transacción grande puede generar transferencias considerables
cuando cambia. Separar metadatos y aprovechar cachés, como ya hacemos, reduce
reconstrucciones locales; no divide automáticamente esa capa publicada.

Propuesta: ensayo separado con dos versiones consecutivas, misma selección
de paquetes y herramienta fijada por digest. Comparar bytes comprimidos de
blobs nuevos, tiempo de construcción, importación bootc y espacio temporal;
después probar arranque, firmas y rollback. Firmar el digest final después de
reorganizar las capas. Adoptarlo solo si la mejora de descarga compensa el
coste añadido. Esta revisión identifica un candidato; no demuestra un ahorro
concreto. El uso de `:latest` por Zirconium no es una elección que necesitemos copiar.

También conviene vigilar el inventario heredado: hay emuladores estáticos QEMU
para muchas arquitecturas y otros componentes de la base que no se deducen
de nuestros manifiestos. Una eventual reducción debe empezar por tamaños,
dependencias y uso real. Borrar archivos o RPM heredados de una capa anterior
no garantiza reducir los blobs ya distribuidos.

## Decisiones que conservaría y patrones que no trasladaría

- **Containerfile sobre Fedora bootc oficial.** Zirconium reconstruye buena
  parte de las convenciones bootc desde sus perfiles. Nosotros ya las heredamos;
  migrar a mkosi ampliaría el trabajo de mantenimiento sin un beneficio demostrado
  para el alcance actual.
- **OSTree con composefs y cadena de arranque Fedora.** El perfil principal de
  Zirconium también configura OSTree/composefs. Su perfil `sysupdate` está marcado
  expresamente como no predeterminado; no constituye una migración recomendada
  para nuestra distribución.
- **Kernel Fedora para el equipo AMD actual.** Jackrabbit reemplaza kernel y
  Mesa y añade schedulers, servicios y variables Proton de gaming. No hay medidas
  que justifiquen importarlo. El perfil NVIDIA compila módulos DKMS; el README
  de esta revisión indica que no están firmados para Secure Boot.
- **Configuración personal independiente.** Zirconium aplica `zdots` con chezmoi
  al iniciar y mediante un timer. Nuestro respaldo mínimo y la precedencia de
  dotfiles del usuario cumplen mejor la decisión actual de Gniri.
- **GDM, GNOME y Niri.** Greetd/DMS responde a otro diseño de escritorio. Sus
  temas, ajustes de entrada y shell no aportan por sí mismos mejoras de drivers.
- **Flathub de usuario y sin aplicaciones preinstaladas.** Zirconium aprovisiona
  remotos de sistema y varios Flatpak. No coincide con nuestro comportamiento
  elegido.
- **Timer bootc y actualización sin reinicio automático.** Zirconium deshabilita
  el timer bootc en su perfil final y emplea `uupd`. Añadirlo aquí duplicaría
  responsabilidades; mantener el calendario dominical ya definido.
- **Configuración mediante fragmentos y validación.** Evitar trasladar sus
  sustituciones `sed` de unidades upstream o sus enlaces `L+` sobre configuración
  administrativa como una receta general. Nuestros fragmentos de actualización
  conservan más claramente la intención y las modificaciones locales.
- **No copiar arreglos ajenos sin su condición.** El servicio de migración de
  grupos para imágenes con legacy rechunker reconstruye archivos de grupos;
  no corresponde incorporarlo a instalaciones nuevas sin ese problema.

Ya heredamos `chronyd`, resolved, `bootloader-update.service`, `fstrim.timer`
y la desactivación de `dnf-makecache.timer`; se comprobó su estado de habilitación.
No falta otro servicio de hora ni hace falta duplicar esos ajustes de Zirconium.

`NetworkManager-wait-online` está habilitado expresamente en Gniri. Antes de
deshabilitarlo para acelerar el arranque, medir la cadena crítica y revisar
dependencias de `network-online.target`, perfiles sin enlace y montajes remotos.
Estar habilitado no significa que siempre retrase GDM.
[Explicación upstream de wait-online](https://networkmanager.dev/docs/api/latest/NetworkManager-wait-online.service.html).

## Cómo lo incorporaría y comprobaría

1. **Completar el escritorio:** UCM, herramientas ALSA/PipeWire, proveedor de
   perfiles de energía y valores zram. Decidir español y emojis. Mantener
   dependencias explícitas y revisar el inventario de lanzadores.
2. **Definir la cobertura de hardware:** SOF e Intel MVM para una imagen más
   general; firmware antiguo, brillo, docks, impresión y VPN según equipos y uso.
   Declarar también el firmware crítico del equipo actual para que su presencia
   no dependa silenciosamente de recomendaciones de una base futura.
3. **Validar la imagen resultante:** construcción/lint; inventario RPM y menús;
   existencia de perfiles UCM, firmware y utilidades; unidades correctas.
   Añadir comprobaciones funcionales que detecten pérdidas reales de soporte,
   evitando pruebas que solo comparen una lista con otra copia de la misma.
4. **Arrancar una VM:** verificar zram con `zramctl` y `swapon --show`; cambios
   de perfil con la API de energía; login GNOME y Niri, llavero, diálogos Wi-Fi
   y portales de captura/compartición. Una VM no valida Wi-Fi/Bluetooth físico.
5. **Probar el equipo físico:** Wi-Fi en arranque frío y tras suspensión,
   coexistencia Wi-Fi/Bluetooth, audio analógico/HDMI/USB, A2DP y micrófono de
   auriculares, reconexión Bluetooth, webcam, Wacom y controles si se utilizan.
   Probar ambas sesiones y bloqueo/reanudación. Registrar fallos antes de ajustar
   parámetros. La suspensión requiere guardar el trabajo y coordinar la prueba.
6. **Ensayar Chunkah por separado:** comparar dos versiones y mantener los
   requisitos de firmas, instalación, actualización y rollback.

Los cambios que añadan aplicaciones gráficas deberán revisar deliberadamente
[`visible-applications.allow`](../packages/visible-applications.allow). No ocultar
iconos para hacer pasar la construcción ni añadir grupos completos para resolver
una función concreta. Las pruebas deben ejecutarse contra una nueva imagen e ISO;
los resultados de la imagen inspeccionada no validan paquetes todavía no añadidos.

Quedan por concretar: si la distribución cubrirá solo el equipo actual o varios;
si se necesita español; qué auriculares, impresora, VPN o docks se usan; y si
existe algún fallo reproducible pendiente. Estas respuestas cambian la selección
opcional, pero no los hallazgos confirmados del inventario.
