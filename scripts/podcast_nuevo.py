#!/usr/bin/env python3
"""
podcast_nuevo.py — De una URL (vídeo, lista o canal de YouTube, o feed RSS de un podcast) a resúmenes.

  1. Descarga el audio con yt-dlp en mp3_input/<carpeta>/ (con archivo de descargas: no repite).
  2. Lo transcribe con Whisper en local → transcripts/<carpeta>/<título>.txt
  3. Extrae los datos con Claude (claude -p) en vez de Gemini, con el mismo prompt que
     2_gemini_resumen.py → resumenes/<carpeta>/<título>.md, y mueve el .txt a summarized/.

Cada paso se salta lo que ya está hecho, así que se puede cortar y relanzar. Después, main.sh
(atuin scripts run ensayos) incorpora los resúmenes y reconstruye music_facts.db; Gemini ya no
encuentra nada que resumir.

Uso (desde la raíz del proyecto, con el python del venv que tenga openai-whisper):
    python scripts/podcast_nuevo.py URL CARPETA [--nombre "Nombre bonito"] [--max 10]
    python scripts/podcast_nuevo.py --solo-resumir [CARPETA]   # transcripciones ya hechas (sin carpeta: todas)
Variables: WHISPER_MODEL (base), WHISPER_LANG (autodetecta), CLAUDE_MODEL (el de claude por defecto).
"""

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP3 = os.path.join(ROOT, 'mp3_input')
TRANSCRIPTS = os.path.join(ROOT, 'transcripts')
RESUMENES = os.path.join(ROOT, 'resumenes')
AUDIO_EXT = ('.mp3', '.m4a', '.wav', '.opus')


def is_youtube(url):
    return re.search(r'(youtube\.com|youtu\.be)/', url) is not None


# ── 0. podcast.env ────────────────────────────────────────────────────────────

def write_podcast_env(carpeta, url, nombre):
    """Crea transcripts/<carpeta>/podcast.env si no existe (lo lee 3_merge_resumenes.py)."""
    folder = os.path.join(TRANSCRIPTS, carpeta)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'podcast.env')
    if os.path.exists(path):
        return
    key = 'YT_PLAYLIST' if 'list=' in url else 'URL'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'NAME={nombre or carpeta}\n{key}={url}\n')
    print(f'Creado {os.path.relpath(path, ROOT)}')
    if not is_youtube(url):
        # Feed RSS: episodes.json para enlazar cada episodio y no el feed entero.
        subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'fetch_rss.py'), folder], cwd=ROOT)


# ── 1. Descarga ───────────────────────────────────────────────────────────────

def download(url, carpeta, max_items):
    out = os.path.join(MP3, carpeta)
    os.makedirs(out, exist_ok=True)
    # Los de YouTube llevan el id en el nombre: así se enlaza cada nota a su episodio.
    name = '%(title)s [%(id)s].%(ext)s' if is_youtube(url) else '%(title)s.%(ext)s'
    cmd = ['yt-dlp', '--extract-audio', '--audio-format', 'mp3', '--ignore-errors',
           '--download-archive', os.path.join(out, f'{carpeta}.log'), '-o', os.path.join(out, name)]
    if max_items:
        cmd += ['--playlist-end', str(max_items)]
    print(f'--- Descargando en mp3_input/{carpeta}/ ---', flush=True)
    subprocess.run(cmd + [url])


# ── 2. Transcripción ──────────────────────────────────────────────────────────

def transcribe(carpeta):
    src = os.path.join(MP3, carpeta)
    dst = os.path.join(TRANSCRIPTS, carpeta)
    done_dir = os.path.join(dst, 'summarized')
    todo = []
    for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        base, ext = os.path.splitext(f)
        if ext.lower() not in AUDIO_EXT:
            continue
        if any(os.path.exists(p) for p in (os.path.join(dst, base + '.txt'), os.path.join(done_dir, base + '.txt'),
                                           os.path.join(RESUMENES, carpeta, base + '.md'))):
            continue
        todo.append(f)
    if not todo:
        print('--- Nada nuevo que transcribir ---')
        return
    try:
        import whisper
    except ImportError:
        sys.exit('Falta Whisper en este python: pip install openai-whisper '
                 '(en el venv: ~/Scripts/python_venv/bin/pip install openai-whisper)')
    model_name = os.environ.get('WHISPER_MODEL', 'base')
    print(f'--- Transcribiendo {len(todo)} audio(s) con Whisper {model_name} ---', flush=True)
    model = whisper.load_model(model_name, device='cpu')
    os.makedirs(dst, exist_ok=True)
    for i, f in enumerate(todo, 1):
        print(f'[{i}/{len(todo)}] {f}', flush=True)
        try:
            r = model.transcribe(os.path.join(src, f), language=os.environ.get('WHISPER_LANG') or None, fp16=False)
        except Exception as e:  # un audio roto no para el resto
            print(f'  Error: {e}')
            continue
        with open(os.path.join(dst, os.path.splitext(f)[0] + '.txt'), 'w', encoding='utf-8') as out:
            out.write(r['text'])


# ── 3. Extracción con Claude ──────────────────────────────────────────────────

def load_prompt():
    """PROMPT_TEMPLATE de 2_gemini_resumen.py, sin ejecutarlo (rota claves al importarse).
    Su filtro es el del presentador de Ongoing History; aquí vale para el de cualquier podcast."""
    with open(os.path.join(ROOT, 'scripts', '2_gemini_resumen.py'), encoding='utf-8') as f:
        tree = ast.parse(f.read())
    prompt = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                  and any(getattr(t, 'id', '') == 'PROMPT_TEMPLATE' for t in n.targets))
    prompt = re.sub(r'IGNORE completely any sentence.*?podcast itself\.',
                    'IGNORE the podcast host(s) themselves: do not extract host commentary, personal opinions '
                    'introduced by the host, sponsor reads, or meta-references to the podcast itself.',
                    prompt, flags=re.S)
    return prompt.replace('Do NOT mention Alan Cross or the podcast host', 'Do NOT mention the podcast host')


def claude(prompt):
    cmd = ['claude', '-p', '--tools', '', '--no-session-persistence', '--strict-mcp-config']
    if os.environ.get('CLAUDE_MODEL'):
        cmd += ['--model', os.environ['CLAUDE_MODEL']]
    # Fuera del proyecto, para que no cargue ningún CLAUDE.md.
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(cmd, input=prompt, text=True, capture_output=True, cwd=tmp, timeout=1800)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError((r.stderr or r.stdout).strip()[-500:] or f'código {r.returncode}')
    return r.stdout.strip() + '\n'


def summarize(carpeta):
    src = os.path.join(TRANSCRIPTS, carpeta)
    dst = os.path.join(RESUMENES, carpeta)
    done_dir = os.path.join(src, 'summarized')
    files = sorted(f for f in os.listdir(src) if f.endswith('.txt')) if os.path.isdir(src) else []
    if not files:
        print(f'--- {carpeta}: nada nuevo que resumir ---')
        return
    prompt = load_prompt()
    os.makedirs(dst, exist_ok=True)
    os.makedirs(done_dir, exist_ok=True)
    print(f'--- {carpeta}: extrayendo datos de {len(files)} transcripción(es) con Claude ---', flush=True)
    for i, f in enumerate(files, 1):
        path = os.path.join(src, f)
        out = os.path.join(dst, os.path.splitext(f)[0] + '.md')
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
        if not text.strip():
            continue
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            print(f'[{i}/{len(files)}] {f}', flush=True)
            try:
                md = claude(prompt.format(content=text))
            except Exception as e:  # límite de uso, red…: se reintenta al relanzar
                print(f'  Error: {e}')
                if 'limit' in str(e).lower():
                    sys.exit('Límite de uso de Claude: relanza más tarde (sigue donde iba).')
                continue
            with open(out, 'w', encoding='utf-8') as fh:
                fh.write(md)
        shutil.move(path, os.path.join(done_dir, f))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('url', nargs='?', help='vídeo, lista o canal de YouTube, o feed RSS')
    ap.add_argument('carpeta', nargs='?', help='carpeta del podcast en mp3_input/, transcripts/ y resumenes/')
    ap.add_argument('--nombre', help='nombre del podcast (podcast.env); por defecto, la carpeta')
    ap.add_argument('--max', type=int, help='descargar como mucho N episodios (los primeros de la lista)')
    ap.add_argument('--solo-resumir', action='store_true', help='solo el paso 3, con lo ya transcrito')
    a = ap.parse_args()
    if a.solo_resumir:
        # Con un solo argumento, argparse lo toma como url: es la carpeta.
        carpeta = a.carpeta or a.url
        for c in [carpeta] if carpeta else sorted(d for d in os.listdir(TRANSCRIPTS) if d != 'summarized'
                                                   and os.path.isdir(os.path.join(TRANSCRIPTS, d))):
            summarize(c.strip().strip('/'))
    else:
        if not a.url or not a.carpeta:
            ap.error('faltan la URL y la carpeta')
        carpeta = a.carpeta.strip().strip('/')
        write_podcast_env(carpeta, a.url, a.nombre)
        download(a.url, carpeta, a.max)
        transcribe(carpeta)
        summarize(carpeta)
    print('--- Listo. Siguiente: atuin scripts run ensayos ---')


if __name__ == '__main__':
    main()
