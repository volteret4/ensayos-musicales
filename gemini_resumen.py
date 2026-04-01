import os
import shutil
from google import genai
from google.genai.errors import ClientError
from sops_env import load_sops_env
import requests

# 1. Configuración de la API
load_sops_env()
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

# Telegram credentials
TELEGRAM_BOT = os.environ['TELEGRAM_BOT']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage"
MENSAJE = "Se ha completado la realización de resumenes"

payload_end = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": MENSAJE
}


# Configuración de rutas
INPUT_FOLDER = './transcripts'
OUTPUT_FOLDER = './resumenes'

# Asegurar que la carpeta de salida existe
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def _generate_with_retry(prompt, diferencia, max_retries=5):
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(
                model='gemini-2.0-flash', # Actualizado a la versión estable actual
                contents=prompt
            )
        except ClientError as e:
            if e.code == 429:
                print("Rate limit alcanzado. Abortando el script.")
                MENSAJE_WORKING = f"Faltan {diferencia} artículos por resumir"
                payload_working = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": MENSAJE_WORKING
                }
                response = requests.post(TELEGRAM_URL, data=payload_working)

                raise SystemExit(1)
            else:
                raise

def summarize_files(folder_path):
    # Recorremos todas las subcarpetas de transcripts
    for root, dirs, files in os.walk(folder_path):
        # Evitar procesar archivos que ya están en la carpeta 'summarized'
        if 'summarized' in root:
            continue

        txt_files = [f for f in files if f.endswith('.txt')]

        for filename in txt_files:
            file_path = os.path.join(root, filename)

            # Determinar ruta relativa para replicar en 'resumenes'
            rel_path = os.path.relpath(root, folder_path)
            output_dir = os.path.join(OUTPUT_FOLDER, rel_path)
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(filename)[0]
            output_path = os.path.join(output_dir, f"{base_name}.md")

            if os.path.exists(output_path):
                print(f"--- Saltando: {filename} (ya resumido) ---")
                response = requests.post(TELEGRAM_URL, data=payload_end)
                continue

            print(f"--- Resumiendo: {os.path.join(rel_path, filename)} ---")

            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()

                if not content.strip(): continue

                prompt = f"""
                You are a renowned music historian and critic, an expert on artists, albums, genres, and musical events. Your task is to prepare a comprehensive document for an essay on music.

                Your goal is to extract all the interesting and relevant information from the following English text (for example, from the podcast *Ongoing History of New Music* by Alan Cross). You are not interested in basic data such as release dates or band formation/dissolution; look for in-depth information, trivia, anecdotes, myths, influences, musical style, cultural impact, collaborations, production details, song inspiration, artistic evolution, and any other information that might be useful for a detailed analysis.

                Produce a complete summary that includes:

                - Subheadings organizing the information (for example: “Album Context,” “Style and Sound,” “Trivia and Anecdotes,” “Cultural Impact,” “Collaborations,” “Related Events”).

                - Within each subheading, describe the relevant information clearly and in detail. Do not limit the number of bullet points; Prioritize richness and depth of information.

                Maintain an informative and academic, yet readable, tone.

                Text:

                {content}
                """

                # Contar archivos (ignora subdirectorios)
                num_archivos1 = len([f for f in os.listdir(rel_path) if os.path.isfile(os.path.join(rel_path, f))])
                num_archivos2 = len([f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))])

                # Diferencia
                diferencia = num_archivos1 - num_archivos2

                response = _generate_with_retry(prompt, diferencia)

                with open(output_path, 'w', encoding='utf-8') as out_f:
                    out_f.write(response.text)

                # Mover a 'summarized' dentro de la subcarpeta actual
                summarized_dir = os.path.join(root, 'summarized')
                os.makedirs(summarized_dir, exist_ok=True)
                shutil.move(file_path, os.path.join(summarized_dir, filename))

            except Exception as e:
                print(f"Error: {e}")

# 2. Ejecución
summarize_files(INPUT_FOLDER)
