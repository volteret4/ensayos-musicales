import os
import json
import sqlite3
import urllib.request

DB_PATH  = 'music_facts.db'
OUT_HTML = 'music_map.html'

# ── Colours ───────────────────────────────────────────────────────────────────

TYPE_COLORS = {
    'artists':     '#e74c3c',
    'albums':      '#3498db',
    'songs':       '#5dade2',
    'genres':      '#2ecc71',
    'labels':      '#f39c12',
    'venues':      '#1abc9c',
    'instruments': '#9b59b6',
    'curiosities': '#95a5a6',
    'members':     '#e67e22',
}
DEFAULT_COLOR = '#bdc3c7'

CAT_LABELS = {
    'albums':      'Álbumes',
    'songs':       'Canciones',
    'genres':      'Géneros',
    'labels':      'Sellos',
    'venues':      'Lugares',
    'instruments': 'Instrumentos',
    'curiosities': 'Curiosidades',
    'members':     'Miembros',
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_data():
    conn       = sqlite3.connect(DB_PATH)
    all_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if 'artists' not in all_tables:
        conn.close()
        return [], []

    mention_item_keys    = set()  # (source_artist_id, item_name)
    mention_targets_map  = {}     # (source_artist_id, item_name) → [{id, name}, …]

    # ── Artists ───────────────────────────────────────────────────────────────
    artists = {}
    for aid, name, is_primary in conn.execute(
        'SELECT id, name, is_primary FROM artists ORDER BY name'
    ):
        artists[aid] = {
            'id': aid, 'name': name,
            'is_primary': bool(is_primary),
            'categories': {},
            'member_of': [],
        }

    # ── Band members ──────────────────────────────────────────────────────────
    band_member_map = {}   # band_id → [member_id, ...]
    if 'band_members' in all_tables:
        for band_id, member_id in conn.execute(
            'SELECT band_id, member_id FROM band_members ORDER BY band_id, member_id'
        ):
            band_member_map.setdefault(band_id, []).append(member_id)
            if member_id in artists and band_id in artists:
                artists[member_id]['member_of'].append(artists[band_id]['name'])

    # ── Cross-reference mention keys + targets ───────────────────────────────
    if 'cross_references' in all_tables:
        for src_id, tgt_id, iname in conn.execute(
            'SELECT DISTINCT source_artist_id, target_artist_id, item_name FROM cross_references'
        ):
            if src_id in artists:
                mention_item_keys.add((src_id, iname))
            if src_id in artists and tgt_id in artists:
                mention_targets_map.setdefault((src_id, iname), []).append(
                    {'id': tgt_id, 'name': artists[tgt_id]['name']}
                )

    # ── Entity curiosities map ─────────────────────────────────────────────────
    # (context_type, context_id) → [{title, description, source_file}, ...]
    entity_curiosities = {}
    if 'curiosities' in all_tables:
        for title, desc, ctx_type, ctx_id, sf in conn.execute(
            "SELECT title, description, context_type, context_id, source_file "
            "FROM curiosities ORDER BY title"
        ):
            key = (ctx_type, ctx_id)
            entity_curiosities.setdefault(key, []).append(
                {'title': title, 'description': f'{title}: {desc}', 'source_file': sf}
            )

    # ── Albums ────────────────────────────────────────────────────────────────
    if 'albums' in all_tables and 'albums_data' in all_tables:
        album_items = {}   # (album_id, artist_id) → item dict
        for album_id, name, artist_id in conn.execute(
            'SELECT id, name, artist_id FROM albums ORDER BY name'
        ):
            if artist_id in artists:
                album_items[(album_id, artist_id)] = {
                    'id': album_id, 'name': name, 'facts': [],
                    'is_mention_source':  (artist_id, name) in mention_item_keys,
                    'mentioned_artists':  mention_targets_map.get((artist_id, name), []),
                }
        for album_id, artist_id, desc, sf in conn.execute(
            'SELECT a.id, a.artist_id, d.description, d.source_file '
            'FROM albums a JOIN albums_data d ON d.album_id = a.id'
        ):
            key = (album_id, artist_id)
            if key in album_items:
                album_items[key]['facts'].append({'description': desc, 'source_file': sf})
        for (_, artist_id), item in album_items.items():
            artists[artist_id]['categories'].setdefault('albums', []).append(item)

    # ── Songs ─────────────────────────────────────────────────────────────────
    if 'songs' in all_tables and 'songs_data' in all_tables:
        song_items = {}
        for song_id, name, artist_id in conn.execute(
            'SELECT id, name, artist_id FROM songs ORDER BY name'
        ):
            if artist_id in artists:
                song_items[(song_id, artist_id)] = {
                    'id': song_id, 'name': name, 'facts': [],
                    'is_mention_source':  (artist_id, name) in mention_item_keys,
                    'mentioned_artists':  mention_targets_map.get((artist_id, name), []),
                }
        for song_id, artist_id, desc, sf in conn.execute(
            'SELECT s.id, s.artist_id, d.description, d.source_file '
            'FROM songs s JOIN songs_data d ON d.song_id = s.id'
        ):
            key = (song_id, artist_id)
            if key in song_items:
                song_items[key]['facts'].append({'description': desc, 'source_file': sf})
        for (_, artist_id), item in song_items.items():
            artists[artist_id]['categories'].setdefault('songs', []).append(item)

    # ── Artist curiosities ────────────────────────────────────────────────────
    for aid in artists:
        facts = entity_curiosities.get(('artist', aid), [])
        if facts:
            for i, f in enumerate(facts):
                title = f.get('title', f['description'].split(':')[0]).strip()
                item = {
                    'id':               aid * 10000 + i,
                    'name':             title[:80],
                    'facts':            [f],
                    'is_mention_source': (aid, title) in mention_item_keys,
                    'mentioned_artists': mention_targets_map.get((aid, title), []),
                }
                artists[aid]['categories'].setdefault('curiosities', []).append(item)

    # ── Association categories (genres, labels, venues, instruments) ──────────
    assoc = [
        ('genres',      'artist_genres',      'genres',      'genre_id',      'genre'),
        ('labels',      'artist_labels',       'labels',      'label_id',      'label'),
        ('venues',      'artist_venues',       'venues',      'venue_id',      'venue'),
        ('instruments', 'artist_instruments',  'instruments', 'instrument_id', 'instrument'),
    ]
    for cat, junc, entity_table, fk, ctx_type in assoc:
        if junc not in all_tables or entity_table not in all_tables:
            continue
        for artist_id, eid, ename in conn.execute(
            f'SELECT j.artist_id, e.id, e.name '
            f'FROM {junc} j JOIN {entity_table} e ON j.{fk} = e.id '
            f'ORDER BY e.name'
        ):
            if artist_id not in artists:
                continue
            facts = entity_curiosities.get((ctx_type, eid), [])
            item = {'id': eid, 'name': ename, 'facts': facts}
            artists[artist_id]['categories'].setdefault(cat, []).append(item)

    # ── Members category (bands) ──────────────────────────────────────────────
    for band_id, member_ids in band_member_map.items():
        if band_id not in artists:
            continue
        members_list = []
        for mid in member_ids:
            if mid not in artists:
                continue
            members_list.append({
                'id':               mid,
                'name':             artists[mid]['name'],
                'facts':            entity_curiosities.get(('artist', mid), []),
                'linked_artist_id': mid if artists[mid]['is_primary'] else None,
            })
        if members_list:
            artists[band_id]['categories']['members'] = members_list

    # ── Relations: dashed lines between primary member artists and their bands ─
    relations = []
    seen = set()
    for band_id, member_ids in band_member_map.items():
        for mid in member_ids:
            if band_id not in artists or mid not in artists:
                continue
            if not artists[mid]['is_primary']:
                continue
            key = (min(band_id, mid), max(band_id, mid))
            if key not in seen:
                seen.add(key)
                relations.append({'source_id': band_id, 'target_id': mid, 'type': 'member'})

    # ── Cross-reference relations (mention edges between artists) ────────────
    if 'cross_references' in all_tables:
        # Count item_type occurrences per undirected pair
        pair_type_counts = {}
        for src_id, tgt_id, itype in conn.execute(
            'SELECT source_artist_id, target_artist_id, item_type FROM cross_references'
        ):
            pair = (min(src_id, tgt_id), max(src_id, tgt_id))
            pair_type_counts.setdefault(pair, {})
            pair_type_counts[pair][itype] = pair_type_counts[pair].get(itype, 0) + 1

        _type_to_cat = {'album': 'albums', 'song': 'songs', 'curiosity': 'curiosities'}
        for (s, t), counts in pair_type_counts.items():
            if s not in artists or t not in artists:
                continue
            dominant = max(counts, key=counts.get)
            color = TYPE_COLORS.get(_type_to_cat.get(dominant, ''), DEFAULT_COLOR)
            relations.append({'source_id': s, 'target_id': t, 'type': 'mention', 'color': color})

    conn.close()
    return list(artists.values()), relations


# ── D3 ────────────────────────────────────────────────────────────────────────

D3_LOCAL  = 'd3.v7.min.js'
D3_URL    = 'https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js'
D3_BACKUP = 'https://unpkg.com/d3@7/dist/d3.min.js'


def get_d3():
    if os.path.exists(D3_LOCAL):
        with open(D3_LOCAL, 'r', encoding='utf-8') as f:
            return f.read()
    for url in (D3_URL, D3_BACKUP):
        try:
            print(f'Descargando D3.js desde {url} ...')
            with urllib.request.urlopen(url, timeout=20) as r:
                src = r.read().decode('utf-8')
            with open(D3_LOCAL, 'w', encoding='utf-8') as f:
                f.write(src)
            print(f'  → guardado ({len(src)//1024} KB)')
            return src
        except Exception as e:
            print(f'  fallo ({e}), probando siguiente...')
    raise RuntimeError('No se pudo descargar D3.js. Descárgalo manualmente como d3.v7.min.js')


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = '''
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", sans-serif; background: #1a1a2e; color: #eee;
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
           border-radius: 0 0 6px 6px; max-height: 380px; overflow-y: auto; z-index: 200; }
#ac-list.open { display: block; }
.ac-item { padding: 7px 10px; font-size: 0.82rem; cursor: pointer;
           border-bottom: 1px solid #16213e; }
.ac-item:last-child { border-bottom: none; }
.ac-item:hover, .ac-item.active { background: #16213e; color: #e94560; }
.ac-item mark { background: none; color: #e94560; font-weight: bold; }

#legend { display: flex; flex-direction: column; gap: 4px; }
.leg-item { display: flex; align-items: center; gap: 7px; font-size: 0.78rem; }
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

#focus-bar { display: none; flex-direction: column; gap: 6px;
             padding-bottom: 10px; border-bottom: 1px solid #0f3460; }
#focus-bar.active { display: flex; }
#focus-back { background: #0f3460; color: #eee; border: 1px solid #1a3a7e;
              border-radius: 5px; padding: 5px 10px; cursor: pointer;
              font-size: 0.8rem; text-align: left; }
#focus-back:hover { background: #16213e; color: #e94560; }
#focus-depth-row { display: flex; align-items: center; gap: 8px; }
#focus-label { font-size: 0.78rem; color: #aaa; white-space: nowrap; }
#focus-slider { flex: 1; accent-color: #e94560; cursor: pointer; }

#graph { flex: 1; }
svg { width: 100%; height: 100%; }
.node { cursor: pointer; }
.node circle { stroke-width: 1.5px; transition: stroke 0.15s, stroke-width 0.15s; }
.node text { pointer-events: none; fill: #ddd; text-anchor: middle; }
.node.expanded > circle { stroke: #fff !important; stroke-width: 2.5px !important; }
.node.selected > circle { stroke: #fff !important; stroke-width: 3px !important; }
.node.member-linked > circle { stroke: #e94560 !important; stroke-width: 2.5px !important;
                                stroke-dasharray: 4 2; }
line.edge-solid   { stroke: #2a3a5e; stroke-width: 1.5px; }
line.edge-member  { stroke: #e67e22; stroke-width: 1px; stroke-dasharray: 6 3; opacity: 0.5; }
line.edge-mention { stroke: #8e44ad; stroke-width: 1px; stroke-dasharray: 3 5; opacity: 0.35; }
line.edge-dashed  { stroke: #555;    stroke-width: 1px; stroke-dasharray: 6 3; opacity: 0.4; }
.node.mention-source > circle { stroke: #3498db !important; stroke-width: 2px !important;
                                 stroke-dasharray: 3 3; }
.artist-link { color: #e94560; font-weight: 600; cursor: pointer;
               text-decoration: none; border-bottom: 1px dotted #e94560; }
.artist-link:hover { color: #fff; border-bottom-color: #fff; }
'''

# ── JS ────────────────────────────────────────────────────────────────────────

JS = r'''
const ARTISTS       = /*ARTISTS*/[];
const RELATIONS     = /*RELATIONS*/[];
const COLORS        = /*COLORS*/{};
const CAT_LABELS    = /*CAT_LABELS*/{};
const DEFAULT_COLOR = /*DEFAULT_COLOR*/'#bdc3c7';

// ── State ────────────────────────────────────────────────────────────────────
const expandedArtists    = new Set();
const expandedCategories = new Set();
let   selectedNodeId     = null;
let   focusArtistId      = null;
let   focusDepth         = 1;

// ── Adjacency list for BFS (artist-to-artist relations) ──────────────────────
const artistAdj = {};
for (const rel of RELATIONS) {
  (artistAdj[rel.source_id] = artistAdj[rel.source_id] || new Set()).add(rel.target_id);
  (artistAdj[rel.target_id] = artistAdj[rel.target_id] || new Set()).add(rel.source_id);
}

function bfsArtists(startId, depth) {
  const visited = new Set([startId]);
  let frontier = [startId];
  for (let d = 0; d < depth && frontier.length; d++) {
    const next = [];
    for (const id of frontier) {
      for (const nb of (artistAdj[id] || [])) {
        if (!visited.has(nb)) { visited.add(nb); next.push(nb); }
      }
    }
    frontier = next;
  }
  return visited;
}

// ── SVG / zoom / sim ──────────────────────────────────────────────────────────
const svgEl = document.getElementById('svg');
const svg   = d3.select(svgEl);
const g     = svg.append('g');
const W = () => svgEl.clientWidth;
const H = () => svgEl.clientHeight;

const zoom = d3.zoom().scaleExtent([0.05, 8]).on('zoom', e => g.attr('transform', e.transform));
svg.call(zoom);

const sim = d3.forceSimulation()
  .force('link',    d3.forceLink().id(d => d.id)
                       .distance(d => d.etype === 'member'  ? 240
                                    : d.etype === 'mention' ? 280
                                    : d.etype === 'cat'     ? 90
                                    : d.etype === 'item'    ? 45 : 180)
                       .strength(d => d.etype === 'member'  ? 0.03
                                    : d.etype === 'mention' ? 0.01
                                    : d.etype === 'cat'     ? 0.9
                                    : d.etype === 'item'    ? 0.7 : 0.5))
  .force('charge',  d3.forceManyBody().strength(d =>
    d.ntype === 'artist' ? -220 : d.ntype === 'category' ? -60 : -20))
  .force('x',       d3.forceX(W() / 2).strength(0.02))
  .force('y',       d3.forceY(H() / 2).strength(0.02))
  .force('collide', d3.forceCollide(d => (d.r || 8) + 4));

const pos = {};
sim.on('tick', () => {
  sim.nodes().forEach(n => { pos[n.id] = { x: n.x, y: n.y }; });
  g.selectAll('line').attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                     .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  g.selectAll('.node').attr('transform', d => `translate(${d.x},${d.y})`);
});

// ── Graph computation ─────────────────────────────────────────────────────────
function computeGraph() {
  const nodes = [], edges = [];

  // Artist nodes
  // Focus mode: only artists in BFS set (all expanded)
  // Normal mode: all primary artists; non-primary only if expanded
  for (const a of ARTISTS) {
    const visible = focusArtistId !== null
      ? expandedArtists.has(a.id)
      : (a.is_primary || expandedArtists.has(a.id));
    if (visible) {
      nodes.push({ id: `a_${a.id}`, ntype: 'artist', label: a.name,
                   data: a, r: 20, color: COLORS.artists || '#e74c3c' });
    }
  }

  // Artist-to-artist relation edges (member, mention)
  // In focus mode, only between artists in the focused set
  for (const rel of RELATIONS) {
    if (rel.type === 'member' || rel.type === 'mention') {
      if (focusArtistId !== null &&
          (!expandedArtists.has(rel.source_id) || !expandedArtists.has(rel.target_id))) continue;
      edges.push({ id: `rel_${rel.source_id}_${rel.target_id}`,
                   source: `a_${rel.source_id}`, target: `a_${rel.target_id}`,
                   etype: rel.type, color: rel.color || null });
    }
  }

  // Expanded artists → categories → items
  for (const artistId of expandedArtists) {
    const artist = ARTISTS.find(a => a.id === artistId);
    if (!artist) continue;

    for (const [catType, items] of Object.entries(artist.categories)) {
      if (!items.length) continue;
      const catId = `cat_${artistId}_${catType}`;
      nodes.push({ id: catId, ntype: 'category',
                   label: (CAT_LABELS[catType] || catType) + ` (${items.length})`,
                   catType, artistId, items, r: 13,
                   color: COLORS[catType] || DEFAULT_COLOR });
      edges.push({ id: `e_${catId}`, source: `a_${artistId}`, target: catId, etype: 'cat' });

      const catKey = `${artistId}_${catType}`;
      if (expandedCategories.has(catKey)) {
        for (const item of items) {
          const itemId = `item_${catType}_${artistId}_${item.id}`;
          const linked = item.linked_artist_id ?? null;
          nodes.push({ id: itemId, ntype: 'item', label: item.name,
                       facts: item.facts, catType, artistId,
                       linked_artist_id:  linked,
                       is_mention_source: item.is_mention_source ?? false,
                       mentioned_artists: item.mentioned_artists ?? [],
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
function render(fromClick = false) {
  const { nodes, edges } = computeGraph();

  for (const n of nodes) {
    if (pos[n.id]) {
      n.x = pos[n.id].x; n.y = pos[n.id].y;
    } else if (n.ntype === 'category' && pos[`a_${n.artistId}`]) {
      const p = pos[`a_${n.artistId}`];
      n.x = p.x + (Math.random() - 0.5) * 20; n.y = p.y + (Math.random() - 0.5) * 20;
    } else if (n.ntype === 'item') {
      const p = pos[`cat_${n.artistId}_${n.catType}`];
      if (p) { n.x = p.x + (Math.random() - 0.5) * 15; n.y = p.y + (Math.random() - 0.5) * 15; }
    }
  }

  sim.nodes(nodes);
  sim.force('link').links(edges);
  sim.alpha(fromClick ? 0.2 : 0.6).restart();

  // Edges
  g.selectAll('line.edge-solid').data(
    edges.filter(e => e.etype === 'cat' || e.etype === 'item'), e => e.id
  ).join('line').attr('class', 'edge-solid');

  g.selectAll('line.edge-member').data(
    edges.filter(e => e.etype === 'member'), e => e.id
  ).join('line').attr('class', 'edge-member');

  g.selectAll('line.edge-mention').data(
    edges.filter(e => e.etype === 'mention'), e => e.id
  ).join('line').attr('class', 'edge-mention')
               .attr('stroke', d => d.color || '#8e44ad');

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
        grp.append('text').attr('dy', d => d.r + 11)
          .style('font-size', d => d.ntype === 'artist' ? '10px' : '8px');
        return grp;
      },
      update => update,
      exit   => exit.remove()
    );

  nodeGroups.select('text').each(function(d) {
    const el = d3.select(this);
    el.selectAll('*').remove();
    d.label.split('\n').forEach((line, i) => {
      el.append('tspan').attr('x', 0).attr('dy', i === 0 ? 0 : '1.1em')
        .text(line.length > 26 ? line.slice(0, 24) + '…' : line);
    });
  });

  nodeGroups
    .classed('expanded', d =>
      (d.ntype === 'artist'   && expandedArtists.has(d.data?.id)) ||
      (d.ntype === 'category' && expandedCategories.has(`${d.artistId}_${d.catType}`))
    )
    .classed('selected',       d => d.id === selectedNodeId)
    .classed('member-linked',  d => d.linked_artist_id != null)
    .classed('mention-source', d => d.is_mention_source === true);
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
      // Auto-expand members category for bands
      if (d.data.categories.members?.length) {
        expandedCategories.add(`${id}_members`);
      }
    }
    showArtistPanel(d.data);
    // Pin this artist while neighbors rearrange, then release
    d.fx = d.x; d.fy = d.y;
    setTimeout(() => { d.fx = null; d.fy = null; }, 1500);
  } else if (d.ntype === 'category') {
    const key = `${d.artistId}_${d.catType}`;
    expandedCategories.has(key) ? expandedCategories.delete(key) : expandedCategories.add(key);
  } else if (d.ntype === 'item') {
    if (d.linked_artist_id != null) {
      activateArtist(d.linked_artist_id);
      return;
    }
    selectedNodeId = d.id;
    showItemPanel(d);
  }
  render(true);
}

function activateArtist(artistId) {
  if (!expandedArtists.has(artistId)) expandedArtists.add(artistId);
  const artist = ARTISTS.find(a => a.id === artistId);
  if (artist) {
    if (artist.categories.members?.length) expandedCategories.add(`${artistId}_members`);
    showArtistPanel(artist);
  }
  render(true);
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

function applyFocus() {
  const ids = bfsArtists(focusArtistId, focusDepth);
  expandedArtists.clear();
  expandedCategories.clear();
  for (const id of ids) {
    expandedArtists.add(id);
    const a = ARTISTS.find(x => x.id === id);
    if (a) {
      for (const cat of Object.keys(a.categories)) {
        expandedCategories.add(`${id}_${cat}`);
      }
    }
  }
  render(true);
}

function focusOnArtist(artistId) {
  focusArtistId = artistId;
  document.getElementById('focus-slider').value = focusDepth;
  document.getElementById('focus-label').textContent = `Profundidad: ${focusDepth}`;
  document.getElementById('focus-bar').classList.add('active');
  applyFocus();
  setTimeout(() => {
    const node = sim.nodes().find(n => n.id === `a_${artistId}`);
    if (!node) return;
    const scale = 1.8;
    svg.transition().duration(600).call(
      zoom.transform,
      d3.zoomIdentity.translate(W() / 2 - node.x * scale, H() / 2 - node.y * scale).scale(scale)
    );
  }, 350);
}

function navigateToArtist(artistId) {
  const node = sim.nodes().find(n => n.id === `a_${artistId}`);
  if (node) {
    const scale = 1.8;
    svg.transition().duration(600).call(
      zoom.transform,
      d3.zoomIdentity.translate(W() / 2 - node.x * scale, H() / 2 - node.y * scale).scale(scale)
    );
  } else {
    focusOnArtist(artistId);
  }
}

function clearFocus() {
  focusArtistId = null;
  focusDepth = 1;
  document.getElementById('focus-slider').value = 1;
  document.getElementById('focus-label').textContent = 'Profundidad: 1';
  document.getElementById('focus-bar').classList.remove('active');
  expandedArtists.clear();
  expandedCategories.clear();
  render(true);
}

function showArtistPanel(artist) {
  const color  = COLORS.artists || '#e74c3c';
  const catCount = Object.keys(artist.categories).length;
  const memberOf = artist.member_of?.length
    ? `<p style="font-size:.72rem;color:#888;margin-bottom:6px">Miembro de: ${artist.member_of.join(', ')}</p>`
    : '';
  document.getElementById('panel').innerHTML = `
    <h2 style="color:${color}">${artist.name}</h2>
    ${memberOf}
    <p style="font-size:.75rem;color:#888;margin-bottom:8px">
      ${catCount} categoría${catCount !== 1 ? 's' : ''} · haz clic en una para expandir
    </p>`;
}

function linkifyArtists(text, mentionedArtists) {
  if (!mentionedArtists || !mentionedArtists.length) return text;
  // Sort longest name first to avoid partial replacements
  const sorted = [...mentionedArtists].sort((a, b) => b.name.length - a.name.length);
  let html = text;
  for (const { id, name } of sorted) {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    html = html.replace(
      new RegExp('\\b' + esc + '\\b', 'gi'),
      `<a class="artist-link" data-id="${id}">${name}</a>`
    );
  }
  return html;
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
        ${linkifyArtists(f.description, d.mentioned_artists)}
        ${f.source_file ? `<div class="fact-src">📂 ${f.source_file}</div>` : ''}
      </div>`).join('')}`;
}

svg.on('click', () => {
  selectedNodeId = null;
  document.getElementById('panel').innerHTML =
    '<p class="empty">Haz clic en un artista para explorar.</p>';
  render(true);
});

document.getElementById('panel').addEventListener('click', e => {
  const link = e.target.closest('.artist-link');
  if (!link) return;
  e.preventDefault();
  navigateToArtist(+link.dataset.id);
});

// ── Autocomplete search ───────────────────────────────────────────────────────
const searchEl = document.getElementById('search');
const acList   = document.getElementById('ac-list');
let   acActive = -1;

function highlight(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return text.slice(0, i) + '<mark>' + text.slice(i, i + q.length) + '</mark>' + text.slice(i + q.length);
}

function buildAcList(q) {
  acList.innerHTML = '';
  acActive = -1;
  const primaryArtists = ARTISTS.filter(a => a.is_primary);
  const matches = q
    ? primaryArtists.filter(a => a.name.toLowerCase().includes(q.toLowerCase()))
    : [...primaryArtists].sort((a, b) => a.name.localeCompare(b.name));
  if (!matches.length) { acList.classList.remove('open'); return; }
  matches.slice(0, q ? 15 : 500).forEach(artist => {
    const div = document.createElement('div');
    div.className = 'ac-item';
    div.innerHTML = highlight(artist.name, q);
    div.addEventListener('mousedown', e => { e.preventDefault(); selectAcItem(artist); });
    acList.appendChild(div);
  });
  acList.classList.add('open');
}

function selectAcItem(artist) {
  searchEl.value = '';
  acList.classList.remove('open');
  focusOnArtist(artist.id);
}

searchEl.addEventListener('input', () => buildAcList(searchEl.value));
searchEl.addEventListener('focus', () => buildAcList(searchEl.value));
searchEl.addEventListener('keydown', e => {
  const items = acList.querySelectorAll('.ac-item');
  if (!items.length) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); acActive = Math.min(acActive + 1, items.length - 1); }
  else if (e.key === 'ArrowUp')  { e.preventDefault(); acActive = Math.max(acActive - 1, 0); }
  else if (e.key === 'Enter' && acActive >= 0) {
    e.preventDefault();
    const q = searchEl.value.toLowerCase();
    const artist = ARTISTS.filter(a => a.is_primary && a.name.toLowerCase().includes(q))[acActive];
    if (artist) selectAcItem(artist);
    return;
  } else if (e.key === 'Escape') { acList.classList.remove('open'); return; }
  else { return; }
  items.forEach((el, i) => el.classList.toggle('active', i === acActive));
});
document.addEventListener('click', e => {
  if (!e.target.closest('#search-wrap')) acList.classList.remove('open');
});

window.addEventListener('resize', () => {
  sim.force('x', d3.forceX(W() / 2).strength(0.02))
     .force('y', d3.forceY(H() / 2).strength(0.02))
     .restart();
});

// ── Focus bar controls ────────────────────────────────────────────────────────
document.getElementById('focus-slider').addEventListener('input', function() {
  focusDepth = +this.value;
  document.getElementById('focus-label').textContent = `Profundidad: ${focusDepth}`;
  if (focusArtistId !== null) applyFocus();
});
document.getElementById('focus-back').addEventListener('click', clearFocus);

// ── Boot ──────────────────────────────────────────────────────────────────────
render();
'''


def inject_data(js, artists, relations):
    js = js.replace('/*ARTISTS*/[]',    json.dumps(artists,    ensure_ascii=False))
    js = js.replace('/*RELATIONS*/[]',  json.dumps(relations,  ensure_ascii=False))
    js = js.replace('/*COLORS*/{}',     json.dumps(TYPE_COLORS, ensure_ascii=False))
    js = js.replace('/*CAT_LABELS*/{}', json.dumps(CAT_LABELS, ensure_ascii=False))
    js = js.replace("/*DEFAULT_COLOR*/'#bdc3c7'", f"'{DEFAULT_COLOR}'")
    return js


def build_html(artists, relations):
    d3_src = get_d3()
    legend = ''.join(
        f'<div class="leg-item">'
        f'<div class="leg-dot" style="background:{color}"></div>'
        f'<span>{CAT_LABELS.get(t, t).capitalize()}</span></div>'
        for t, color in TYPE_COLORS.items()
    )
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
  <div id="focus-bar">
    <button id="focus-back">← Mapa completo</button>
    <div id="focus-depth-row">
      <span id="focus-label">Profundidad: 1</span>
      <input id="focus-slider" type="range" min="1" max="10" value="1">
    </div>
  </div>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Buscar artista...">
    <div id="ac-list"></div>
  </div>
  <div id="legend">{legend}</div>
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
        print(f'No se encuentra {DB_PATH}. Ejecuta primero md_to_sqlite.py')
        return

    artists, relations = load_data()
    if not artists:
        print('La base de datos está vacía.')
        return

    html = build_html(artists, relations)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    primary  = sum(1 for a in artists if a['is_primary'])
    n_cats   = sum(len(a['categories']) for a in artists)
    n_rels   = len(relations)
    print(f'{primary} artistas primarios ({len(artists)} total), '
          f'{n_cats} categorías, {n_rels} relaciones miembro → {OUT_HTML}')


if __name__ == '__main__':
    main()
