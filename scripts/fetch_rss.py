#!/usr/bin/env python3
"""
fetch_rss.py — Descarga el feed RSS de un podcast y crea episodes.json.

episodes.json mapea títulos de episodios → URLs individuales para que
3_merge_resumenes.py pueda enlazar episodios concretos en vez del feed general.

Uso:
    python3 scripts/fetch_rss.py transcripts/mi_podcast/
    python3 scripts/fetch_rss.py                          # procesa todas las carpetas
    python3 scripts/fetch_rss.py --base transcripts/      # busca en otra carpeta raíz

Requisito en podcast.env:
    NAME=Lex Fridman Podcast
    RSS=https://lexfridman.com/feed/podcast/
"""

import argparse
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

TRANSCRIPTS_FOLDER = './transcripts'

# Namespaces RSS / Podcast
_NS = {
    'itunes':  'http://www.itunes.com/dtds/podcast-1.0.dtd',
    'podcast': 'https://podcastindex.org/namespace/1.0',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'atom':    'http://www.w3.org/2005/Atom',
}


# ── podcast.env ───────────────────────────────────────────────────────────────

def load_podcast_env(folder):
    """Lee podcast.env → (title, rss_url). Acepta URL= / RSS= / WEBSITE=."""
    env_path = os.path.join(folder, 'podcast.env')
    if not os.path.exists(env_path):
        return '', ''
    title = rss_url = ''
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            k, sep, v = line.strip().partition('=')
            if not sep:
                continue
            k = k.strip().upper()
            v = v.strip().strip('"').strip("'")
            if k in ('TITLE', 'NAME'):
                title = v
            elif k in ('URL', 'RSS', 'WEBSITE'):
                rss_url = v
    return title, rss_url


# ── Descarga y parseo RSS ─────────────────────────────────────────────────────

def fetch_feed(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'EnsayosMusicales/1.0 (rss-fetcher)',
        'Accept':     'application/rss+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _text(el):
    return el.text.strip() if el is not None and el.text else ''


def parse_feed(xml_bytes):
    """Parsea RSS → lista de dicts con title, url, audio_url, date, guid."""
    root = ET.fromstring(xml_bytes)
    # Registrar namespaces para que ElementTree los encuentre
    for prefix, uri in _NS.items():
        ET.register_namespace(prefix, uri)

    channel = root.find('channel')
    if channel is None:
        return []

    episodes = []
    for item in channel.findall('item'):
        title = _text(item.find('title'))
        if not title:
            continue

        # URL de la página del episodio (más útil que el audio directo para citar)
        link = _text(item.find('link'))

        # URL del audio (enclosure)
        enc = item.find('enclosure')
        audio_url = enc.get('url', '') if enc is not None else ''

        # Algunos feeds ponen la URL en atom:link
        if not link:
            atom_link = item.find(f'{{{_NS["atom"]}}}link')
            if atom_link is not None:
                link = atom_link.get('href', '')

        episode_url = link or audio_url

        date = _text(item.find('pubDate'))
        guid = _text(item.find('guid'))

        # Duración (itunes:duration) — opcional, útil para debug
        dur_el = item.find(f'{{{_NS["itunes"]}}}duration')
        duration = _text(dur_el) if dur_el is not None else ''

        episodes.append({
            'title':     title,
            'url':       episode_url,
            'audio_url': audio_url,
            'date':      date,
            'guid':      guid,
            'duration':  duration,
        })

    return episodes


# ── Procesado de carpeta ──────────────────────────────────────────────────────

def process_folder(folder):
    title, rss_url = load_podcast_env(folder)
    if not rss_url:
        print(f"  [{folder}] sin RSS= en podcast.env — saltando")
        return False

    out_path = os.path.join(folder, 'episodes.json')
    print(f"  Descargando: {rss_url}", end=' ', flush=True)
    try:
        xml_bytes = fetch_feed(rss_url)
        episodes  = parse_feed(xml_bytes)
    except Exception as e:
        print(f"→ error: {e}")
        return False

    data = {
        'feed_url':      rss_url,
        'podcast_title': title,
        'episodes':      episodes,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"→ {len(episodes)} episodios → {out_path}")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Descarga feeds RSS y genera episodes.json por carpeta'
    )
    parser.add_argument('folder', nargs='?',
                        help='Carpeta concreta (ej: transcripts/mi_podcast/)')
    parser.add_argument('--base', default=TRANSCRIPTS_FOLDER,
                        help=f'Carpeta raíz donde buscar subcarpetas (default: {TRANSCRIPTS_FOLDER})')
    args = parser.parse_args()

    if args.folder:
        process_folder(args.folder.rstrip('/'))
        return

    # Auto-descubrir carpetas con RSS= en podcast.env
    found = 0
    for root, dirs, files in os.walk(args.base):
        dirs.sort()
        if 'podcast.env' not in files:
            continue
        _, rss_url = load_podcast_env(root)
        if not rss_url:
            continue
        found += 1
        process_folder(root)

    if not found:
        print(f"No se encontraron carpetas con RSS= en {args.base}")
        print("Crea un podcast.env con:  RSS=https://tu-podcast.com/feed.xml")


if __name__ == '__main__':
    main()
