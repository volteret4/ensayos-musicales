#!/usr/bin/env python3
"""
edit_data.py — Interactive music data editor
Run: python edit_data.py
Open: http://localhost:8765
"""
import os, json, re, sqlite3, subprocess, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from edit_data_html import HTML

PORT        = 8765
DB_PATH     = './music_facts.db'
DATA_FOLDER = './data'

TYPE_TO_DIR = {
    'artist': 'artists', 'genre': 'genres', 'label': 'labels',
    'concert': 'concerts', 'instrument': 'instruments',
}

# ── Slug (identical to merge_resumenes.py) ────────────────────────────────────
def slug(name):
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s.strip('-') or 'unknown'

def entity_filepath(etype, name):
    d = TYPE_TO_DIR.get(etype, etype + 's')
    return os.path.join(DATA_FOLDER, d, slug(name) + '.md')

# ── MD helpers ────────────────────────────────────────────────────────────────
def _read(fp):
    with open(fp, 'r', encoding='utf-8') as f:
        return f.readlines()

def _write(fp, lines):
    with open(fp, 'w', encoding='utf-8') as f:
        f.writelines(lines)

def _section_name(line):
    """Return normalised section name if line is a ## header, else None."""
    m = re.match(r'^##\s+(.+)', line.strip())
    return m.group(1).strip().lower().replace(' ', '_') if m else None

def delete_entry(fp, section, key, is_list=False):
    """Remove one entry (list item or **key** line) from a section."""
    lines = _read(fp)
    out, in_sec = [], False
    kl = key.strip().lower()
    for line in lines:
        s   = line.strip()
        sec = _section_name(line)
        if sec is not None:
            in_sec = (sec == section.lower().replace(' ', '_'))
            out.append(line); continue
        if s.startswith('# '):
            in_sec = False; out.append(line); continue
        if in_sec:
            if is_list and s.startswith('- ') and s[2:].strip().lower() == kl:
                continue
            if not is_list and s.startswith('**'):
                m = re.match(r'^\*\*(.+?)\*\*', s)
                if m and m.group(1).strip().lower() == kl:
                    continue
        out.append(line)
    _write(fp, out)

def delete_section(fp, section):
    """Remove an entire ## section block."""
    lines = _read(fp)
    out, skip = [], False
    norm = section.lower().replace(' ', '_')
    for line in lines:
        s   = line.strip()
        sec = _section_name(line)
        if sec is not None:
            skip = (sec == norm)
            if not skip: out.append(line)
            continue
        if s.startswith('# '):
            skip = False; out.append(line); continue
        if not skip:
            out.append(line)
    _write(fp, out)

def add_entry_to_md(fp, section, key, desc='', is_list=False):
    """Append a new entry to a section, creating it if absent."""
    lines = _read(fp)
    norm     = section.lower().replace(' ', '_')
    new_line = f'- {key}\n' if is_list else f'**{key}** : {desc}\n'

    sec_start = None
    for i, line in enumerate(lines):
        if _section_name(line) == norm:
            sec_start = i; break

    if sec_start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += [f'\n## {section}\n', new_line]
    else:
        end = len(lines)
        for i in range(sec_start + 1, len(lines)):
            s = lines[i].strip()
            if s.startswith('##') or (s.startswith('#') and not s.startswith('##')):
                end = i; break
        while end > sec_start + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, new_line)

    _write(fp, lines)

def delete_standalone_curiosity(title):
    """Remove a **title** entry from data/curiosities.md."""
    fp = os.path.join(DATA_FOLDER, 'curiosities.md')
    if not os.path.exists(fp): return
    lines = _read(fp)
    out, kl = [], title.strip().lower()
    for line in lines:
        s = line.strip()
        if s.startswith('**'):
            m = re.match(r'^\*\*(.+?)\*\*', s)
            if m and m.group(1).strip().lower() == kl:
                continue
        out.append(line)
    _write(fp, out)

def rename_entity(etype, old_name, new_name):
    """Rename entity file + update its header + update list refs in artist files."""
    old_fp = entity_filepath(etype, old_name)
    new_fp = entity_filepath(etype, new_name)

    if os.path.exists(old_fp):
        lines = _read(old_fp)
        out = []
        for line in lines:
            if re.match(r'^#\s+\w+\s+-\s+', line):
                out.append(f'# {etype} - {new_name}\n')
            else:
                out.append(line)
        _write(old_fp, out)
        if old_fp != new_fp:
            os.rename(old_fp, new_fp)

    # Update list references in all artist files
    artist_dir = os.path.join(DATA_FOLDER, 'artists')
    if not os.path.isdir(artist_dir): return
    sec_key   = etype + 's'          # genres → genres section key
    old_lower = old_name.strip().lower()
    for fn in os.listdir(artist_dir):
        if not fn.endswith('.md'): continue
        fp2 = os.path.join(artist_dir, fn)
        lines = _read(fp2)
        out, in_sec, changed = [], False, False
        for line in lines:
            s   = line.strip()
            sec = _section_name(line)
            if sec is not None:
                in_sec = (sec == sec_key)
                out.append(line); continue
            if s.startswith('# '):
                in_sec = False; out.append(line); continue
            if in_sec and s.startswith('- ') and s[2:].strip().lower() == old_lower:
                out.append(f'- {new_name}\n'); changed = True
            else:
                out.append(line)
        if changed:
            _write(fp2, out)

def edit_entry(fp, section, old_key, new_title, new_desc):
    """Replace **old_key** : … with **new_title** : new_desc."""
    lines = _read(fp)
    out, in_sec = [], False
    kl = old_key.strip().lower()
    for line in lines:
        s   = line.strip()
        sec = _section_name(line)
        if sec is not None:
            in_sec = (sec == section.lower().replace(' ', '_'))
            out.append(line); continue
        if s.startswith('# '):
            in_sec = False; out.append(line); continue
        if in_sec and s.startswith('**'):
            m = re.match(r'^\*\*(.+?)\*\*', s)
            if m and m.group(1).strip().lower() == kl:
                out.append(f'**{new_title}** : {new_desc}\n'); continue
        out.append(line)
    _write(fp, out)

# ── SQLite data loading ───────────────────────────────────────────────────────
def load_data():
    if not os.path.exists(DB_PATH):
        return None
    conn = sqlite3.connect(DB_PATH)
    tabs = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    artists = {}
    for aid, name, isp in conn.execute('SELECT id, name, is_primary FROM artists ORDER BY name'):
        artists[aid] = {
            'id': aid, 'name': name, 'is_primary': bool(isp),
            'member_of': [], 'members': [], 'genres': [], 'labels': [],
            'concerts': [], 'instruments': [], 'albums': [], 'songs': [], 'curiosities': [],
        }

    if 'band_members' in tabs:
        for bid, mid in conn.execute('SELECT band_id, member_id FROM band_members'):
            if bid in artists and mid in artists:
                artists[bid]['members'].append({'id': mid, 'name': artists[mid]['name']})
                artists[mid]['member_of'].append({'id': bid, 'name': artists[bid]['name']})

    for field, junc, etab, fk in [
        ('genres',      'artist_genres',      'genres',      'genre_id'),
        ('labels',      'artist_labels',      'labels',      'label_id'),
        ('concerts',    'artist_concerts',    'concerts',    'concert_id'),
        ('instruments', 'artist_instruments', 'instruments', 'instrument_id'),
    ]:
        if junc not in tabs: continue
        for aid, name in conn.execute(
            f'SELECT j.artist_id, e.name FROM {junc} j JOIN {etab} e ON j.{fk}=e.id ORDER BY e.name'
        ):
            if aid in artists: artists[aid][field].append(name)

    if 'albums' in tabs and 'albums_data' in tabs:
        buf = {}
        for aid, name, arid in conn.execute('SELECT id, name, artist_id FROM albums ORDER BY name'):
            if arid in artists: buf[aid] = {'arid': arid, 'name': name, 'facts': []}
        for aid, desc, sf in conn.execute('SELECT album_id, description, source_file FROM albums_data'):
            if aid in buf: buf[aid]['facts'].append({'description': desc, 'source_file': sf or ''})
        for al in buf.values():
            artists[al['arid']]['albums'].append({'name': al['name'], 'facts': al['facts']})

    if 'songs' in tabs and 'songs_data' in tabs:
        buf = {}
        for sid, name, arid in conn.execute('SELECT id, name, artist_id FROM songs ORDER BY name'):
            if arid in artists: buf[sid] = {'arid': arid, 'name': name, 'facts': []}
        for sid, desc, sf in conn.execute('SELECT song_id, description, source_file FROM songs_data'):
            if sid in buf: buf[sid]['facts'].append({'description': desc, 'source_file': sf or ''})
        for sg in buf.values():
            artists[sg['arid']]['songs'].append({'name': sg['name'], 'facts': sg['facts']})

    if 'curiosities' in tabs:
        for title, desc, sf, cid in conn.execute(
            "SELECT title, description, source_file, context_id "
            "FROM curiosities WHERE context_type='artist' ORDER BY title"
        ):
            if cid in artists:
                artists[cid]['curiosities'].append(
                    {'name': title, 'facts': [{'description': desc, 'source_file': sf or ''}]}
                )

    entities = {}
    for etype, table in [('genre','genres'),('label','labels'),('concert','concerts'),('instrument','instruments')]:
        elist = []
        if table in tabs:
            for eid, name in conn.execute(f'SELECT id, name FROM {table} ORDER BY name'):
                elist.append({'id': eid, 'name': name, 'curiosities': []})
        entities[etype] = elist

    if 'curiosities' in tabs:
        idx = {}
        for etype, elist in entities.items():
            for e in elist: idx[(etype, e['id'])] = e
        for title, desc, sf, ctype, cid in conn.execute(
            "SELECT title, description, source_file, context_type, context_id "
            "FROM curiosities WHERE context_type NOT IN ('artist','general') ORDER BY title"
        ):
            k = (ctype, cid)
            if k in idx:
                idx[k]['curiosities'].append({'title': title, 'description': desc, 'source_file': sf or ''})

    gen = []
    if 'curiosities' in tabs:
        for i, (title, desc, sf) in enumerate(conn.execute(
            "SELECT title, description, source_file FROM curiosities "
            "WHERE context_type='general' ORDER BY title"
        )):
            gen.append({'id': i, 'title': title, 'description': desc, 'source_file': sf or ''})

    conn.close()
    primary = sorted(
        [a for a in artists.values() if a['is_primary']],
        key=lambda x: re.sub(r'^(The|Los|Las)\s+', '', x['name'], flags=re.IGNORECASE),
    )
    return {
        'artists': primary,
        'genres':  entities['genre'],  'labels':      entities['label'],
        'concerts': entities['concert'], 'instruments': entities['instrument'],
        'gen_curiosities': gen,
    }

# ── DB rebuild ────────────────────────────────────────────────────────────────
def rebuild_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    r1 = subprocess.run([sys.executable, 'md_to_sqlite.py'],  capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, 'find_mentions.py'], capture_output=True, text=True)
    return {
        'ok':  r1.returncode == 0 and r2.returncode == 0,
        'out': (r1.stdout + r2.stdout).strip(),
        'err': (r1.stderr + r2.stderr).strip(),
    }

# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def _json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(b))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/data':
            d = load_data()
            self._json(d if d is not None else {'error': 'No DB — run md_to_sqlite.py first'}, 200 if d else 500)
            return
        # Serve main HTML for everything else
        b = HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(b))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            d = self._body()
        except Exception as e:
            self._json({'error': str(e)}, 400); return

        if path == '/api/rebuild':
            self._json(rebuild_db()); return

        etype = d.get('type', '')
        name  = d.get('name', '')

        if path == '/api/delete/entity':
            fp = entity_filepath(etype, name)
            if os.path.exists(fp): os.remove(fp)
            self._json({'ok': True}); return

        fp = entity_filepath(etype, name)
        if not os.path.exists(fp):
            self._json({'error': f'File not found: {fp}'}, 404); return

        section = d.get('section', '')

        if path == '/api/delete/section':
            delete_section(fp, section)
            self._json({'ok': True}); return

        key = d.get('key', '')

        if path == '/api/delete/entry':
            delete_entry(fp, section, key, is_list=d.get('is_list', False))
            self._json({'ok': True}); return

        if path == '/api/edit/entry':
            edit_entry(fp, section, key, d.get('new_title', key), d.get('new_desc', ''))
            self._json({'ok': True}); return

        if path == '/api/add/entry':
            add_entry_to_md(fp, section, key,
                            desc=d.get('desc', ''),
                            is_list=d.get('is_list', False))
            self._json({'ok': True}); return

        if path == '/api/rename/entity':
            new_name = d.get('new_name', '')
            if not new_name:
                self._json({'error': 'new_name required'}, 400); return
            rename_entity(etype, name, new_name)
            self._json({'ok': True}); return

        if path == '/api/delete/curiosity':
            delete_standalone_curiosity(key)
            self._json({'ok': True}); return

        self._json({'error': 'Unknown endpoint'}, 404)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'Music Editor → http://localhost:{PORT}')
    print('Ctrl+C to stop')
    HTTPServer(('', PORT), Handler).serve_forever()
