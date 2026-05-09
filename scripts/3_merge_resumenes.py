import json
import os
import re
from collections import defaultdict

RESUMENES_FOLDER   = './resumenes'
DATA_FOLDER        = './data'
TRANSCRIPTS_FOLDER = './transcripts'

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.+)')

# ── Podcast source helpers ─────────────────────────────────────────────────────

def load_podcast_env(folder):
    """Read podcast.env from folder. Returns (title, playlist_id, source_url).
    Keys accepted:
      TITLE= / NAME=            — podcast name
      PLAYLIST= / YT_PLAYLIST=  — YouTube playlist URL (playlist_id extracted)
      URL= / WEBSITE= / RSS=    — generic source URL (non-YouTube podcasts)
    """
    env_path = os.path.join(folder, 'podcast.env')
    if not os.path.exists(env_path):
        return '', '', ''
    title = ''
    playlist_id = ''
    source_url = ''
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            k, sep, v = line.strip().partition('=')
            if not sep:
                continue
            k = k.strip().upper()
            v = v.strip().strip('"').strip("'")
            if k in ('TITLE', 'NAME'):
                title = v
            elif k in ('PLAYLIST', 'YT_PLAYLIST'):
                m = re.search(r'[?&]list=([A-Za-z0-9_-]+)', v)
                if m:
                    playlist_id = m.group(1)
            elif k in ('URL', 'WEBSITE', 'RSS'):
                source_url = v
    return title, playlist_id, source_url

def extract_video_id(filename):
    """Extract YouTube video ID from 'Title [VID_ID].md' filenames."""
    m = re.search(r'\[([A-Za-z0-9_-]{8,12})\]', filename)
    return m.group(1) if m else ''

def extract_chapter_title(filename):
    """Extract chapter title from 'Chapter Title [VID_ID].md' filenames."""
    name = os.path.splitext(filename)[0]
    name = re.sub(r'\s*\[[A-Za-z0-9_-]{8,12}\]\s*$', '', name)
    return name.strip()

def make_source_str(podcast_title, video_id, playlist_id, chapter_title='', source_url=''):
    """Build source attribution string.
    YouTube:  'Podcast > Chapter | https://youtube.com/watch?v=VID&list=LIST'
    Generic:  'Podcast > Chapter | https://feeds.example.com/rss'
    No URL:   'Podcast > Chapter'
    """
    if video_id:
        url = f'https://www.youtube.com/watch?v={video_id}'
        if playlist_id:
            url += f'&list={playlist_id}'
    else:
        url = source_url
    parts = [p for p in (podcast_title, chapter_title) if p]
    label = ' > '.join(parts)
    if not label and not url:
        return ''
    if label and url:
        return f'{label} | {url}'
    return label or url

def _norm_ep(t):
    """Normaliza título de episodio para matching flexible."""
    t = t.lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def _transcripts_mirror(resumenes_root):
    """Devuelve la carpeta transcripts/ equivalente a una ruta de resumenes/."""
    norm = os.path.normpath(resumenes_root)
    base = os.path.normpath(RESUMENES_FOLDER)
    if norm.startswith(base):
        rel = os.path.relpath(norm, base)
        return os.path.join(TRANSCRIPTS_FOLDER, rel)
    return None

def load_episodes_index(folder):
    """Carga episodes.json → dict {título_normalizado: url_episodio}."""
    path = os.path.join(folder, 'episodes.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            _norm_ep(ep['title']): ep['url']
            for ep in data.get('episodes', [])
            if ep.get('title') and ep.get('url')
        }
    except Exception:
        return {}

def match_episode_url(chapter_title, index):
    """Intenta encontrar la URL del episodio más cercana al título del capítulo.
    Prueba: exacto → uno contiene al otro → mayor solapamiento de palabras."""
    if not chapter_title or not index:
        return ''
    norm = _norm_ep(chapter_title)
    if norm in index:
        return index[norm]
    # Containment match
    for ep_norm, url in index.items():
        if norm in ep_norm or ep_norm in norm:
            return url
    # Word-overlap fallback: ≥ 60 % de palabras coinciden
    words = set(norm.split())
    best_url, best_ratio = '', 0.0
    for ep_norm, url in index.items():
        ep_words = set(ep_norm.split())
        if not ep_words:
            continue
        ratio = len(words & ep_words) / max(len(words), len(ep_words))
        if ratio > best_ratio:
            best_ratio, best_url = ratio, url
    return best_url if best_ratio >= 0.6 else ''

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
        self.concerts    = []
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

def parse_folder(folder, artists, genres, labels, concerts, instruments, standalone):
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
        'concert': concerts, 'instrument': instruments
    }

    # Cache podcast.env y episodes.json por directorio
    _env_cache = {}
    _ep_cache  = {}

    def _load_env_with_fallback(root):
        """Carga podcast.env; si no existe en resumenes/, busca en transcripts/."""
        env = load_podcast_env(root)
        if not env[0] and not env[2]:  # sin título ni URL
            alt = _transcripts_mirror(root)
            if alt and os.path.isdir(alt):
                env = load_podcast_env(alt)
        return env

    def _load_ep_index(root):
        """Carga episodes.json; busca también en la carpeta transcripts/ espejo."""
        idx = load_episodes_index(root)
        if not idx:
            alt = _transcripts_mirror(root)
            if alt and os.path.isdir(alt):
                idx = load_episodes_index(alt)
        return idx

    def get_file_source(root, filename):
        if root not in _env_cache:
            _env_cache[root] = _load_env_with_fallback(root)
        title, playlist_id, source_url = _env_cache[root]

        video_id      = extract_video_id(filename)
        chapter_title = extract_chapter_title(filename)

        # Para fuentes no-YouTube, intentar URL específica del episodio
        if not video_id and chapter_title:
            if root not in _ep_cache:
                _ep_cache[root] = _load_ep_index(root)
            ep_url = match_episode_url(chapter_title, _ep_cache[root])
            if ep_url:
                source_url = ep_url

        return make_source_str(title, video_id, playlist_id, chapter_title, source_url)

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
                    m = re.match(r'^#\s+(artist|genre|label|venue|concert|instrument)\s+-\s+(.+)', s, re.IGNORECASE)
                    if m:
                        ctx_type = m.group(1).lower()
                        ctx_name = m.group(2).strip()
                        # Normalise legacy 'venue' → 'concert'
                        if ctx_type == 'venue':
                            ctx_type = 'concert'
                        section = None
                        if ctx_type == 'artist':
                            get_artist(ctx_name)
                        else:
                            get_entity(store_for[ctx_type], ctx_name)
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
                        list_keys = {'members', 'member_of', 'genres', 'labels', 'concerts', 'instruments'}
                        if section in list_keys:
                            name = s.lstrip('- ').strip()
                            if not name: continue
                            norm = section.replace(' ', '_')
                            artist.add_list(norm, name)
                            # Maintain inverse member relationships automatically
                            if norm == 'members':
                                # The listed name is a member → that person's member_of = ctx_name
                                get_artist(name).add_list('member_of', ctx_name)
                            elif norm == 'member_of':
                                # ctx_name is a member of the listed band → band's members = ctx_name
                                get_artist(name).add_list('members', ctx_name)
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

_ENRICHMENT_SECTIONS = {'awards', 'charts', 'lists'}

def _read_enrichment_sections(path):
    """Lee secciones ## awards/charts/lists de un archivo existente para preservarlas."""
    if not os.path.exists(path):
        return ''
    blocks = []
    current = []
    inside = False
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^##\s+(\w+)', line)
            if m:
                if inside and current:
                    blocks.append(''.join(current))
                inside = m.group(1).lower() in _ENRICHMENT_SECTIONS
                current = [line] if inside else []
            elif inside:
                current.append(line)
    if inside and current:
        blocks.append(''.join(current))
    return '\n'.join(blocks)


def write_artist(artist, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(artist.name) + '.md')

    # Preservar secciones de enriquecimiento (awards, charts, lists) si ya existen
    enrichment = _read_enrichment_sections(path)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# artist - {artist.name}\n\n')

        # El orden y los nombres de las secciones deben coincidir con LIST_SECTIONS en md_to_sqlite.py
        _write_list_section(f, 'member of', artist.member_of)
        _write_list_section(f, 'members', artist.members)
        _write_list_section(f, 'genres', artist.genres)
        _write_list_section(f, 'labels', artist.labels)
        _write_list_section(f, 'concerts', artist.concerts)
        _write_list_section(f, 'instruments', artist.instruments)

        _write_entry_section(f, 'albums', artist.albums)
        _write_entry_section(f, 'songs', artist.songs)
        _write_entry_section(f, 'curiosities', artist.curiosities)

        if enrichment:
            f.write('\n' + enrichment)

def write_entity(etype, entity, out_dir, artist_names=None):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(entity.name) + '.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'# {etype} - {entity.name}\n\n')
        _write_entry_section(f, 'curiosities', entity.curiosities)
        if artist_names:
            _write_list_section(f, 'artists', sorted(artist_names))

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
    artists, genres, labels, concerts, instruments, standalone = {}, {}, {}, {}, {}, {}

    # 1. Cargar datos existentes para no perder relaciones previas
    if os.path.exists(DATA_FOLDER):
        parse_folder(DATA_FOLDER, artists, genres, labels, concerts, instruments, standalone)

    # 2. Mezclar nuevos resumenes
    if os.path.exists(RESUMENES_FOLDER):
        parse_folder(RESUMENES_FOLDER, artists, genres, labels, concerts, instruments, standalone)

    # 3. Construir índice inverso: entidad → artistas que la usan
    entity_artists = {
        'genre':      defaultdict(set),
        'label':      defaultdict(set),
        'concert':    defaultdict(set),
        'instrument': defaultdict(set),
    }
    for a in artists.values():
        for g in a.genres:      entity_artists['genre'][g].add(a.name)
        for l in a.labels:      entity_artists['label'][l].add(a.name)
        for c in a.concerts:    entity_artists['concert'][c].add(a.name)
        for i in a.instruments: entity_artists['instrument'][i].add(a.name)

    # 4. Guardar con el formato exacto requerido por md_to_sqlite.py
    artist_dir = os.path.join(DATA_FOLDER, 'artists')
    for a in artists.values(): write_artist(a, artist_dir)

    for etype, store, subdir in [
        ('genre',      genres,      'genres'),
        ('label',      labels,      'labels'),
        ('concert',    concerts,    'concerts'),
        ('instrument', instruments, 'instruments'),
    ]:
        d = os.path.join(DATA_FOLDER, subdir)
        for e in store.values():
            write_entity(etype, e, d, artist_names=entity_artists[etype].get(e.name))

    write_standalone_curiosities(standalone, DATA_FOLDER)

    n_artists  = len(artists)
    n_members  = sum(1 for a in artists.values() if a.member_of)
    print(f"Mezcla finalizada: {n_artists} artistas ({n_members} con member_of), "
          f"{len(genres)} géneros, {len(labels)} sellos, "
          f"{len(concerts)} conciertos, {len(instruments)} instrumentos.")

if __name__ == '__main__':
    main()
