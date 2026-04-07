"""
convert_old_resumenes.py

Converts old-format summary files (flat __type__ **Title** : desc entries)
to the current structured markdown format (# artist - Name / ## section).

Input:  resumenes/ongoing_history_of_music/old_prompt/temp/*.md
Output: resumenes/ongoing_history_of_music/*.md  (same filenames)
"""

import os
import re
from google import genai
from google.genai.errors import ClientError
from sops_env import load_sops_env
import time

load_sops_env()
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

INPUT_FOLDER  = './resumenes/ongoing_history_of_music/old_prompt/temp'
OUTPUT_FOLDER = './resumenes/ongoing_history_of_music'

CONVERSION_PROMPT = """You are converting a music podcast summary from an old flat format to a structured format.

═══ OLD FORMAT ═══
The input contains flat entries like:
  *   __type__ **Title** : description
Where type can be: artist, album, song, genre, event, general music curiosity, organization, instrument, venue, collaborations, etc.

═══ NEW FORMAT ═══
Output structured markdown where each entity has its own section:

  # artist - Exact Artist Name

  ## members        one name per line (bare name)
  ## member of      one band name per line (bare name) — bands this artist belongs to
  ## genres         one genre per line (bare name)
  ## labels         one label per line (bare name)
  ## concerts       one concert or festival name per line (bare name)
  ## instruments    one instrument or gear item per line (bare name)
  ## albums         **Title (Year) – Subtitle** : description. "verbatim quote."
  ## songs          **Song Title (Year)** : description. "verbatim quote."
  ## curiosities    **Descriptive Title** : description. "verbatim quote."


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

═══ CONVERSION RULES ═══

1. GROUP entries by artist. If multiple entries mention the same artist, put them all under one # artist section.
2. For __artist__ entries: the title often IS the artist name or "Artist's thing" — create a # artist section and put the content as a ## curiosities entry.
3. For __album__ entries: find which artist they belong to from context, put under ## albums.
4. For __song__ entries: find which artist they belong to from context, put under ## songs.
5. For __genre__ entries: create # genre - GenreName sections. Extract the genre name from the entry title.
6. For __organization__ entries that are record labels: create # label - Name sections.
7. For __event__ entries tied to specific concerts or festivals: create # concert - Name sections.
8. For __event__ and __general music curiosity__ entries NOT tied to a specific artist, genre, label, or concert: put in # curiosity standalone section.
9. IGNORE completely: __podcast__, __social media__, __collaborations__ entries that are podcast self-promotion or meta-references about the podcast itself (e.g., "Art Context Podcast", "Architects Pods", host bios).
10. Descriptive titles must be INFORMATIVE:
    GOOD: **Ramones (1976) – Debut Album** | **MTV Launch (August 1981) – 24h Music Channel**
    BAD:  **Ramones (1976)**               | **MTV Launch**
11. Descriptions must preserve ALL specific details: dates, places, names, figures, cause-and-effect.
12. End EVERY albums/songs/curiosities entry with one short verbatim quote from the source text in quotation marks: "exact words from source."
13. Do NOT invent information not in the source.
14. Do NOT write prose paragraphs — only the structured entries above.

═══ INPUT TO CONVERT ═══

{content}
"""


def convert_file(filepath, output_path):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    if not content.strip():
        return

    prompt = CONVERSION_PROMPT.format(content=content)

    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            return
        except ClientError as e:
            if e.code == 429:
                print(f"  Rate limit. Esperando 60s...")
                time.sleep(60)
            else:
                raise
        except Exception as e:
            print(f"  Error en intento {attempt+1}: {e}")
            if attempt < 4:
                time.sleep(10)
            else:
                raise


def main():
    if not os.path.isdir(INPUT_FOLDER):
        print(f"No se encuentra {INPUT_FOLDER}")
        return

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.endswith('.md')])
    print(f"Convirtiendo {len(files)} archivos...\n")

    for i, filename in enumerate(files, 1):
        input_path  = os.path.join(INPUT_FOLDER, filename)
        output_path = os.path.join(OUTPUT_FOLDER, filename)

        if os.path.exists(output_path):
            print(f"[{i}/{len(files)}] Saltando (ya existe): {filename}")
            continue

        print(f"[{i}/{len(files)}] Convirtiendo: {filename}")
        try:
            convert_file(input_path, output_path)
            print(f"  → guardado en {output_path}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nConversión completada.")


if __name__ == '__main__':
    main()
