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
                model='gemini-2.5-flash', # Actualizado a la versión estable actual
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
You are a renowned music historian and critic. Extract all musically significant information from the transcript and output it as structured data entries. Be exhaustive — do not summarize away details.

ENTRY FORMAT — one entry per line:

  __type__ @Artist Name **Descriptive Title** : description

For member entries specifically:

  __member__ @BandName @@MemberName **MemberName – Role** : description

ENTRY TYPES:
  artist, album, song, genre, event, venue, instrument, member, influence, curiosity

RULES:

1. @Artist is OPTIONAL — include only when the entry belongs clearly to a specific artist or band.
   - For collaborations: @Artist One, Artist Two
   - Band-level facts → @BandName  |  Individual facts → @MemberName
   - Omit @Artist for genres, broad historical events, venues, or curiosities not tied to one artist.

2. __member__ entries MUST use @BandName @@MemberName (both fields required):
   - @BandName  = the group they belong to
   - @@MemberName = the individual person (creates their own profile for solo work, side projects, etc.)
   - Example: __member__ @The Ramones @@Dee Dee Ramone **Dee Dee Ramone – Primary Songwriter** : Born Douglas Colvin, raised on US military bases in Germany. Wrote the majority of the Ramones catalogue. Heroin addiction was a constant destabilizing force.
   - Do NOT create __artist__ entries for band members. Their solo albums, songs, etc. go in the appropriate type tagged @MemberName.

3. **Descriptive Title** must be informative — never a bare name.
   GOOD: **Ramones (1976) – Debut Album**  |  **Dee Dee Ramone – Primary Songwriter**  |  **Roskilde 2000 – Fatal Crowd Crush**
   BAD:  **Ramones (1976)**                |  **Dee Dee Ramone**                        |  **Roskilde 2000**

4. description: specific, factual, detailed. Include dates, places, names, figures. No generic praise.

WHAT TO EXTRACT (be exhaustive):
- Artist biography, formation, breakup, lineup changes → artist, member entries
- Album/song recording details, production stories, chart performance, inspirations → album, song entries
- Musical influences and who they in turn influenced → influence entries
- Collaborations and guest appearances → song/album entries with multiple @artists
- Myths, controversies, anecdotes, behind-the-scenes stories → curiosity entries
- Gear, signature sounds, unique techniques → instrument entries
- Festivals, disasters, landmark concerts → event entries
- Genres and musical movements, their origins and defining traits → genre entries

OUTPUT RULES:
- You MAY add ## Section Headers for human readability (e.g., ## Albums, ## Members, ## Curiosities)
- Every non-header line must be a valid entry or blank — no prose paragraphs, no bullet points
- Do not invent any information not present in the source text

Text to process:

{content}
"""

                # Contar archivos (ignora subdirectorios)
                num_archivos1 = len([f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))])
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
