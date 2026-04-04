# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Goal

Build a pipeline that transcribes music podcasts, summarizes them into structured data, and eventually populates a SQLite database to power an interactive web map of music knowledge (artists, albums, genres, events, anecdotes).

## Running the Pipeline

```bash
# Full pipeline (transcribe → summarize → cleanup)
bash main.sh

# Individual steps
python3 audio_to_text.py      # Transcribe audio files in mp3_input/
python3 gemini_resumen.py     # Summarize transcripts via Gemini API
python3 borrar_mp3_escritos.py  # Delete processed MP3s and TXT files
```

The pipeline is idempotent: each script skips files that already have output.

## Secrets

All API keys are stored in `.encrypted.env` (encrypted with SOPS+age). To use them, call `load_sops_env()` from `sops_env.py` — this decrypts and injects vars into `os.environ`. Required vars: `GEMINI_API_KEY`, `TELEGRAM_BOT`, `TELEGRAM_CHAT_ID`.

`sops` CLI and an age key must be available for decryption to work.

## Data Flow

```
mp3_input/[subfolders]/podcast.mp3
  → audio_to_text.py (Whisper, local CPU)
  → transcripts/[subfolders]/podcast.txt

transcripts/[subfolders]/podcast.txt
  → gemini_resumen.py (Gemini 2.5 Flash)
  → resumenes/[subfolders]/podcast.md
  → (source txt moved to transcripts/[subfolders]/summarized/)

borrar_mp3_escritos.py
  → deletes mp3 when its .txt exists
  → deletes .txt when its .md exists
```

Subdirectory structure under `mp3_input/` is mirrored in `transcripts/` and `resumenes/`.

## Summary Format

`gemini_resumen.py` produces markdown with this entry format per fact:

```
__type__ **object** : description
```

Where `type` is one of: `artist`, `album`, `genre`, `event`, `general music curiosity`, `instrument`, etc. The `resumenes/` folder holds these files; two example outputs are at the repo root (`Rock's Greatest Disasters [...].md`, `The Original Ramones [...].md`).

## Python Environment

The project uses a local `.pyenv/` virtual environment. Key packages: `openai-whisper`, `google-genai`, `requests`. No `requirements.txt` — install via pip into `.pyenv/`.

## Full Pipeline

```bash
# After adding new audio to mp3_input/:
python3 audio_to_text.py      # → transcripts/*.txt
python3 gemini_resumen.py     # → resumenes/*.md  (moves processed txts to transcripts/summarized/)
python3 borrar_mp3_escritos.py  # deletes processed mp3s and txts

# Build the web map (run after resumenes/ has content):
python3 md_to_sqlite.py       # → music_facts.db
python3 sqlite_to_web.py      # → music_map.html
```

## md_to_sqlite.py

Walks `resumenes/` recursively, parses every line matching `__type__ **object** : description`, and inserts into a `facts` table in `music_facts.db`. Clears and rebuilds the DB on each run.

## sqlite_to_web.py

Reads `music_facts.db` and generates a self-contained `music_map.html` with a D3.js v7 force-directed graph. Nodes are unique `(type, object)` pairs, sized by number of facts and coloured by type. Edges connect objects that appear in the same source file. Clicking a node shows all its facts in a sidebar. Includes type-filter checkboxes and a search box.
