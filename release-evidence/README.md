# Evidencia por candidato

La promoción no acepta un build verde como prueba de arranque. Después de
construir y firmar un candidato, genera su ISO con `make iso-candidate
PAYLOAD_REF=ghcr.io/OWNER/gniri@sha256:DIGEST` y ejecuta `docs/testing.md`.
Para probar la ISO de producción antes de cambiar el tag, también se puede usar
`make iso-published` con el mismo digest y `TARGET_REF=ghcr.io/OWNER/gniri:stable`.

Genera el registro inicial sin marcar resultados como aprobados:

```sh
python3 scripts/release-gate.py template \
  --digest sha256:DIGEST --revision COMMIT_COMPLETO \
  --run-id RUN_ID --run-attempt ATTEMPT --iso-sha256 SHA256_ISO \
  --output release-evidence/DIGEST.json
```

El nombre del archivo usa los 64 caracteres hexadecimales, sin `sha256:`.
Conserva los logs de las comprobaciones de ese digest e ISO en URLs HTTPS
duraderas. Registra `pass` únicamente después de ejecutar y revisar cada ensayo,
incluyendo `rebase-accounts` desde un sistema anterior con una cuenta existente.
No copies evidencia de otro build o versión.

Revisa y conserva el JSON en `main`. Ejecuta manualmente **Promote reviewed
stable image** con digest, run y attempt exactos. La primera fase valida
procedencia, evidencia, firmas, versión y las protecciones reales de GitHub.
La segunda requiere aprobación en el entorno `stable`, repite las validaciones
y copia el mismo manifest sin reconstruirlo. Si el tag cambió durante la revisión
o el candidato baja de Fedora, la promoción se detiene.

No se incluyen registros de aprobación inventados. Un `stable` legado sin
procedencia suficiente o con una versión mayor que el candidato necesita una
migración revisada; el workflow no salta controles para reemplazarlo.
