"""
artist_page.py

Genera markdown_style.html — enciclopedia de artistas con todos los datos
de music_facts.db en un formato limpio y legible con búsqueda integrada.
"""

import json
import os
import sqlite3

DB_PATH  = 'music_facts.db'
OUT_HTML = 'markdown_style.html'

SECTION_COLORS = {
    'members':     '#e67e22',
    'genres':      '#2ecc71',
    'labels':      '#f39c12',
    'concerts':    '#1abc9c',
    'instruments': '#9b59b6',
    'albums':      '#3498db',
    'songs':       '#5dade2',
    'curiosities': '#95a5a6',
}

SECTION_LABELS = {
    'members':     'Miembros',
    'genres':      'Géneros',
    'labels':      'Sellos',
    'concerts':    'Conciertos',
    'instruments': 'Instrumentos',
    'albums':      'Álbumes',
    'songs':       'Canciones',
    'curiosities': 'Curiosidades',
}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)
    all_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # All artists (primary + members, to resolve names for links)
    all_artists = {}
    for aid, name, is_primary in conn.execute(
        'SELECT id, name, is_primary FROM artists ORDER BY name'
    ):
        all_artists[aid] = {
            'id': aid, 'name': name, 'is_primary': bool(is_primary),
            'member_of': [], 'members': [],
            'genres': [], 'labels': [], 'concerts': [], 'instruments': [],
            'albums': [], 'songs': [], 'curiosities': [],
        }

    # Band members
    if 'band_members' in all_tables:
        for band_id, member_id in conn.execute('SELECT band_id, member_id FROM band_members'):
            if band_id in all_artists and member_id in all_artists:
                all_artists[band_id]['members'].append(
                    {'id': member_id, 'name': all_artists[member_id]['name']}
                )
                all_artists[member_id]['member_of'].append(
                    {'id': band_id, 'name': all_artists[band_id]['name']}
                )

    # Association tables
    assoc = [
        ('genres',      'artist_genres',     'genres',      'genre_id'),
        ('labels',      'artist_labels',     'labels',      'label_id'),
        ('concerts',    'artist_concerts',   'concerts',    'concert_id'),
        ('instruments', 'artist_instruments','instruments', 'instrument_id'),
    ]
    for field, junc, etable, fk in assoc:
        if junc not in all_tables:
            continue
        for aid, name in conn.execute(
            f'SELECT j.artist_id, e.name FROM {junc} j JOIN {etable} e ON j.{fk}=e.id ORDER BY e.name'
        ):
            if aid in all_artists:
                all_artists[aid][field].append(name)

    # Albums
    if 'albums' in all_tables and 'albums_data' in all_tables:
        album_buf = {}
        for album_id, name, artist_id in conn.execute(
            'SELECT id, name, artist_id FROM albums ORDER BY name'
        ):
            if artist_id in all_artists:
                album_buf[album_id] = {'artist_id': artist_id, 'name': name, 'facts': []}
        for album_id, desc, sf in conn.execute(
            'SELECT album_id, description, source_file FROM albums_data'
        ):
            if album_id in album_buf:
                album_buf[album_id]['facts'].append({'description': desc, 'source_file': sf or ''})
        for al in album_buf.values():
            all_artists[al['artist_id']]['albums'].append({'name': al['name'], 'facts': al['facts']})

    # Songs
    if 'songs' in all_tables and 'songs_data' in all_tables:
        song_buf = {}
        for song_id, name, artist_id in conn.execute(
            'SELECT id, name, artist_id FROM songs ORDER BY name'
        ):
            if artist_id in all_artists:
                song_buf[song_id] = {'artist_id': artist_id, 'name': name, 'facts': []}
        for song_id, desc, sf in conn.execute(
            'SELECT song_id, description, source_file FROM songs_data'
        ):
            if song_id in song_buf:
                song_buf[song_id]['facts'].append({'description': desc, 'source_file': sf or ''})
        for sg in song_buf.values():
            all_artists[sg['artist_id']]['songs'].append({'name': sg['name'], 'facts': sg['facts']})

    # Artist curiosities
    if 'curiosities' in all_tables:
        for title, desc, sf, ctx_id in conn.execute(
            "SELECT title, description, source_file, context_id "
            "FROM curiosities WHERE context_type='artist' ORDER BY title"
        ):
            if ctx_id in all_artists:
                all_artists[ctx_id]['curiosities'].append(
                    {'name': title, 'facts': [{'description': desc, 'source_file': sf or ''}]}
                )

    conn.close()

    primary = sorted(
        [a for a in all_artists.values() if a['is_primary']],
        key=lambda x: x['name'].lstrip('The ').lstrip('Los ').lstrip('Las '),
    )
    # Also pass name→id map for linkification
    name_to_id = {a['name']: a['id'] for a in all_artists.values() if a['is_primary']}
    return primary, name_to_id


# ── HTML template ──────────────────────────────────────────────────────────────

CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, sans-serif; background: #0d1117;
       color: #c9d1d9; display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ── */
#sidebar { width: 260px; min-width: 200px; background: #161b22;
           border-right: 1px solid #30363d; display: flex; flex-direction: column;
           flex-shrink: 0; }

#search-wrap { padding: 12px; border-bottom: 1px solid #30363d; }
#search { width: 100%; padding: 7px 10px; background: #0d1117; color: #c9d1d9;
          border: 1px solid #30363d; border-radius: 6px; font-size: 0.85rem;
          outline: none; }
#search:focus { border-color: #58a6ff; }
#search::placeholder { color: #484f58; }

#artist-list { flex: 1; overflow-y: auto; padding: 6px 0; }
.artist-item { padding: 7px 16px; font-size: 0.85rem; cursor: pointer;
               border-left: 3px solid transparent; color: #8b949e;
               transition: all 0.1s; white-space: nowrap; overflow: hidden;
               text-overflow: ellipsis; }
.artist-item:hover { background: #1c2128; color: #c9d1d9; border-left-color: #30363d; }
.artist-item.active { background: #1c2128; color: #58a6ff;
                      border-left-color: #58a6ff; font-weight: 600; }
.artist-item mark { background: none; color: #f0883e; font-weight: bold; }
#count-label { padding: 6px 16px; font-size: 0.72rem; color: #484f58; }

/* ── Content ── */
#content { flex: 1; overflow-y: auto; padding: 32px 40px; }

#placeholder { display: flex; align-items: center; justify-content: center;
               height: 100%; color: #484f58; font-size: 1rem; }

#artist-detail { max-width: 800px; }

#artist-detail h1 { font-size: 2rem; font-weight: 700; color: #e6edf3;
                    margin-bottom: 4px; line-height: 1.2; }
.member-of-line { font-size: 0.85rem; color: #8b949e; margin-bottom: 20px; }
.member-of-line a { color: #58a6ff; text-decoration: none; cursor: pointer; }
.member-of-line a:hover { text-decoration: underline; }

.section { margin-bottom: 28px; }
.section-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
                 text-transform: uppercase; margin-bottom: 10px;
                 padding-bottom: 6px; border-bottom: 1px solid #21262d; }

/* Tags (members, genres, labels, venues, instruments) */
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { display: inline-block; padding: 3px 10px; border-radius: 20px;
       font-size: 0.78rem; border: 1px solid; cursor: default; }
.tag.clickable { cursor: pointer; }
.tag.clickable:hover { opacity: 0.8; filter: brightness(1.2); }

/* Cards (albums, songs, curiosities) */
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
        padding: 14px 16px; margin-bottom: 10px; border-left: 3px solid; }
.card-title { font-size: 0.9rem; font-weight: 600; color: #e6edf3;
              margin-bottom: 6px; }
.card-desc { font-size: 0.85rem; line-height: 1.6; color: #8b949e; }
.card-source { margin-top: 8px; font-size: 0.72rem; }
.card-source a { color: #388bfd; text-decoration: none; }
.card-source a:hover { text-decoration: underline; }
.card-source span { color: #484f58; }

.artist-link { color: #f0883e; font-weight: 600; cursor: pointer;
               text-decoration: none; border-bottom: 1px dotted #f0883e; }
.artist-link:hover { color: #ffa657; border-bottom-color: #ffa657; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
'''

JS = r'''
const ARTISTS      = /*ARTISTS*/[];
const NAME_TO_ID   = /*NAME_TO_ID*/{};
const SEC_COLORS   = /*SEC_COLORS*/{};
const SEC_LABELS   = /*SEC_LABELS*/{};

// Index for fast lookup by id
const byId = {};
ARTISTS.forEach(a => { byId[a.id] = a; });

// ── Sidebar list ─────────────────────────────────────────────────────────────
const searchEl  = document.getElementById('search');
const listEl    = document.getElementById('artist-list');
const countEl   = document.getElementById('count-label');
let   activeId  = null;

function renderList(q) {
  const qL = q.toLowerCase();
  listEl.innerHTML = '';
  let count = 0;
  for (const a of ARTISTS) {
    if (q && !a.name.toLowerCase().includes(qL)) continue;
    count++;
    const div = document.createElement('div');
    div.className = 'artist-item' + (a.id === activeId ? ' active' : '');
    div.dataset.id = a.id;
    div.innerHTML = q ? highlight(a.name, qL) : a.name;
    div.addEventListener('click', () => showArtist(a.id));
    listEl.appendChild(div);
  }
  countEl.textContent = `${count} artista${count !== 1 ? 's' : ''}`;
}

function highlight(text, q) {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return text;
  return text.slice(0, i) + '<mark>' + text.slice(i, i + q.length) + '</mark>' + text.slice(i + q.length);
}

searchEl.addEventListener('input', () => renderList(searchEl.value.trim()));

// ── Artist detail ─────────────────────────────────────────────────────────────
const contentEl = document.getElementById('content');

function renderSource(sf) {
  if (!sf) return '';
  const pipe = sf.indexOf('|');
  if (pipe > -1) {
    const name = sf.slice(0, pipe).trim();
    const url  = sf.slice(pipe + 1).trim();
    if (url.startsWith('http')) {
      return `<div class="card-source"><a href="${url}" target="_blank" rel="noopener">📺 ${name || 'Ver fuente'}</a></div>`;
    }
  }
  return `<div class="card-source"><span>📂 ${sf}</span></div>`;
}

function linkifyArtists(text) {
  // Sort by length desc to avoid partial replacements
  const entries = Object.entries(NAME_TO_ID).sort((a, b) => b[0].length - a[0].length);
  let html = text;
  for (const [name, id] of entries) {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    html = html.replace(
      new RegExp('\\b' + esc + '\\b', 'gi'),
      `<a class="artist-link" data-id="${id}">${name}</a>`
    );
  }
  return html;
}

function showArtist(id) {
  activeId = id;
  const a  = byId[id];
  if (!a) return;

  // Update sidebar highlight
  document.querySelectorAll('.artist-item').forEach(el => {
    el.classList.toggle('active', +el.dataset.id === id);
  });

  // Scroll active item into view
  const activeEl = listEl.querySelector('.artist-item.active');
  if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });

  // Build detail HTML
  let html = `<div id="artist-detail">`;
  html += `<h1>${a.name}</h1>`;

  if (a.member_of.length) {
    const links = a.member_of.map(b =>
      `<a data-id="${b.id}">${b.name}</a>`
    ).join(', ');
    html += `<div class="member-of-line">Miembro de: ${links}</div>`;
  } else {
    html += `<div style="margin-bottom:20px"></div>`;
  }

  // Tag sections (list-based)
  const tagSections = [
    ['members',     a.members],
    ['genres',      a.genres],
    ['labels',      a.labels],
    ['concerts',    a.concerts],
    ['instruments', a.instruments],
  ];
  for (const [key, items] of tagSections) {
    if (!items.length) continue;
    const color = SEC_COLORS[key] || '#888';
    const colorAlpha = color + '22';
    html += `<div class="section">`;
    html += `<div class="section-title" style="color:${color}">${SEC_LABELS[key]}</div>`;
    html += `<div class="tag-list">`;
    for (const item of items) {
      const isObj = typeof item === 'object';
      const name  = isObj ? item.name : item;
      const mid   = isObj ? item.id   : null;
      const clickable = mid != null ? ' clickable' : '';
      const dataId    = mid != null ? ` data-id="${mid}"` : '';
      html += `<span class="tag${clickable}" style="color:${color};border-color:${color};background:${colorAlpha}"${dataId}>${name}</span>`;
    }
    html += `</div></div>`;
  }

  // Card sections (albums, songs, curiosities)
  const cardSections = [
    ['albums',      a.albums],
    ['songs',       a.songs],
    ['curiosities', a.curiosities],
  ];
  for (const [key, items] of cardSections) {
    if (!items.length) continue;
    const color = SEC_COLORS[key] || '#888';
    html += `<div class="section">`;
    html += `<div class="section-title" style="color:${color}">${SEC_LABELS[key]} (${items.length})</div>`;
    for (const item of items) {
      html += `<div class="card" style="border-left-color:${color}">`;
      html += `<div class="card-title">${item.name}</div>`;
      for (const f of item.facts) {
        html += `<div class="card-desc">${linkifyArtists(f.description)}</div>`;
        html += renderSource(f.source_file);
      }
      html += `</div>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  contentEl.innerHTML = html;

  // Attach click handlers for artist links and member tags
  contentEl.querySelectorAll('.artist-link, .tag.clickable, .member-of-line a').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      const targetId = +el.dataset.id;
      if (targetId) showArtist(targetId);
    });
  });

  // Update URL hash for bookmarking
  history.replaceState(null, '', '#' + id);
}

// ── Boot ─────────────────────────────────────────────────────────────────────
renderList('');

// Restore from hash
const hashId = parseInt(location.hash.slice(1));
if (hashId && byId[hashId]) {
  showArtist(hashId);
} else {
  contentEl.innerHTML = '<div id="placeholder">← Selecciona un artista</div>';
}
'''


def build_html(artists, name_to_id):
    js = JS
    js = js.replace('/*ARTISTS*/[]',    json.dumps(artists,    ensure_ascii=False))
    js = js.replace('/*NAME_TO_ID*/{}', json.dumps(name_to_id, ensure_ascii=False))
    js = js.replace('/*SEC_COLORS*/{}', json.dumps(SECTION_COLORS, ensure_ascii=False))
    js = js.replace('/*SEC_LABELS*/{}', json.dumps(SECTION_LABELS, ensure_ascii=False))

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Encyclopedia</title>
<!-- Umami Analytics -->
<script>
    defer
    src="https://cloud.umami.is/script.js"
    data-website-id="5d84fd6c-0760-4a0c-a2d0-ffabb82179f5"
</script>
<style>{CSS}</style>
</head>
<body>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Buscar artista..." autocomplete="off">
  </div>
  <div id="count-label"></div>
  <div id="artist-list"></div>
</div>
<div id="content">
  <div id="placeholder">← Selecciona un artista</div>
</div>
<script>
{js}
</script>
</body>
</html>'''


def main():
    if not os.path.exists(DB_PATH):
        print(f'No se encuentra {DB_PATH}. Ejecuta primero md_to_sqlite.py')
        return

    artists, name_to_id = load_data()
    if not artists:
        print('La base de datos está vacía.')
        return

    html = build_html(artists, name_to_id)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    total_facts = sum(
        len(a['albums']) + len(a['songs']) + len(a['curiosities'])
        for a in artists
    )
    print(f'{len(artists)} artistas, {total_facts} entradas → {OUT_HTML}')


if __name__ == '__main__':
    main()
