---
description: Revisa N lotes de artistas nuevos (de podcasts recién incorporados) y deja propuestas de corrección
argument-hint: "[nº de lotes, por defecto 1] [artistas por lote, por defecto 25]"
---

Revisa lotes de la cola de artistas nuevos de este proyecto. Argumentos: `$ARGUMENTS`
(primer número = cuántos lotes, por defecto 1; segundo = artistas por lote, por defecto 25).

Contexto: `scripts/3_merge_resumenes.py` incorpora los podcasts nuevos y apunta en
`correcciones/cola_revision.txt` cada artista que ha tocado. Tú haces la revisión que
antes se habría pedido a la API: la respuesta la das tú en esta sesión.

Pasos:

1. `python3 scripts/limpieza/revisar_lote.py --esperando`. Si hay lotes preparados sin
   respuesta, revisa esos primero. Si faltan hasta llegar al número pedido, prepara el resto con
   `python3 scripts/limpieza/revisar_lote.py --lotes <n> --tam <tam>`.
   Si la cola está vacía, dilo y termina.
2. Para cada lote, lee `correcciones/lotes/lote_NNNN_prompt.md` entero. Contiene las reglas, el
   formato de respuesta, ejemplos y las fichas (las entradas con ★ son las nuevas; "Parecidos
   ya existentes" son posibles duplicados). Sigue esas reglas al pie de la letra.
   - Usa tu conocimiento musical para detectar nombres y títulos mal transcritos.
   - Si dudas de si un parecido es el mismo artista, puedes mirar su ficha
     (`data/artists/<slug>.md` o `pendiente/artists/<slug>.md`). No propongas nada dudoso.
   - No modifiques `data/`, `pendiente/` ni el fichero de decisiones directamente.
3. Escribe la respuesta en `correcciones/lotes/lote_NNNN_respuesta.md`: primera línea
   `DECISIONES` y después solo las líneas de decisión, cada una con `  # motivo`. Si no hay nada
   que corregir, escribe `SIN CAMBIOS`. Luego importa la respuesta:
   `python3 scripts/limpieza/revisar_lote.py --importar NNNN correcciones/lotes/lote_NNNN_respuesta.md`
4. Al terminar, enseña al usuario las propuestas de cada lote
   (`python3 scripts/limpieza/revisar_lote.py --ver NNNN`) de forma breve, destacando las que
   menos claras veas. Dile que puede aceptarlas o rechazarlas en el editor web (pestaña 🤖 Lotes)
   o aquí mismo.
   - Si te lo pide aquí, usa `--aceptar NNNN <ids|todas>` y `--rechazar NNNN <ids>`.
   - Después ejecuta `python3 scripts/limpieza/revisar_lote.py --aplicar` y
     `MUSIC_DATA_FOLDER=data python3 scripts/5_md_to_sqlite.py`.
   - Nunca aceptes ni apliques propuestas sin que el usuario lo diga.
5. Termina con `python3 scripts/limpieza/revisar_lote.py --estado` para mostrar cuánto queda en la
   cola.
