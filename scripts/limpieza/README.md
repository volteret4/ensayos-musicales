# Limpieza y revisión de artistas

## Piezas

| Fichero | Qué es |
|---|---|
| `correcciones/decisiones_artistas.txt` | Todas las correcciones, una por línea (formato al principio del fichero). Es la fuente de verdad: se aplica a todo lo que entra. |
| `correcciones/resumenes_procesados.txt` | Resúmenes ya incorporados a `data/`/`pendiente/` (el merge solo lee los nuevos). |
| `correcciones/cola_revision.txt` | Artistas tocados por podcasts nuevos, pendientes de revisar (un JSON por línea). |
| `correcciones/lotes/lote_NNNN.txt` | Cada consulta a Claude: artistas, prompt, respuesta y propuestas con su estado. |
| `correcciones/INFORME_limpieza.md` | Informe de la última aplicación de decisiones. |

## Flujo diario

1. `main.sh` transcribe, resume y ejecuta `scripts/3_merge_resumenes.py`: añade lo nuevo
   (ya corregido con las decisiones existentes) y apunta cada artista tocado en la cola.
2. Revisión por lotes, **en una sesión de Claude Code con tu plan** (no se usa la API de pago):
   abre Claude Code en este repo y escribe `/revisar-lotes 3` (3 lotes de 25 artistas;
   `/revisar-lotes 2 40` para 2 lotes de 40). Claude prepara los lotes, los revisa en la
   conversación, importa sus propuestas y te las enseña. Alternativas: «📋 Preparar lote» en el
   editor web y pegar el prompt en claude.ai; `LOTES_DIARIOS=2 ./main.sh` los deja preparados.
3. Aceptas, editas o rechazas cada propuesta en el editor web (pestaña **🤖 Lotes**) o en la
   misma sesión («acepta todas menos la 3»). «Aplicar aceptadas» (o `revisar_lote.py --aplicar`)
   las pasa al fichero de decisiones, reaplica la limpieza sobre `data/` y `pendiente/` y
   reconstruye la BD.

Las ediciones hechas a mano en el editor (renombrar, fusionar o borrar artistas, borrar o
retitular entradas, quitar miembros) también se guardan como decisiones, en bloques
`### editor web (fecha)`, para que los podcasts futuros se corrijan igual.

## Comandos útiles

```bash
python3 scripts/limpieza/revisar_lote.py --estado
```

```bash
python3 scripts/limpieza/revisar_lote.py --ver 3
```

```bash
python3 scripts/limpieza/revisar_lote.py --aceptar 3 todas
```

```bash
python3 scripts/limpieza/revisar_lote.py --aplicar
```

```bash
python3 scripts/limpieza/limpiar_artistas.py --in-place
```

`limpiar_artistas.py` es idempotente (≈3 s): se puede lanzar siempre que se edite a mano el
fichero de decisiones. Sin `--in-place` genera una copia en `limpio/` para comparar.

Consumo orientativo: un lote de 10 artistas son unos 11 000 tokens de prompt; 25 artistas,
unos 25 000–30 000. El cupo de tu plan marca cuántos lotes caben al día.
