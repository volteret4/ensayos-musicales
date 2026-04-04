import os
import json
import sqlite3
import urllib.request

DB_PATH = 'music_facts.db'
OUT_HTML = 'music_map.html'

TYPE_COLORS = {
    'artists':     '#e74c3c',
    'albums':      '#3498db',
    'songs':       '#5dade2',
    'genres':      '#2ecc71',
    'events':      '#f39c12',
    'instruments': '#9b59b6',
    'venues':      '#1abc9c',
    'members':     '#e67e22',
    'influences':  '#a29bfe',
    'curiosities': '#95a5a6',
}
DEFAULT_COLOR = '#bdc3c7'

CAT_LABELS = {
    'albums':      'Álbumes',
    'songs':       'Canciones',
    'events':      'Eventos',
    'genres':      'Géneros',
    'curiosities': 'Curiosidades',
    'instruments': 'Instrumentos',
    'venues':      'Lugares',
    'members':     'Miembros',
    'influences':  'Influencias',
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
    conn = sqlite3.connect(DB_PATH)
    all_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if 'artists' not in all_tables:
        conn.close()
        return [], []

    # Primary artists = those with explicit __artist__ entries in artists_data
    primary_artist_ids = set()
    if 'artists_data' in all_tables:
        for (aid,) in conn.execute('SELECT DISTINCT artist_id FROM artists_data'):
            primary_artist_ids.add(aid)

    artists = {}
    for aid, name in conn.execute('SELECT id, name FROM artists ORDER BY name'):
        artists[aid] = {'id': aid, 'name': name, 'categories': {},
                        'is_primary': aid in primary_artist_ids}

    # Fallback: source_file → artist_ids (for entries without @Artist tag)
    source_to_artists = {}
    if 'source_artists' in all_tables:
        for sf, aid in conn.execute('SELECT source_file, artist_id FROM source_artists'):
            source_to_artists.setdefault(sf, set()).add(aid)

    # Primary: direct entry_artists junction (from @Artist field in md)
    direct_map = {}   # (data_table, data_id) → set of artist_ids
    if 'entry_artists' in all_tables:
        for dt, did, aid in conn.execute('SELECT data_table, data_id, artist_id FROM entry_artists'):
            direct_map.setdefault((dt, did), set()).add(aid)

    # member_data_id → artist_id (from @@Member field in __member__ entries)
    member_data_to_artist = {}
    if 'member_artist_links' in all_tables:
        for md_id, aid in conn.execute('SELECT members_data_id, artist_id FROM member_artist_links'):
            member_data_to_artist[md_id] = aid

    skip = {'artists', 'source_artists', 'artist_relations', 'entry_artists'}
    obj_tables = sorted(t for t in all_tables if not t.endswith('_data') and t not in skip)

    # Sentinel for items with no artist association
    UNATTRIBUTED_ID = -1
    artists[UNATTRIBUTED_ID] = {'id': UNATTRIBUTED_ID, 'name': '[ Sin atribuir ]', 'categories': {},
                                 'is_primary': True}

    for obj_table in obj_tables:
        data_table = obj_table + '_data'
        if data_table not in all_tables:
            continue
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info({data_table})')]
        fk_candidates = [c for c in cols if c not in ('id', 'description', 'source_folder', 'source_file')]
        if not fk_candidates:
            continue
        fk = fk_candidates[0]
        has_folder = 'source_folder' in cols

        items = {}
        extra = ', d.source_folder' if has_folder else ''
        for row in conn.execute(
            f'SELECT o.id, o.name, d.id, d.description, d.source_file{extra} '
            f'FROM {obj_table} o JOIN {data_table} d ON d.{fk}=o.id ORDER BY o.name'
        ):
            if has_folder:
                iid, name, d_id, desc, sf, folder = row
            else:
                iid, name, d_id, desc, sf = row
                folder = os.path.dirname(sf) or '.'

            if iid not in items:
                items[iid] = {'id': iid, 'name': name, 'facts': [], 'aids': set()}
            # For member entries, resolve @@Member → linked artist profile
            if obj_table == 'members':
                linked = member_data_to_artist.get(d_id)
                if linked is not None and items[iid].get('linked_artist_id') is None:
                    items[iid]['linked_artist_id'] = linked
            items[iid]['facts'].append(
                {'description': desc, 'source_folder': folder, 'source_file': sf}
            )
            # Prefer direct @Artist link; fall back to source_file inference
            direct_aids = direct_map.get((data_table, d_id), set())
            if direct_aids:
                items[iid]['aids'].update(direct_aids)
            else:
                items[iid]['aids'].update(source_to_artists.get(sf, set()))

        for item in items.values():
            aids = item.pop('aids')
            if not aids:
                aids = {UNATTRIBUTED_ID}
            for aid in aids:
                if aid in artists:
                    cats = artists[aid]['categories']
                    cats.setdefault(obj_table, [])
                    if not any(x['id'] == item['id'] for x in cats[obj_table]):
                        cats[obj_table].append(dict(item))

    # Remove sentinel if it ended up with no items
    if not artists[UNATTRIBUTED_ID]['categories']:
        del artists[UNATTRIBUTED_ID]

    relations = []
    if 'artist_relations' in all_tables:
        rel_map = {}
        for aid, rid, ctx in conn.execute(
            'SELECT artist_id, related_artist_id, context FROM artist_relations'
        ):
            key = (aid, rid)
            if key not in rel_map:
                rel_map[key] = []
            if len(rel_map[key]) < 2:
                rel_map[key].append(ctx)
        for (aid, rid), ctxs in rel_map.items():
            relations.append({'source_id': aid, 'target_id': rid, 'contexts': ctxs})

    conn.close()
    return list(artists.values()), relations


# ── HTML generation ───────────────────────────────────────────────────────────

CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee;
       display: flex; height: 100vh; overflow: hidden; }

#sidebar { width: 300px; min-width: 220px; background: #16213e; padding: 14px;
           display: flex; flex-direction: column; gap: 10px; overflow-y: auto;
           border-right: 1px solid #0f3460; z-index: 10; }
#sidebar h1 { font-size: 1rem; color: #e94560; letter-spacing: 1px; }

#search-wrap { position: relative; }
#search { width: 100%; padding: 6px 10px; border-radius: 6px;
          border: 1px solid #0f3460; background: #0f3460; color: #eee;
          font-size: 0.85rem; outline: none; }
#search::placeholder { color: #666; }
#search:focus { border-color: #e94560; }
#ac-list { display: none; position: absolute; top: 100%; left: 0; right: 0;
           background: #0f3460; border: 1px solid #1a3a7e; border-top: none;
           border-radius: 0 0 6px 6px; max-height: 220px; overflow-y: auto; z-index: 200; }
#ac-list.open { display: block; }
.ac-item { padding: 7px 10px; font-size: 0.82rem; cursor: pointer;
           border-bottom: 1px solid #16213e; }
.ac-item:last-child { border-bottom: none; }
.ac-item:hover, .ac-item.active { background: #16213e; color: #e94560; }
.ac-item mark { background: none; color: #e94560; font-weight: bold; }

#legend { display: flex; flex-direction: column; gap: 4px; }
.leg-item { display: flex; align-items: center; gap: 7px; font-size: 0.78rem;
            cursor: pointer; user-select: none; }
.leg-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

#panel { flex: 1; overflow-y: auto; border-top: 1px solid #0f3460; padding-top: 10px; }
#panel h2 { font-size: 0.9rem; margin-bottom: 4px; }
.fact-card { background: #0f3460; border-radius: 5px; padding: 7px 9px; margin-bottom: 6px;
             font-size: 0.78rem; line-height: 1.45; border-left: 3px solid #e94560; }
.fact-src { font-size: 0.68rem; color: #777; margin-top: 3px; }
.rel-card { background: #1a1a2e; border-radius: 5px; padding: 6px 9px; margin-bottom: 5px;
            font-size: 0.76rem; line-height: 1.4; border-left: 3px solid #555;
            font-style: italic; color: #aaa; }
#panel .empty { color: #555; font-size: 0.82rem; }

#graph { flex: 1; }
svg { width: 100%; height: 100%; }
.node { cursor: pointer; }
.node circle { stroke-width: 1.5px; transition: stroke 0.15s, stroke-width 0.15s; }
.node text { pointer-events: none; fill: #ddd; text-anchor: middle; }
.node.expanded > circle { stroke: #fff !important; stroke-width: 2.5px !important; }
.node.selected > circle { stroke: #fff !important; stroke-width: 3px !important; }
.node.member-linked > circle { stroke: #e94560 !important; stroke-width: 2.5px !important; stroke-dasharray: 4 2; }
line.edge-solid { stroke: #2a3a5e; stroke-width: 1.5px; }
line.edge-dashed { stroke: #555; stroke-width: 1px; stroke-dasharray: 6 3; opacity: 0.6; }
'''

# Plain JS — no Python f-string interpolation needed here
JS = r'''
// ── Data injected by Python ──────────────────────────────────────────────────
const ARTISTS       = /*ARTISTS*/[];
const RELATIONS     = /*RELATIONS*/[];
const COLORS        = /*COLORS*/{};
const CAT_LABELS    = /*CAT_LABELS*/{};
const DEFAULT_COLOR = /*DEFAULT_COLOR*/'#bdc3c7';

// ── State ────────────────────────────────────────────────────────────────────
const expandedArtists    = new Set();
const expandedCategories = new Set();
let selectedNodeId = null;

// ── SVG / zoom / simulation ───────────────────────────────────────────────────
const svgEl = document.getElementById('svg');
const svg   = d3.select(svgEl);
const g     = svg.append('g');
const W     = () => svgEl.clientWidth;
const H     = () => svgEl.clientHeight;

const zoom = d3.zoom().scaleExtent([0.1, 8]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);

const sim = d3.forceSimulation()
  .force('link',    d3.forceLink().id(d => d.id)
                       .distance(d => d.dashed ? 220 : d.etype === 'cat' ? 110 : 55)
                       .strength(d => d.dashed ? 0.04 : 0.5))
  .force('charge',  d3.forceManyBody().strength(d =>
    d.ntype === 'artist' ? -500 : d.ntype === 'category' ? -180 : -60))
  .force('center',  d3.forceCenter(W() / 2, H() / 2))
  .force('collide', d3.forceCollide(d => (d.r || 8) + 5));

// Position memory
const pos = {};

sim.on('tick', () => {
  sim.nodes().forEach(n => { pos[n.id] = { x: n.x, y: n.y }; });
  g.selectAll('line.edge-solid, line.edge-dashed')
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  g.selectAll('.node').attr('transform', d => `translate(${d.x},${d.y})`);
});

// ── Graph computation ─────────────────────────────────────────────────────────
function computeGraph() {
  const nodes = [], edges = [];

  for (const a of ARTISTS) {
    // Show primary artists always; non-primary (member-only) only when explicitly expanded
    if (a.is_primary || expandedArtists.has(a.id)) {
      nodes.push({ id: `a_${a.id}`, ntype: 'artist', label: a.name,
                   data: a, r: 20, color: COLORS.artists || '#e74c3c' });
    }
  }
  for (const rel of RELATIONS) {
    edges.push({ id: `rel_${rel.source_id}_${rel.target_id}`,
                 source: `a_${rel.source_id}`, target: `a_${rel.target_id}`,
                 dashed: true, rel });
  }
  for (const artistId of expandedArtists) {
    const artist = ARTISTS.find(a => a.id === artistId);
    if (!artist) continue;
    for (const [catType, items] of Object.entries(artist.categories)) {
      if (!items.length) continue;
      const catId = `cat_${artistId}_${catType}`;
      nodes.push({ id: catId, ntype: 'category',
                   label: (CAT_LABELS[catType] || catType) + `\n(${items.length})`,
                   catType, artistId, items, r: 13, color: COLORS[catType] || DEFAULT_COLOR });
      edges.push({ id: `e_${catId}`, source: `a_${artistId}`, target: catId, etype: 'cat' });
      const catKey = `${artistId}_${catType}`;
      if (expandedCategories.has(catKey)) {
        for (const item of items) {
          const itemId = `item_${catType}_${artistId}_${item.id}`;
          const linked = item.linked_artist_id ?? null;
          nodes.push({ id: itemId, ntype: 'item', label: item.name,
                       facts: item.facts, catType, artistId,
                       linked_artist_id: linked,
                       r: linked != null ? 11 : 7,
                       color: COLORS[catType] || DEFAULT_COLOR });
          edges.push({ id: `e_${itemId}`, source: catId, target: itemId, etype: 'item' });
        }
      }
    }
  }
  return { nodes, edges };
}

// ── Render ────────────────────────────────────────────────────────────────────
// fromClick=true: pin existing nodes so only new ones drift into place
function render(fromClick = false) {
  const { nodes, edges } = computeGraph();

  for (const n of nodes) {
    if (pos[n.id]) {
      n.x = pos[n.id].x; n.y = pos[n.id].y;
      // Pin nodes that already have a position so they don't jump
      if (fromClick) { n.fx = n.x; n.fy = n.y; }
    } else if (n.ntype === 'category' && pos[`a_${n.artistId}`]) {
      const p = pos[`a_${n.artistId}`];
      n.x = p.x + (Math.random() - 0.5) * 50; n.y = p.y + (Math.random() - 0.5) * 50;
    } else if (n.ntype === 'item') {
      const p = pos[`cat_${n.artistId}_${n.catType}`];
      if (p) { n.x = p.x + (Math.random() - 0.5) * 35; n.y = p.y + (Math.random() - 0.5) * 35; }
    }
  }

  sim.nodes(nodes);
  sim.force('link').links(edges);
  sim.alpha(fromClick ? 0.25 : 0.6).restart();

  // Unpin after new nodes have settled
  if (fromClick) {
    setTimeout(() => {
      sim.nodes().forEach(n => { n.fx = null; n.fy = null; });
    }, 600);
  }

  // Edges
  g.selectAll('line.edge-solid').data(edges.filter(e => !e.dashed), e => e.id)
    .join('line').attr('class', 'edge-solid');
  g.selectAll('line.edge-dashed').data(edges.filter(e => e.dashed), e => e.id)
    .join('line').attr('class', 'edge-dashed');

  // Nodes
  const nodeGroups = g.selectAll('.node').data(nodes, d => d.id)
    .join(
      enter => {
        const grp = enter.append('g').attr('class', 'node')
          .call(d3.drag()
            .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
            .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
            .on('end',   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
          )
          .on('click', onNodeClick);
        grp.append('circle').attr('r', d => d.r).attr('fill', d => d.color).attr('stroke', '#1a1a2e');
        grp.append('text').attr('dy', d => d.r + 10)
          .style('font-size', d => d.ntype === 'artist' ? '10px' : '8px');
        return grp;
      },
      update => update,
      exit => exit.remove()
    );

  nodeGroups.select('text').each(function(d) {
    const el = d3.select(this);
    el.selectAll('*').remove();
    d.label.split('\n').forEach((line, i) => {
      el.append('tspan').attr('x', 0).attr('dy', i === 0 ? 0 : '1.1em')
        .text(line.length > 24 ? line.slice(0, 22) + '…' : line);
    });
  });

  nodeGroups
    .classed('expanded', d =>
      (d.ntype === 'artist'   && expandedArtists.has(d.data?.id)) ||
      (d.ntype === 'category' && expandedCategories.has(`${d.artistId}_${d.catType}`))
    )
    .classed('selected', d => d.id === selectedNodeId)
    .classed('member-linked', d => d.linked_artist_id != null);
}

// ── Interaction ───────────────────────────────────────────────────────────────
function onNodeClick(event, d) {
  event.stopPropagation();
  if (d.ntype === 'artist') {
    const id = d.data.id;
    if (expandedArtists.has(id)) {
      expandedArtists.delete(id);
      for (const k of [...expandedCategories]) {
        if (k.startsWith(`${id}_`)) expandedCategories.delete(k);
      }
    } else {
      expandedArtists.add(id);
    }
    showArtistPanel(d.data);
  } else if (d.ntype === 'category') {
    const key = `${d.artistId}_${d.catType}`;
    expandedCategories.has(key) ? expandedCategories.delete(key) : expandedCategories.add(key);
  } else if (d.ntype === 'item') {
    if (d.linked_artist_id != null) {
      // Member node → expand that artist's profile in the graph
      activateArtist(d.linked_artist_id);
    } else {
      selectedNodeId = d.id;
      showItemPanel(d);
    }
  }
  render(true);
}

// Expand an artist by id, pan/zoom the camera to it
function activateArtist(artistId) {
  if (!expandedArtists.has(artistId)) expandedArtists.add(artistId);
  const artist = ARTISTS.find(a => a.id === artistId);
  if (artist) showArtistPanel(artist);
  render(true);

  // Pan to the artist node after the simulation has had a moment to settle
  setTimeout(() => {
    const node = sim.nodes().find(n => n.id === `a_${artistId}`);
    if (!node) return;
    const scale = 1.8;
    svg.transition().duration(700).call(
      zoom.transform,
      d3.zoomIdentity.translate(W() / 2 - node.x * scale, H() / 2 - node.y * scale).scale(scale)
    );
  }, 350);
}

function showArtistPanel(artist) {
  const color = COLORS.artists || '#e74c3c';
  const rels = RELATIONS.filter(r => r.source_id === artist.id || r.target_id === artist.id);
  const relHtml = rels.length ? `
    <p style="font-size:.75rem;color:#888;margin:8px 0 4px">Relacionado con:</p>
    ${rels.map(r => {
      const otherId = r.source_id === artist.id ? r.target_id : r.source_id;
      const other = ARTISTS.find(a => a.id === otherId);
      return `<div class="rel-card">${other ? other.name : otherId}: ${r.contexts[0] || ''}</div>`;
    }).join('')}
  ` : '';
  document.getElementById('panel').innerHTML = `
    <h2 style="color:${color}">${artist.name}</h2>
    <p style="font-size:.75rem;color:#888;margin-bottom:8px">
      ${Object.keys(artist.categories).length} categorías · haz clic en una para expandir
    </p>${relHtml}`;
}

function showItemPanel(d) {
  const color = COLORS[d.catType] || DEFAULT_COLOR;
  document.getElementById('panel').innerHTML = `
    <h2 style="color:${color}">${d.label}</h2>
    <p style="font-size:.75rem;color:#888;margin-bottom:8px">
      ${CAT_LABELS[d.catType] || d.catType} · ${d.facts.length} hecho${d.facts.length !== 1 ? 's' : ''}
    </p>
    ${d.facts.map(f => `
      <div class="fact-card" style="border-left-color:${color}">
        ${f.description}
        <div class="fact-src">📂 ${f.source_folder} / ${f.source_file.split('/').pop()}</div>
      </div>`).join('')}`;
}

svg.on('click', () => {
  selectedNodeId = null;
  document.getElementById('panel').innerHTML =
    '<p class="empty">Haz clic en un artista para explorar.</p>';
  render(true);
});

// ── Autocomplete search ───────────────────────────────────────────────────────
const searchEl = document.getElementById('search');
const acList   = document.getElementById('ac-list');
let acActive   = -1;  // keyboard-selected index

function highlight(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return text.slice(0, i) + '<mark>' + text.slice(i, i + q.length) + '</mark>' + text.slice(i + q.length);
}

function buildAcList(q) {
  acList.innerHTML = '';
  acActive = -1;
  if (!q) { acList.classList.remove('open'); return; }

  const matches = ARTISTS.filter(a => a.name.toLowerCase().includes(q.toLowerCase()));
  if (!matches.length) { acList.classList.remove('open'); return; }

  matches.slice(0, 12).forEach((artist, idx) => {
    const div = document.createElement('div');
    div.className = 'ac-item';
    div.innerHTML = highlight(artist.name, q);
    div.addEventListener('mousedown', e => {
      e.preventDefault();  // don't blur the input
      selectAcItem(artist);
    });
    acList.appendChild(div);
  });
  acList.classList.add('open');
}

function selectAcItem(artist) {
  searchEl.value = artist.name;
  acList.classList.remove('open');
  activateArtist(artist.id);
}

searchEl.addEventListener('input', () => buildAcList(searchEl.value));

searchEl.addEventListener('keydown', e => {
  const items = acList.querySelectorAll('.ac-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    acActive = Math.min(acActive + 1, items.length - 1);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    acActive = Math.max(acActive - 1, 0);
  } else if (e.key === 'Enter' && acActive >= 0) {
    e.preventDefault();
    const artist = ARTISTS.filter(a => a.name.toLowerCase().includes(searchEl.value.toLowerCase()))[acActive];
    if (artist) selectAcItem(artist);
    return;
  } else if (e.key === 'Escape') {
    acList.classList.remove('open'); return;
  } else { return; }
  items.forEach((el, i) => el.classList.toggle('active', i === acActive));
});

document.addEventListener('click', e => {
  if (!e.target.closest('#search-wrap')) acList.classList.remove('open');
});

window.addEventListener('resize', () => {
  sim.force('center', d3.forceCenter(W() / 2, H() / 2)).restart();
});

// ── Boot ──────────────────────────────────────────────────────────────────────
render();
'''


D3_LOCAL  = 'd3.v7.min.js'
D3_URL    = 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js'
D3_BACKUP = 'https://unpkg.com/d3@7/dist/d3.min.js'


def get_d3():
    """Return D3 source, downloading and caching it locally on first run."""
    if os.path.exists(D3_LOCAL):
        with open(D3_LOCAL, 'r', encoding='utf-8') as f:
            return f.read()
    for url in (D3_URL, D3_BACKUP):
        try:
            print(f"Descargando D3.js desde {url} ...")
            with urllib.request.urlopen(url, timeout=20) as r:
                src = r.read().decode('utf-8')
            with open(D3_LOCAL, 'w', encoding='utf-8') as f:
                f.write(src)
            print(f"  → guardado en {D3_LOCAL} ({len(src)//1024} KB)")
            return src
        except Exception as e:
            print(f"  fallo ({e}), probando siguiente URL...")
    raise RuntimeError("No se pudo descargar D3.js. Descárgalo manualmente como d3.v7.min.js")


def inject_data(js, artists, relations):
    """Replace /*PLACEHOLDER*/ comments in JS with actual JSON data."""
    js = js.replace('/*ARTISTS*/[]',         json.dumps(artists,    ensure_ascii=False))
    js = js.replace('/*RELATIONS*/[]',        json.dumps(relations,  ensure_ascii=False))
    js = js.replace('/*COLORS*/{}',           json.dumps(TYPE_COLORS, ensure_ascii=False))
    js = js.replace('/*CAT_LABELS*/{}',       json.dumps(CAT_LABELS, ensure_ascii=False))
    js = js.replace("/*DEFAULT_COLOR*/'#bdc3c7'", f"'{DEFAULT_COLOR}'")
    return js


def build_html(artists, relations):
    d3_src = get_d3()
    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Music Map</title>
<script>{d3_src}</script>
<style>{CSS}</style>
</head>
<body>
<div id="sidebar">
  <h1>🎵 Music Map</h1>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Buscar artista...">
    <div id="ac-list"></div>
  </div>
  <div id="legend">
    {''.join(
      f'<div class="leg-item"><div class="leg-dot" style="background:{color}"></div>'
      f'<span>{CAT_LABELS.get(t, t).capitalize()}</span></div>'
      for t, color in TYPE_COLORS.items()
    )}
  </div>
  <div id="panel"><p class="empty">Haz clic en un artista para explorar.</p></div>
</div>
<div id="graph"><svg id="svg"></svg></div>
<script>
{inject_data(JS, artists, relations)}
</script>
</body>
</html>'''


def main():
    if not os.path.exists(DB_PATH):
        print(f"No se encuentra {DB_PATH}. Ejecuta primero md_to_sqlite.py")
        return

    artists, relations = load_data()
    if not artists:
        print("La base de datos está vacía.")
        return

    html = build_html(artists, relations)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    n_rels = len(relations)
    n_cats = sum(len(a['categories']) for a in artists)
    print(f"{len(artists)} artistas, {n_cats} categorías totales, {n_rels} relaciones → {OUT_HTML}")


if __name__ == '__main__':
    main()
