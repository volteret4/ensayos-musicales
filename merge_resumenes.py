import os
import re
from collections import defaultdict

RESUMENES_FOLDER = './resumenes'
DATA_FOLDER      = './data'

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.+)')

# ── Podcast source helpers ─────────────────────────────────────────────────────

def load_podcast_env(folder):
    """Read podcast.env from folder. Returns (title, playlist_id)."""
    env_path = os.path.join(folder, 'podcast.env')
    if not os.path.exists(env_path):
        return '', ''
    title = ''
    playlist_id = ''
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            k, sep, v = line.strip().partition('=')
            if not sep:
                continue
            k = k.strip().upper()
            v = v.strip()
            if k == 'TITLE':
                title = v
            elif k == 'PLAYLIST':
                m = re.search(r'[?&]list=([A-Za-z0-9_-]+)', v)
                if m:
                    playlist_id = m.group(1)
    return title, playlist_id

def extract_video_id(filename):
    """Extract YouTube video ID from 'Title [VID_ID].md' filenames."""
    m = re.search(r'\[([A-Za-z0-9_-]{8,12})\]', filename)
    return m.group(1) if m else ''

def make_source_str(podcast_title, video_id, playlist_id):
    """Build 'podcast_title | https://youtube.com/watch?v=VID&list=LIST'."""
    if not video_id:
        return ''
    url = f'https://www.youtube.com/watch?v={video_id}'
    if playlist_id:
        url += f'&list={playlist_id}'
    if podcast_title:
        return f'{podcast_title} | {url}'
    return url

def slug(name):
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s.strip('-') or 'unknown'

class ArtistData:
    def __init__(self, name):
        self.name        = name
        self.members     = []
        self.member_of   = []
        self.genres      = []
        self.labels      = []
        self.venues      = []
        self.instruments = []
        self.albums      = {}
        self.songs       = {}
        self.curiosities = {}

    def add_list(self, section, name):
        target = getattr(self, section, None)
        # Normalizamos a minúsculas para evitar duplicados por capitalización
        if target is not None and name not in target:
            target.append(name)

    def add_entry(self, section, title, desc, source=''):
        target = getattr(self, section, None)
        if target is not None and title not in target:
            target[title] = desc + (f' ← {source}' if source else '')

class EntityData:
    def __init__(self, name):
        self.name        = name
        self.curiosities = {}

    def add_entry(self, title, desc, source=''):
        if title not in self.curiosities:
            self.curiosities[title] = desc + (f' ← {source}' if source else '')

# ── Parser compatible con ambos sentidos ──────────────────────────────────────

def parse_folder(folder, artists, genres, labels, venues, instruments, standalone):
    if not os.path.exists(folder):
        return

    def get_artist(name):
        if name not in artists: artists[name] = ArtistData(name)
        return artists[name]

    def get_entity(store, name):
        if name not in store: store[name] = EntityData(name)
        return store[name]

    store_for = {
        'genre': genres, 'label': labels,
        'venue': venues, 'instrument': instruments
    }

    # Cache podcast.env data per directory to avoid repeated reads
    _env_cache = {}
    def get_file_source(root, filename):
        if root not in _env_cache:
            _env_cache[root] = load_podcast_env(root)
        title, playlist_id = _env_cache[root]
        video_id = extract_video_id(filename)
        return make_source_str(title, video_id, playlist_id)

    for root, _dirs, files in os.walk(folder):
        for filename in sorted(files):
            if not filename.endswith('.md'): continue
            filepath = os.path.join(root, filename)
            file_source = get_file_source(root, filename)

            ctx_type, ctx_name, section = None, None, None

            with open(filepath, 'r', encoding='utf-8') as fh:
                for raw in fh:
                    s = raw.strip()
                    if not s: continue

                    # Detectar cabecera principal
                    m = re.match(r'^#\s+(artist|genre|label|venue|instrument)\s+-\s+(.+)', s, re.IGNORECASE)
                    if m:
                        ctx_type, ctx_name = m.group(1).lower(), m.group(2).strip()
                        section = None
                        if ctx_type == 'artist': get_artist(ctx_name)
                        else: get_entity(store_for[ctx_type], ctx_name)
                        continue

                    if re.match(r'^#\s+curiosity\s*$', s, re.IGNORECASE):
                        ctx_type, ctx_name, section = 'standalone', None, 'curiosities'
                        continue

                    # Detectar Sub-secciones
                    m_sub = re.match(r'^##\s+(.+)', s, re.IGNORECASE)
                    if m_sub:
                        section = m_sub.group(1).strip().lower()
                        continue

                    if ctx_type is None or section is None: continue

                    # Procesar contenido según el tipo de sección
                    if ctx_type == 'standalone':
                        me = ENTRY_RE.match(s)
                        if me:
                            t, d = me.group(1).strip(), me.group(2).strip()
                            if t not in standalone:
                                standalone[t] = d + (f' ← {file_source}' if file_source else '')

                    elif ctx_type == 'artist':
                        artist = get_artist(ctx_name)
                        list_keys = {'members', 'member_of', 'genres', 'labels', 'venues', 'instruments'}
                        if section in list_keys:
                            name = s.lstrip('- ').strip()
                            if name: artist.add_list(section.replace(' ', '_'), name)
                        else:
                            me = ENTRY_RE.match(s)
                            if me:
                                artist.add_entry(section.replace(' ', '_'),
                                                 me.group(1).strip(), me.group(2).strip(),
                                                 source=file_source)

                    else:  # Géneros, sellos, etc.
                        entity = get_entity(store_for[ctx_type], ctx_name)
                        if section == 'curiosities':
                            me = ENTRY_RE.match(s)
                            if me:
                                entity.add_entry(me.group(1).strip(), me.group(2).strip(),
                                                 source=file_source)

# ── Escritores con formato compatible con md_to_sqlite.py ─────────────────────

def _write_list_section(f, header, items):
    """Escribe listas con guiones para que el script SQL las reconozca."""
    if items:
        f.write(f'## {header}\n')
        for item in sorted(set(items)):
            f.write(f'- {item}\n')
        f.write('\n')

def _write_entry_section(f, header, entries):
    """Escribe entradas con formato **Key** : Value."""
    if entries:
        f.write(f'## {header}\n')
        for t, d in sorted(entries.items()):
            f.write(f'**{t}** : {d}\n')
        f.write('\n')

def write_artist(artist, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(artist.name) + '.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# artist - {artist.name}\n\n')

        # El orden y los nombres de las secciones deben coincidir con LIST_SECTIONS en md_to_sqlite.py
        _write_list_section(f, 'member of', artist.member_of)
        _write_list_section(f, 'members', artist.members)
        _write_list_section(f, 'genres', artist.genres)
        _write_list_section(f, 'labels', artist.labels)
        _write_list_section(f, 'venues', artist.venues)
        _write_list_section(f, 'instruments', artist.instruments)

        _write_entry_section(f, 'albums', artist.albums)
        _write_entry_section(f, 'songs', artist.songs)
        _write_entry_section(f, 'curiosities', artist.curiosities)

def write_entity(etype, entity, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(entity.name) + '.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {etype} - {entity.name}\n\n')
        _write_entry_section(f, 'curiosities', entity.curiosities)

def write_standalone_curiosities(standalone, out_dir):
    if not standalone: return
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'curiosities.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# curiosity\n\n')
        for t, d in sorted(standalone.items()):
            f.write(f'**{t}** : {d}\n')

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    artists, genres, labels, venues, instruments, standalone = {}, {}, {}, {}, {}, {}

    # 1. Cargar datos existentes para no perder relaciones previas
    if os.path.exists(DATA_FOLDER):
        parse_folder(DATA_FOLDER, artists, genres, labels, venues, instruments, standalone)

    # 2. Mezclar nuevos resumenes
    if os.path.exists(RESUMENES_FOLDER):
        parse_folder(RESUMENES_FOLDER, artists, genres, labels, venues, instruments, standalone)

    # 3. Guardar con el formato exacto requerido por md_to_sqlite.py
    artist_dir = os.path.join(DATA_FOLDER, 'artists')
    for a in artists.values(): write_artist(a, artist_dir)

    for etype, store, subdir in [
        ('genre', genres, 'genres'), ('label', labels, 'labels'),
        ('venue', venues, 'venues'), ('instrument', instruments, 'instruments'),
    ]:
        d = os.path.join(DATA_FOLDER, subdir)
        for e in store.values(): write_entity(etype, e, d)

    write_standalone_curiosities(standalone, DATA_FOLDER)
    print("Mezcla finalizada respetando el formato de relaciones SQL.")

if __name__ == '__main__':
    main()
