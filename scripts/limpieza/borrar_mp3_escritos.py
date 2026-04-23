import os
import fnmatch

ruta_txt_root = "./transcripts"
ruta_mp3_root = "./mp3_input"
ruta_to_resumenes = "./resumenes"
patrones_ignorar = ["CLAUDE.md", "README.md", "*-claude.md"]

for root, dirs, files in os.walk(ruta_txt_root):
    for archivo in files:
        if any(fnmatch.fnmatch(archivo, patron) for patron in patrones_ignorar):
            continue

        if archivo.endswith(".txt"):
            ruta_archivo_txt = os.path.join(root, archivo)

            if os.path.getsize(ruta_archivo_txt) > 0:
                # Obtener la subcarpeta relativa (ej: "Jazz/MilesDavis")
                rel_path = os.path.relpath(root, ruta_txt_root)
                nombre_base = os.path.splitext(archivo)[0]

                # Buscar el mp3 en la misma subcarpeta de mp3_input
                archivo_mp3 = nombre_base + ".mp3"
                ruta_archivo_mp3 = os.path.join(ruta_mp3_root, rel_path, archivo_mp3)

                if os.path.exists(ruta_archivo_mp3):
                    os.remove(ruta_archivo_mp3)
                    print(f"Eliminado: {ruta_archivo_mp3}")



for root, dirs, files in os.walk(ruta_to_resumenes):
    for archivo in files:
        if any(fnmatch.fnmatch(archivo, patron) for patron in patrones_ignorar):
            continue
        if archivo.endswith(".md"):
            ruta_archivo_md = os.path.join(root, archivo)

            if os.path.getsize(ruta_archivo_md) > 0:
                # Obtener la subcarpeta relativa (ej: "Jazz/MilesDavis")
                rel_path = os.path.relpath(root, ruta_to_resumenes)
                nombre_base = os.path.splitext(archivo)[0]

                # Buscar el txt en la misma subcarpeta de transcripts
                archivo_txt = nombre_base + ".txt"
                ruta_archivo_txt = os.path.join(ruta_txt_root, rel_path, archivo_txt)

                if os.path.exists(ruta_archivo_txt):
                    os.remove(ruta_archivo_txt)
                    print(f"Eliminado: {ruta_archivo_txt}")
