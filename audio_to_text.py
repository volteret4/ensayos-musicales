import whisper
import os

# --- CONFIGURACIÓN DE RUTAS ---
TRANSCRIPTS_FOLDER = 'transcripts'
RESUMENES_FOLDER = 'resumenes'
INPUT_FOLDER = "./mp3_input"

os.makedirs(TRANSCRIPTS_FOLDER, exist_ok=True)
os.makedirs(RESUMENES_FOLDER, exist_ok=True)

def transcribir_podcasts(directorio_entrada):
    device = "cpu"
    print(f"Cargando modelo en {device.upper()}...")
    model = whisper.load_model("base", device=device)
    extensiones = ('.mp3', '.m4a', '.wav', '.opus')

    # Usamos os.walk para recorrer subcarpetas
    for root, dirs, files in os.walk(directorio_entrada):
        for archivo in files:
            if archivo.lower().endswith(extensiones):
                # Calcular la ruta relativa (ej: "Rock/PinkFloyd")
                rel_path = os.path.relpath(root, directorio_entrada)

                # Definir rutas de salida manteniendo la estructura
                target_txt_dir = os.path.join(TRANSCRIPTS_FOLDER, rel_path)
                target_md_dir = os.path.join(RESUMENES_FOLDER, rel_path)

                os.makedirs(target_txt_dir, exist_ok=True)
                os.makedirs(target_md_dir, exist_ok=True)

                base_name = os.path.splitext(archivo)[0]
                ruta_txt = os.path.join(target_txt_dir, base_name + ".txt")
                ruta_md = os.path.join(target_md_dir, base_name + ".md")

                if os.path.exists(ruta_txt) or os.path.exists(ruta_md):
                    print(f"--- Saltando {archivo}: ya existe transcripción o resumen. ---")
                    continue

                print(f"Procesando: {os.path.join(rel_path, archivo)}...")
                try:
                    resultado = model.transcribe(os.path.join(root, archivo), language="en", fp16=False)
                    with open(ruta_txt, "w", encoding="utf-8") as f:
                        f.write(resultado["text"])
                    print(f"  ✓ Transcripción guardada.")
                except Exception as e:
                    print(f"  Error: {e}")

transcribir_podcasts(INPUT_FOLDER)
