"""
artist_page.py

Genera markdown_style.html — enciclopedia interactiva con todos los datos
de music_facts.db.  Panel lateral con seis tabs independientes (artistas,
géneros, sellos, conciertos, instrumentos, curiosidades generales) y
botón para ocultar/mostrar el sidebar.
"""

import json
import os
import re
import sqlite3

DB_PATH  = 'music_facts.db'
OUT_HTML = 'markdown_style.html'

SECTION_COLORS = {
    'members':     '#e67e22',
    'member_of':   '#e67e22',
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
    'member_of':   'Miembro de',
    'genres':      'Géneros',
    'labels':      'Sellos',
    'concerts':    'Conciertos',
    'instruments': 'Instrumentos',
    'albums':      'Álbumes',
    'songs':       'Canciones',
    'curiosities': 'Curiosidades',
}

# entity_type -> (table, junction, fk)
ENTITY_TYPES = {
    'genre':      ('genres',      'artist_genres',      'genre_id'),
    'label':      ('labels',      'artist_labels',      'label_id'),
    'concert':    ('concerts',    'artist_concerts',    'concert_id'),
    'instrument': ('instruments', 'artist_instruments', 'instrument_id'),
}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)
    all_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    # ── Artists ──────────────────────────────────────────────────────────────
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

    if 'band_members' in all_tables:
        for band_id, member_id in conn.execute('SELECT band_id, member_id FROM band_members'):
            if band_id in all_artists and member_id in all_artists:
                all_artists[band_id]['members'].append(
                    {'id': member_id, 'name': all_artists[member_id]['name']}
                )
                all_artists[member_id]['member_of'].append(
                    {'id': band_id, 'name': all_artists[band_id]['name']}
                )

    for field, junc, etable, fk in [
        ('genres',      'artist_genres',      'genres',      'genre_id'),
        ('labels',      'artist_labels',      'labels',      'label_id'),
        ('concerts',    'artist_concerts',    'concerts',    'concert_id'),
        ('instruments', 'artist_instruments', 'instruments', 'instrument_id'),
    ]:
        if junc not in all_tables:
            continue
        for aid, name in conn.execute(
            f'SELECT j.artist_id, e.name FROM {junc} j JOIN {etable} e ON j.{fk}=e.id ORDER BY e.name'
        ):
            if aid in all_artists:
                all_artists[aid][field].append(name)

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

    if 'curiosities' in all_tables:
        for title, desc, sf, ctx_id in conn.execute(
            "SELECT title, description, source_file, context_id "
            "FROM curiosities WHERE context_type='artist' ORDER BY title"
        ):
            if ctx_id in all_artists:
                all_artists[ctx_id]['curiosities'].append(
                    {'name': title, 'facts': [{'description': desc, 'source_file': sf or ''}]}
                )

    # ── Named entities (genres, labels, concerts, instruments) ───────────────
    entities = {}
    for etype, (table, _, _) in ENTITY_TYPES.items():
        elist = []
        if table in all_tables:
            for eid, name in conn.execute(f'SELECT id, name FROM {table} ORDER BY name'):
                elist.append({'id': eid, 'name': name, 'curiosities': []})
        entities[etype] = elist

    if 'curiosities' in all_tables:
        ent_idx = {}
        for etype, elist in entities.items():
            for e in elist:
                ent_idx[(etype, e['id'])] = e
        for title, desc, sf, ctx_type, ctx_id in conn.execute(
            "SELECT title, description, source_file, context_type, context_id "
            "FROM curiosities WHERE context_type NOT IN ('artist','general') ORDER BY title"
        ):
            key = (ctx_type, ctx_id)
            if key in ent_idx:
                ent_idx[key]['curiosities'].append(
                    {'title': title, 'description': desc, 'source_file': sf or ''}
                )

    # ── General curiosities ───────────────────────────────────────────────────
    gen_curiosities = []
    if 'curiosities' in all_tables:
        for idx, (title, desc, sf) in enumerate(conn.execute(
            "SELECT title, description, source_file FROM curiosities "
            "WHERE context_type='general' ORDER BY title"
        )):
            gen_curiosities.append(
                {'id': idx, 'title': title, 'description': desc, 'source_file': sf or ''}
            )

    conn.close()

    primary = sorted(
        [a for a in all_artists.values() if a['is_primary']],
        key=lambda x: re.sub(r'^(The|Los|Las)\s+', '', x['name'], flags=re.IGNORECASE),
    )
    name_to_id = {a['name']: a['id'] for a in all_artists.values() if a['is_primary']}

    return {
        'artists':         primary,
        'genres':          entities.get('genre', []),
        'labels':          entities.get('label', []),
        'concerts':        entities.get('concert', []),
        'instruments':     entities.get('instrument', []),
        'gen_curiosities': gen_curiosities,
        'name_to_id':      name_to_id,
    }


# ── HTML template ──────────────────────────────────────────────────────────────

CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, sans-serif; background: #0d1117;
       color: #c9d1d9; display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ── */
#sidebar { width: 280px; min-width: 280px; background: #161b22;
           border-right: 1px solid #30363d; display: flex; flex-direction: column;
           flex-shrink: 0; transition: width 0.25s, min-width 0.25s, border-width 0.25s;
           overflow: hidden; }
#sidebar.hidden { width: 0; min-width: 0; border-right-width: 0; }

#sidebar-header { display: flex; align-items: center; justify-content: space-between;
                  padding: 10px 12px; border-bottom: 1px solid #30363d; flex-shrink: 0; }
#sidebar-header h1 { font-size: 0.82rem; color: #e94560; letter-spacing: 0.06em;
                     text-transform: uppercase; white-space: nowrap; }
#sidebar-close { background: none; border: none; color: #484f58; cursor: pointer;
                 font-size: 1rem; padding: 2px 6px; border-radius: 4px; line-height: 1; }
#sidebar-close:hover { color: #e94560; background: #21262d; }

/* Floating open button */
#sidebar-open { position: fixed; top: 12px; left: 12px; z-index: 100;
                background: #1f6feb; color: #fff; border: none; cursor: pointer;
                border-radius: 8px; padding: 7px 12px; font-size: 0.82rem;
                display: none; box-shadow: 0 2px 10px rgba(0,0,0,0.5); }
#sidebar-open.visible { display: block; }
#sidebar-open:hover { background: #388bfd; }

/* ── Tab bar ── */
#tab-bar { display: flex; flex-shrink: 0; overflow-x: auto; scrollbar-width: none;
           border-bottom: 1px solid #30363d; background: #0d1117; }
#tab-bar::-webkit-scrollbar { display: none; }
.tab-btn { flex: 1; min-width: 0; padding: 8px 2px; background: none; border: none;
           border-bottom: 2px solid transparent; color: #484f58; cursor: pointer;
           font-size: 0.72rem; white-space: nowrap; transition: color 0.1s; }
.tab-btn:hover { color: #c9d1d9; }
.tab-btn.active { color: #58a6ff; border-bottom-color: #58a6ff; }

/* ── Panels ── */
.panel { display: none; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.panel.active { display: flex; }

.panel-search-wrap { padding: 8px 10px; flex-shrink: 0; border-bottom: 1px solid #21262d; }
.panel-search { width: 100%; padding: 6px 10px; background: #0d1117; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 6px; font-size: 0.82rem; outline: none; }
.panel-search:focus { border-color: #58a6ff; }
.panel-search::placeholder { color: #484f58; }

#filter-wrap { padding: 5px 10px 8px; flex-shrink: 0; border-bottom: 1px solid #21262d; }
#filter-label { font-size: 0.68rem; color: #8b949e; margin-bottom: 4px;
                display: flex; justify-content: space-between; }
#filter-label b { color: #58a6ff; }
#filter-slider { width: 100%; accent-color: #1f6feb; cursor: pointer; }

.panel-count { padding: 4px 14px; font-size: 0.68rem; color: #484f58; flex-shrink: 0; }
.panel-list  { flex: 1; overflow-y: auto; padding: 4px 0; }

.list-item { padding: 7px 14px; font-size: 0.84rem; cursor: pointer;
             border-left: 3px solid transparent; color: #8b949e;
             transition: all 0.1s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.list-item:hover  { background: #1c2128; color: #c9d1d9; border-left-color: #30363d; }
.list-item.active { background: #1c2128; color: #58a6ff; border-left-color: #58a6ff; font-weight: 600; }
.list-item mark   { background: none; color: #f0883e; font-weight: bold; }

/* ── Content area ── */
#content { flex: 1; overflow-y: auto; padding: 32px 40px; }
#placeholder { display: flex; align-items: center; justify-content: center;
               height: 100%; color: #484f58; font-size: 1rem; }

#artist-detail, #entity-detail { max-width: 800px; }
#artist-detail h1, #entity-detail h1 { font-size: 2rem; font-weight: 700; color: #e6edf3;
                                        margin-bottom: 6px; line-height: 1.2; }
.entity-badge { display: inline-block; font-size: 0.7rem; padding: 2px 10px;
                border-radius: 12px; margin-bottom: 20px; font-weight: 700;
                letter-spacing: 0.06em; text-transform: uppercase; }
.member-of-line { font-size: 0.85rem; color: #8b949e; margin-bottom: 20px; }
.member-of-line a { color: #58a6ff; text-decoration: none; cursor: pointer; }
.member-of-line a:hover { text-decoration: underline; }

.section { margin-bottom: 28px; }
.section-title { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
                 text-transform: uppercase; margin-bottom: 10px;
                 padding-bottom: 6px; border-bottom: 1px solid #21262d; }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { display: inline-block; padding: 3px 10px; border-radius: 20px;
       font-size: 0.78rem; border: 1px solid; cursor: default; }
.tag.clickable { cursor: pointer; }
.tag.clickable:hover { opacity: 0.8; filter: brightness(1.2); }

.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px;
        padding: 14px 16px; margin-bottom: 10px; border-left: 3px solid; }
.card-title { font-size: 0.9rem; font-weight: 600; color: #e6edf3; margin-bottom: 6px; }
.card-desc  { font-size: 0.85rem; line-height: 1.6; color: #8b949e; }
.card-source { margin-top: 8px; font-size: 0.72rem; }
.card-source a    { color: #388bfd; text-decoration: none; cursor: pointer; }
.card-source a:hover { text-decoration: underline; color: #58a6ff; }
.card-source span { color: #484f58; }

.empty-state { color: #484f58; font-size: 0.85rem; padding: 16px 0; }

.artist-link { color: #f0883e; font-weight: 600; cursor: pointer;
               text-decoration: none; border-bottom: 1px dotted #f0883e; }
.artist-link:hover { color: #ffa657; border-bottom-color: #ffa657; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
'''

JS = r'''
const ARTISTS         = /*ARTISTS*/[];
const GENRES          = /*GENRES*/[];
const LABELS          = /*LABELS*/[];
const CONCERTS        = /*CONCERTS*/[];
const INSTRUMENTS     = /*INSTRUMENTS*/[];
const GEN_CURIOSITIES = /*GEN_CURIOSITIES*/[];
const NAME_TO_ID      = /*NAME_TO_ID*/{};
const SEC_COLORS      = /*SEC_COLORS*/{};
const SEC_LABELS      = /*SEC_LABELS*/{};

const ENTITY_COLORS = {
  genres:      SEC_COLORS.genres,
  labels:      SEC_COLORS.labels,
  concerts:    SEC_COLORS.concerts,
  instruments: SEC_COLORS.instruments,
};
const ENTITY_LABEL = {
  genres: 'Género', labels: 'Sello', concerts: 'Concierto', instruments: 'Instrumento',
};

// Artist index
const byId = {};
ARTISTS.forEach(a => { byId[a.id] = a; });

// ── Sidebar toggle ────────────────────────────────────────────────────────────
const sidebarEl = document.getElementById('sidebar');
const openBtn   = document.getElementById('sidebar-open');
document.getElementById('sidebar-close').addEventListener('click', () => {
  sidebarEl.classList.add('hidden');
  openBtn.classList.add('visible');
});
openBtn.addEventListener('click', () => {
  sidebarEl.classList.remove('hidden');
  openBtn.classList.remove('visible');
});

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name)
  );
  document.querySelectorAll('.panel').forEach(p =>
    p.classList.toggle('active', p.id === 'panel-' + name)
  );
}
document.querySelectorAll('.tab-btn').forEach(b =>
  b.addEventListener('click', () => switchTab(b.dataset.tab))
);

// ── Helpers ───────────────────────────────────────────────────────────────────
function highlight(text, q) {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return text;
  return text.slice(0,i) + '<mark>' + text.slice(i, i+q.length) + '</mark>' + text.slice(i+q.length);
}

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

function attachLinks(container) {
  container.querySelectorAll('.artist-link, .tag.clickable, .member-of-line a').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      const tid = +el.dataset.id;
      if (tid) showArtist(tid);
    });
  });
}

// ── Content area ──────────────────────────────────────────────────────────────
const contentEl = document.getElementById('content');
let   activeId  = null;

function showArtist(id) {
  activeId = id;
  const a = byId[id];
  if (!a) return;

  document.querySelectorAll('#artist-list .list-item').forEach(el =>
    el.classList.toggle('active', +el.dataset.id === id)
  );
  const sel = document.querySelector('#artist-list .list-item.active');
  if (sel) sel.scrollIntoView({ block: 'nearest' });

  let html = `<div id="artist-detail"><h1>${a.name}</h1>`;
  if (a.member_of.length) {
    const links = a.member_of.map(b => `<a data-id="${b.id}">${b.name}</a>`).join(', ');
    html += `<div class="member-of-line">Miembro de: ${links}</div>`;
  } else {
    html += `<div style="margin-bottom:20px"></div>`;
  }

  for (const [key, items] of [
    ['members', a.members], ['genres', a.genres], ['labels', a.labels],
    ['concerts', a.concerts], ['instruments', a.instruments],
  ]) {
    if (!items.length) continue;
    const color = SEC_COLORS[key] || '#888';
    html += `<div class="section">`;
    html += `<div class="section-title" style="color:${color}">${SEC_LABELS[key]}</div>`;
    html += `<div class="tag-list">`;
    for (const item of items) {
      const isObj = typeof item === 'object';
      const name  = isObj ? item.name : item;
      const mid   = isObj ? item.id   : null;
      const cls   = mid != null ? ' clickable' : '';
      const did   = mid != null ? ` data-id="${mid}"` : '';
      html += `<span class="tag${cls}" style="color:${color};border-color:${color};background:${color}22"${did}>${name}</span>`;
    }
    html += `</div></div>`;
  }

  for (const [key, items] of [['albums', a.albums], ['songs', a.songs], ['curiosities', a.curiosities]]) {
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
  attachLinks(contentEl);
  history.replaceState(null, '', '#artist_' + id);
}

function showEntity(type, entity) {
  document.querySelectorAll(`#panel-${type} .list-item`).forEach(el =>
    el.classList.toggle('active', el.textContent.trim() === entity.name)
  );
  const color = ENTITY_COLORS[type] || '#888';
  let html = `<div id="entity-detail">`;
  html += `<h1>${entity.name}</h1>`;
  html += `<div class="entity-badge" style="background:${color}22;color:${color};border:1px solid ${color}">${ENTITY_LABEL[type] || type}</div>`;
  if (!entity.curiosities.length) {
    html += `<div class="empty-state">No hay datos detallados disponibles.</div>`;
  } else {
    html += `<div class="section">`;
    for (const c of entity.curiosities) {
      html += `<div class="card" style="border-left-color:${color}">`;
      html += `<div class="card-title">${c.title}</div>`;
      html += `<div class="card-desc">${linkifyArtists(c.description)}</div>`;
      html += renderSource(c.source_file);
      html += `</div>`;
    }
    html += `</div>`;
  }
  html += `</div>`;
  contentEl.innerHTML = html;
  attachLinks(contentEl);
}

function showGeneralCuriosity(c) {
  document.querySelectorAll('#curiosity-list .list-item').forEach(el =>
    el.classList.toggle('active', el.textContent.trim() === c.title)
  );
  const color = SEC_COLORS.curiosities || '#95a5a6';
  let html = `<div id="entity-detail">`;
  html += `<h1>${c.title}</h1>`;
  html += `<div class="entity-badge" style="background:${color}22;color:${color};border:1px solid ${color}">Curiosidad</div>`;
  html += `<div class="card" style="border-left-color:${color}">`;
  html += `<div class="card-desc">${linkifyArtists(c.description)}</div>`;
  html += renderSource(c.source_file);
  html += `</div></div>`;
  contentEl.innerHTML = html;
  attachLinks(contentEl);
}

// ── Artists panel ─────────────────────────────────────────────────────────────
let minElements = 0;

function getCount(a) {
  return a.members.length + a.genres.length + a.labels.length +
         a.concerts.length + a.instruments.length +
         a.albums.length + a.songs.length + a.curiosities.length;
}

const artistListEl  = document.getElementById('artist-list');
const artistCountEl = document.getElementById('artist-count');

function renderArtistList(q) {
  const qL = q.toLowerCase();
  artistListEl.innerHTML = '';
  let count = 0;
  for (const a of ARTISTS) {
    if (getCount(a) < minElements) continue;
    if (q && !a.name.toLowerCase().includes(qL)) continue;
    count++;
    const div = document.createElement('div');
    div.className = 'list-item' + (a.id === activeId ? ' active' : '');
    div.dataset.id = a.id;
    div.innerHTML = q ? highlight(a.name, qL) : a.name;
    div.addEventListener('click', () => showArtist(a.id));
    artistListEl.appendChild(div);
  }
  artistCountEl.textContent = `${count} artista${count !== 1 ? 's' : ''}`;
}

document.getElementById('search-artists').addEventListener('input', e =>
  renderArtistList(e.target.value.trim())
);

// Discrete slider: snap to actual count values, no gaps
const countVals    = [...new Set(ARTISTS.map(getCount))].sort((a,b) => a-b);
const filterSlider = document.getElementById('filter-slider');
const minValLabel  = document.getElementById('min-val');
filterSlider.min   = 0;
filterSlider.max   = countVals.length - 1;
// Start at MAX — drag left to see more artists
filterSlider.value = countVals.length - 1;
minElements        = countVals[countVals.length - 1] ?? 0;
minValLabel.textContent = minElements;
filterSlider.addEventListener('input', function() {
  minElements = countVals[+this.value] ?? 0;
  minValLabel.textContent = minElements;
  renderArtistList(document.getElementById('search-artists').value.trim());
});

// ── Entity panels ─────────────────────────────────────────────────────────────
function setupEntityPanel(type, data, searchId, listId, countId) {
  const listEl  = document.getElementById(listId);
  const countEl = document.getElementById(countId);
  const search  = document.getElementById(searchId);

  function render(q) {
    const qL = q.toLowerCase();
    listEl.innerHTML = '';
    let count = 0;
    for (const e of data) {
      if (q && !e.name.toLowerCase().includes(qL)) continue;
      count++;
      const div = document.createElement('div');
      div.className = 'list-item';
      div.innerHTML = q ? highlight(e.name, qL) : e.name;
      div.addEventListener('click', () => showEntity(type, e));
      listEl.appendChild(div);
    }
    countEl.textContent = `${count} elemento${count !== 1 ? 's' : ''}`;
  }

  search.addEventListener('input', e => render(e.target.value.trim()));
  render('');
}

setupEntityPanel('genres',      GENRES,      'search-genres',      'genre-list',      'genre-count');
setupEntityPanel('labels',      LABELS,      'search-labels',      'label-list',      'label-count');
setupEntityPanel('concerts',    CONCERTS,    'search-concerts',    'concert-list',    'concert-count');
setupEntityPanel('instruments', INSTRUMENTS, 'search-instruments', 'instrument-list', 'instrument-count');

// ── Curiosities panel ─────────────────────────────────────────────────────────
(function() {
  const listEl  = document.getElementById('curiosity-list');
  const countEl = document.getElementById('curiosity-count');
  const search  = document.getElementById('search-curiosities');

  function render(q) {
    const qL = q.toLowerCase();
    listEl.innerHTML = '';
    let count = 0;
    for (const c of GEN_CURIOSITIES) {
      if (q && !c.title.toLowerCase().includes(qL) && !c.description.toLowerCase().includes(qL)) continue;
      count++;
      const div = document.createElement('div');
      div.className = 'list-item';
      div.textContent = c.title;
      div.addEventListener('click', () => showGeneralCuriosity(c));
      listEl.appendChild(div);
    }
    countEl.textContent = `${count} curiosidad${count !== 1 ? 'es' : ''}`;
  }

  search.addEventListener('input', e => render(e.target.value.trim()));
  render('');
})();

// ── Boot ──────────────────────────────────────────────────────────────────────
switchTab('artists');
renderArtistList('');

const hashMatch = location.hash.match(/^#artist_(\d+)$/);
if (hashMatch && byId[+hashMatch[1]]) {
  showArtist(+hashMatch[1]);
} else {
  contentEl.innerHTML = '<div id="placeholder">← Selecciona un elemento</div>';
}
'''


def build_html(data):
    js = JS
    js = js.replace('/*ARTISTS*/[]',         json.dumps(data['artists'],         ensure_ascii=False))
    js = js.replace('/*GENRES*/[]',           json.dumps(data['genres'],          ensure_ascii=False))
    js = js.replace('/*LABELS*/[]',           json.dumps(data['labels'],          ensure_ascii=False))
    js = js.replace('/*CONCERTS*/[]',         json.dumps(data['concerts'],        ensure_ascii=False))
    js = js.replace('/*INSTRUMENTS*/[]',      json.dumps(data['instruments'],     ensure_ascii=False))
    js = js.replace('/*GEN_CURIOSITIES*/[]',  json.dumps(data['gen_curiosities'], ensure_ascii=False))
    js = js.replace('/*NAME_TO_ID*/{}',       json.dumps(data['name_to_id'],      ensure_ascii=False))
    js = js.replace('/*SEC_COLORS*/{}',       json.dumps(SECTION_COLORS,          ensure_ascii=False))
    js = js.replace('/*SEC_LABELS*/{}',       json.dumps(SECTION_LABELS,          ensure_ascii=False))

    def panel(pid, label, search_ph, list_id, count_id, search_id, extra=''):
        return f'''
  <div id="panel-{pid}" class="panel">
    <div class="panel-search-wrap">
      <input id="{search_id}" class="panel-search" type="text" placeholder="{search_ph}" autocomplete="off">
    </div>{extra}
    <div id="{count_id}" class="panel-count"></div>
    <div id="{list_id}" class="panel-list"></div>
  </div>'''

    slider_extra = '''
    <div id="filter-wrap">
      <div id="filter-label">Mínimo elementos: <b id="min-val">0</b></div>
      <input id="filter-slider" type="range" min="0" max="100" value="0">
    </div>'''

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Music Encyclopedia</title>
<style>{CSS}</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <h1>🎵 Music Encyclopedia</h1>
    <button id="sidebar-close" title="Ocultar panel">✕</button>
  </div>
  <div id="tab-bar">
    <button class="tab-btn active" data-tab="artists">🎤 Artistas</button>
    <button class="tab-btn" data-tab="genres">🎵 Géneros</button>
    <button class="tab-btn" data-tab="labels">💿 Sellos</button>
    <button class="tab-btn" data-tab="concerts">🎪 Conciertos</button>
    <button class="tab-btn" data-tab="instruments">🎸 Instr.</button>
    <button class="tab-btn" data-tab="curiosities">✨ General</button>
  </div>
{panel("artists",     "Artistas",     "Buscar artista...",     "artist-list",     "artist-count",     "search-artists",     slider_extra)}
{panel("genres",      "Géneros",      "Buscar género...",      "genre-list",      "genre-count",      "search-genres")}
{panel("labels",      "Sellos",       "Buscar sello...",       "label-list",      "label-count",      "search-labels")}
{panel("concerts",    "Conciertos",   "Buscar concierto...",   "concert-list",    "concert-count",    "search-concerts")}
{panel("instruments", "Instrumentos", "Buscar instrumento...", "instrument-list", "instrument-count", "search-instruments")}
{panel("curiosities", "Curiosidades", "Buscar curiosidad...",  "curiosity-list",  "curiosity-count",  "search-curiosities")}
</div>

<button id="sidebar-open" title="Mostrar panel">☰ Panel</button>

<div id="content">
  <div id="placeholder">← Selecciona un elemento</div>
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

    data = load_data()
    if not data['artists']:
        print('La base de datos está vacía.')
        return

    html = build_html(data)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    total_facts = sum(
        len(a['albums']) + len(a['songs']) + len(a['curiosities'])
        for a in data['artists']
    )
    print(f"{len(data['artists'])} artistas, {total_facts} entradas → {OUT_HTML}")
    print(f"  Géneros: {len(data['genres'])}, Sellos: {len(data['labels'])}")
    print(f"  Conciertos: {len(data['concerts'])}, Instrumentos: {len(data['instruments'])}")
    print(f"  Curiosidades generales: {len(data['gen_curiosities'])}")


if __name__ == '__main__':
    main()
