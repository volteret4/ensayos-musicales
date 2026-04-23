import os
import shutil

# Definir las rutas de las carpetas
carpeta1 = 'ongoing_history_old'
carpeta2 = 'resumenes/ongoing_history_of_music'

# Listar los archivos en ambas carpetas
archivos_carpeta1 = set(os.listdir(carpeta1))
archivos_carpeta2 = set(os.listdir(carpeta2))

# Encontrar archivos duplicados
duplicados = archivos_carpeta1.intersection(archivos_carpeta2)

# Eliminar los duplicados de la carpeta 1
for archivo in duplicados:
    ruta_archivo = os.path.join(carpeta1, archivo)
    if os.path.isfile(ruta_archivo):
        os.remove(ruta_archivo)
        print(f"Archivo eliminado: {archivo}")
    else:
        print(f"No se encontró el archivo: {archivo}")
