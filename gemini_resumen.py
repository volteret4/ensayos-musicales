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
You are a renowned music historian and critic. Extract all musically significant information from the transcript and output it as structured markdown. Be exhaustive — preserve every detail, anecdote, date, name, and figure mentioned.

═══ FILTER ═══

IGNORE completely any sentence or passage that mentions "Alan Cross" (the host). Do not extract host commentary, personal opinions introduced by the host, or meta-references to the podcast itself.

═══ STRUCTURE ═══

For each artist or band with meaningful coverage, open a section:

  # artist - Exact Artist Name

Then add ONLY the subsections for which you have real data:

  ## members        one name per line (bare name, no formatting)
  ## member of      one band name per line (bare name) — bands this artist belongs to
  ## genres         one genre per line (bare name)
  ## labels         one label per line (bare name)
  ## concerts       one concert or festival name per line (bare name)
  ## instruments    one instrument or gear item per line (bare name)
  ## albums         one entry per line: **Title (Year) – Subtitle** : description
  ## songs          one entry per line: **Song Title (Year)** : description
  ## curiosities    one entry per line: **Descriptive Title** : description

═══ ENTRY FORMAT ═══

For ## members / member of / genres / labels / concerts / instruments — just the name, one per line:

  John Lennon
  Punk Rock
  EMI Records
  Woodstock 1969

For ## albums / songs / curiosities — one entry per line:

  **Descriptive Title** : full description

Title must be INFORMATIVE, never a bare name:
  GOOD: **Abbey Road (1969) – Final Studio Album**  |  **Come Together (1969)**  |  **Ed Sullivan Debut – 73 Million Viewers**
  BAD:  **Abbey Road**                              |  **Come Together**         |  **Ed Sullivan**

Description must be RICH and COMPLETE — write everything the transcript says about it:
  - Include all dates, cities, chart positions, sales figures, real names, studio names
  - Include cause-and-effect context: why something happened, what led to it, what it caused
  - Include comparisons and influences mentioned
  - Aim for 2–5 sentences per entry. Do NOT truncate or summarise — if the transcript gives detail, keep it.
  - No generic praise ("groundbreaking", "iconic") unless the transcript itself uses those words
  - End EVERY albums/songs/curiosities entry with one short verbatim quote from the transcript that captures the core idea, formatted as: "exact words from transcript."

═══ WHAT TO EXTRACT ═══

  ## members:       lineup at relevant period, key changes, who joined or left and when, and why
  ## member of:     bands or supergroups this person is or was a member of
  ## albums:        recording context, studio, producers, chart performance, cultural impact, sales
  ## songs:         origin story, full meaning, recording anecdotes, chart positions, live history, covers
  ## curiosities:   scandals, controversies, historical firsts, behind-the-scenes stories, personal details
  ## instruments:   signature gear, custom tunings, recording techniques, studio equipment and how used
  ## genres:        just list genre names — factual prose goes in standalone # genre sections
  ## labels:        just list label names — factual prose goes in standalone # label sections
  ## concerts:      specific concerts or festivals attended/performed — factual prose goes in standalone # concert sections

═══ STANDALONE SECTIONS (at end of file) ═══

After all artist sections, add sections for entities NOT tied to a single artist:

  # genre - Genre Name

  ## curiosities
  **Descriptive Title** : description. "verbatim quote."


  # label - Label Name

  ## curiosities
  **Descriptive Title** : description. "verbatim quote."


  # concert - Concert or Festival Name

  ## curiosities
  **Descriptive Title** : description. "verbatim quote."


  # instrument - Instrument Name

  ## curiosities
  **Descriptive Title** : description. "verbatim quote."


  # curiosity

  **Descriptive Title** : description. "verbatim quote."
  **Another Title** : description. "verbatim quote."

Use # curiosity (no name) for facts that do NOT belong to any single artist, genre, label, concert, or instrument.

═══ RULES ═══

- Multiple artists in one file is fine — start each with # artist - Name
- Do NOT create a section if you have no real data for it
- Do NOT invent information not present in the source text
- Do NOT write prose paragraphs — only entries in the formats above
- Do NOT mention Alan Cross or the podcast host under any section
- The verbatim quote must be words actually spoken/written in the transcript — do NOT paraphrase or invent


Text to process:

{content}
"""

                # Contar archivos (ignora subdirectorios)
                num_transcripts = len([f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))])
                # num_resumenes = len([f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))])

                # Diferencia
                # diferencia = num_transcripts - num_resumenes

                response = _generate_with_retry(prompt, num_transcripts)

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
