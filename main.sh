#!/bin/bash

# Acceder a la carpeta del proyecto (ajusta la ruta a tu caso real)
cd "$HOME"/gits/pollo/podcast_to_text || echo "no existe la carpeta"

# 1. Transcribir de MP3 a TXT (Whisper corre en local, no suele tener límite de API)
echo "--- Iniciando Transcripción con Whisper ---"
#python3 audio_to_text.py

# 2. Generar resúmenes con Gemini
echo "--- Iniciando Resúmenes con Gemini ---"
python3 gemini_resumen.py

# Capturar el código de salida de Gemini
# Si el script terminó con SystemExit(1) por el error 429, el valor será 1
if [ $? -eq 1 ]; then
    echo "Límite de API alcanzado o error crítico. Deteniendo flujo diario."
    exit 1
fi

# 3. Limpiar archivos MP3 procesados (solo si los anteriores terminaron bien)
echo "--- Limpiando archivos MP3 procesados ---"
python3 borrar_mp3_escritos.py

echo "--- Proceso completado con éxito ---"
