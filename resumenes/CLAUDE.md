# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Two-script pipeline that transcribes audio podcasts to text (English) and summarizes them (Spanish):

1. `audio_to_text.py` — Whisper-based transcription
2. `gemini_resumen.py` — Gemini API summarization

## Running the Scripts

```bash
# Activate the virtual environment first
source .pyenv/bin/activate

# Step 1: Transcribe audio files from mp3_input/ → transcripts/
python audio_to_text.py

# Step 2: Summarize transcripts from mp3_input/ → summary_*.txt
python gemini_resumen.py
```

No build, lint, or test commands exist — this is a minimal scripted project.

## Data Flow

```
mp3_input/*.{mp3,m4a,wav,opus}
        ↓ audio_to_text.py (Whisper "base", CPU, language=en)
transcripts/*.txt
        ↓ gemini_resumen.py (Gemini 2.0 Flash)
summary_<filename>.txt (saved in root)
```

## Key Behaviors

- **Transcription is idempotent**: skips files that already have a corresponding `.txt` in `transcripts/`
- **Whisper runs on CPU** (`fp16=False`) — intentional, no GPU required
- **Summaries are in Spanish**, 10 key bullet points per transcript
- The Gemini API key is hardcoded in `gemini_resumen.py` line 5 — use an env var if changing it

## Dependencies

Managed inside `.pyenv/` (Python 3.14.3 virtualenv). Key packages:
- `openai-whisper` — transcription
- `google-genai` — Gemini API client
- `torch` — required by Whisper
