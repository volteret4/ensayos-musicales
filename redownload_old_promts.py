import os
import re

# Ruta de la carpeta con los .md
carpeta_md = "./resumenes/ongoing_history_of_music/old_prompt/old_prompt"

# Archivo con las líneas a limpiar
archivo_lista = "./mp3_input/ongoing_history_of_music/podcast_music_history.log"

# 1. Obtener todos los IDs desde los nombres de archivos .md
ids = set()

for root, dirs, files in os.walk(carpeta_md):
    for file in files:
        if file.endswith(".md"):
            match = re.search(r'\[([a-zA-Z0-9_-]{11})\]', file)
            if match:
                ids.add(match.group(1))

# 2. Leer archivo y filtrar líneas
with open(archivo_lista, "r", encoding="utf-8") as f:
    lineas = f.readlines()

lineas_filtradas = []
for linea in lineas:
    match = re.search(r'youtube\s+([a-zA-Z0-9_-]{11})', linea)
    if match:
        if match.group(1) not in ids:
            lineas_filtradas.append(linea)
    else:
        lineas_filtradas.append(linea)

# 3. Sobrescribir archivo (o guardar en otro)
with open(archivo_lista, "w", encoding="utf-8") as f:
    f.writelines(lineas_filtradas)

print("Limpieza completada.")
