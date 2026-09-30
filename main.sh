#!/bin/bash
# Pipeline diario: podcasts nuevos → datos revisados.
#
# Variables opcionales:
#   LOTES_DIARIOS=2   lotes de revisión que se dejan preparados cada día (0 = ninguno).
#                     Aquí NO se llama a Claude: los revisas en una sesión de Claude Code
#                     con /revisar-lotes (o desde el editor web, pestaña 🤖 Lotes).
#   LOTE_TAM=25       artistas por lote

cd "$(dirname "$0")" || exit 1

# 1. Transcribir de MP3 a TXT (Whisper corre en local)
echo "--- Transcripción con Whisper ---"
#python3 scripts/1_audio_to_text.py

# 2. Generar resúmenes con Gemini
echo "--- Resúmenes con Gemini ---"
python3 scripts/2_gemini_resumen.py
# Si terminó con SystemExit(1) (p. ej. error 429 de cuota), se detiene el flujo
if [ $? -eq 1 ]; then
    echo "Límite de API alcanzado o error crítico. Deteniendo flujo diario."
    exit 1
fi

# 3. Borrar los MP3 ya transcritos
echo "--- Limpiando MP3 procesados ---"
python3 scripts/limpieza/borrar_mp3_escritos.py

# 4. Incorporar SOLO los resúmenes nuevos a data/ y pendiente/, aplicando las
#    decisiones de correcciones/decisiones_artistas.txt; lo tocado va a la cola
echo "--- Incorporando resúmenes nuevos ---"
python3 scripts/3_merge_resumenes.py || exit 1

# 5. Premios / charts / listas para los artistas que aún no los tienen
echo "--- Premios, charts y listas ---"
python3 scripts/4_awards_charts.py

# 6. Preparar lotes de revisión (se revisan luego con /revisar-lotes en Claude Code)
if [ "${LOTES_DIARIOS:-0}" -gt 0 ]; then
    echo "--- Preparando ${LOTES_DIARIOS} lote(s) de revisión ---"
    python3 scripts/limpieza/revisar_lote.py --lotes "${LOTES_DIARIOS}"
fi

# 7. Base de datos para el editor y la web
echo "--- Reconstruyendo la base de datos ---"
MUSIC_DATA_FOLDER=data python3 scripts/5_md_to_sqlite.py

echo "--- Proceso completado con éxito ---"
