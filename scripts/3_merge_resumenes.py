"""
3_merge_resumenes.py — Incorpora los resúmenes NUEVOS de resumenes/ a data/ y pendiente/.

Incremental: recuerda qué resúmenes ya se han incorporado en
correcciones/resumenes_procesados.txt y solo lee los nuevos, así no vuelve a
traer los nombres mal escritos que ya se corrigieron.

Al incorporar, aplica correcciones/decisiones_artistas.txt (nombres canónicos,
fusiones, borrados, relaciones [Grupo] Miembro, títulos) y lo borrado en el
editor web (correcciones/deleted.json). Nunca quita nada de las fichas: solo
añade. Cada artista tocado se apunta en correcciones/cola_revision.txt para
revisarlo después por lotes con Claude (scripts/limpieza/revisar_lote.py).

Uso:
    python3 scripts/3_merge_resumenes.py                # incorpora lo nuevo
    python3 scripts/3_merge_resumenes.py --dry-run      # solo informa
    python3 scripts/3_merge_resumenes.py --inicializar  # marca todo lo actual como ya incorporado
"""
import json
import os
import re
import sys
from collections import defaultdict

RESUMENES_FOLDER   = './resumenes'
DATA_FOLDER        = './data'
PENDING_FOLDER     = './pendiente'
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

# ── Contenedores de lo leído en los resúmenes ─────────────────────────────────

class ArtistData:
    def __init__(self, name):
        self.name        = name
        self.files       = set()           # resúmenes (rutas relativas) donde aparece
        self.members     = []
        self.member_of   = []
        self.genres      = []
        self.labels      = []
        self.concerts    = []
        self.instruments = []
        self.albums      = []              # [(título, descripción ← fuente)]
        self.songs       = []
        self.curiosities = []

    def add_list(self, section, name):
        target = getattr(self, section, None)
        if target is not None and name not in target:
            target.append(name)

    def add_entry(self, section, title, desc, source=''):
        # Se guardan todas: varias fuentes pueden contar cosas distintas con el mismo título
        target = getattr(self, section, None)
        item = (title, desc + (f' ← {source}' if source else ''))
        if target is not None and item not in target:
            target.append(item)


class EntityData:
    def __init__(self, name):
        self.name        = name
        self.curiosities = []

    def add_entry(self, title, desc, source=''):
        item = (title, desc + (f' ← {source}' if source else ''))
        if item not in self.curiosities:
            self.curiosities.append(item)

# ── Parser compatible con ambos sentidos ──────────────────────────────────────

def parse_folder(folder, artists, genres, labels, concerts, instruments, standalone, only=None):
    """Lee los .md de folder. Con only (conjunto de rutas relativas a RESUMENES_FOLDER) solo esos."""
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
            rel = os.path.relpath(filepath, folder)
            if only is not None and rel not in only: continue
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
                            get_artist(ctx_name).files.add(rel)
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

# ── Ficheros .md existentes: lectura y escritura conservando todo ─────────────

LIST_SECTIONS  = ['member of', 'members', 'genres', 'labels', 'concerts', 'instruments']
ENTRY_SECTIONS = ['albums', 'songs', 'curiosities']


def _strip_source(desc):
    return re.sub(r'\s+←.*$', '', desc).strip()


class MdFile:
    """Ficha .md de entidad: cabecera + secciones en orden. Solo añade, nunca quita."""

    def __init__(self, path, etype='artist', name=None):
        self.path, self.etype = path, etype
        self.name = name
        self.order, self.secs = [], {}
        self.changed = not os.path.exists(path)
        if os.path.exists(path):
            sec = None
            with open(path, 'r', encoding='utf-8') as f:
                for raw in f:
                    s = raw.rstrip('\n')
                    m = re.match(r'^#\s+\w+\s+-\s+(.+)$', s)
                    if m and not s.startswith('##'):
                        self.name = m.group(1).strip(); continue
                    m = re.match(r'^##\s+(.+)$', s)
                    if m:
                        sec = m.group(1).strip().lower()
                        if sec not in self.secs:
                            self.order.append(sec); self.secs[sec] = []
                        continue
                    if sec is not None and s.strip():
                        self.secs[sec].append(s.strip())

    def _sec(self, sec):
        if sec not in self.secs:
            self.order.append(sec); self.secs[sec] = []
        return self.secs[sec]

    def has_list(self, sec, item):
        k = nkey(item)
        return any(nkey(x.lstrip('- ').strip()) == k for x in self.secs.get(sec, []))

    def add_list(self, sec, item):
        if item and not self.has_list(sec, item):
            self._sec(sec).append(f'- {item}')
            self.changed = True
            return True
        return False

    def add_entry(self, sec, title, desc):
        """Añade '**título** : desc' salvo que ya exista la misma descripción (sin fuente)."""
        core = _strip_source(desc)
        for line in self.secs.get(sec, []):
            m = ENTRY_RE.match(line)
            if m and _strip_source(m.group(2)) == core:
                return False
        self._sec(sec).append(f'**{title}** : {desc}')
        self.changed = True
        return True

    def titles(self, sec):
        return [m.group(1).strip() for l in self.secs.get(sec, []) if (m := ENTRY_RE.match(l))]

    def save(self):
        if not self.changed:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        canon_order = LIST_SECTIONS + ENTRY_SECTIONS
        order = [s for s in canon_order if s in self.secs] + [s for s in self.order if s not in canon_order]
        out = [f'# {self.etype} - {self.name}\n']
        for sec in order:
            if self.secs[sec]:
                out.append(f'\n## {sec}\n' + '\n'.join(self.secs[sec]) + '\n')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(''.join(out))


# ── Main ──────────────────────────────────────────────────────────────────────

PROCESADOS   = './correcciones/resumenes_procesados.txt'
DELETED_JSON = './correcciones/deleted.json'

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'limpieza'))
import limpiar_artistas as L          # noqa: E402  (decisiones, nombres canónicos)
import lotes                          # noqa: E402  (cola de revisión)
nkey = L.norm


def _todos_los_resumenes():
    out = []
    for root, _d, files in os.walk(RESUMENES_FOLDER):
        for fn in files:
            if fn.endswith('.md') and fn not in ('README.md', 'CLAUDE.md'):
                out.append(os.path.relpath(os.path.join(root, fn), RESUMENES_FOLDER))
    return sorted(out)


def _cargar_procesados():
    if not os.path.exists(PROCESADOS):
        return None
    with open(PROCESADOS, 'r', encoding='utf-8') as f:
        return {l.rstrip('\n') for l in f if l.strip()}


def _guardar_procesados(conj):
    os.makedirs(os.path.dirname(PROCESADOS), exist_ok=True)
    with open(PROCESADOS, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(conj)) + '\n')


def _indice(subdir):
    """nombre normalizado → ruta del .md (data/ tiene prioridad sobre pendiente/)."""
    idx = {}
    for base in (PENDING_FOLDER, DATA_FOLDER):
        d = os.path.join(base, subdir)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.md'):
                continue
            p = os.path.join(d, fn)
            with open(p, 'r', encoding='utf-8') as f:
                first = f.readline()
            m = re.match(r'^#\s+\w+\s+-\s+(.+)$', first.strip())
            idx[nkey(m.group(1) if m else fn[:-3])] = p
    return idx


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Incorpora los resúmenes nuevos a data/ y pendiente/')
    ap.add_argument('--inicializar', action='store_true',
                    help='marca todos los resúmenes actuales como ya incorporados (no mezcla nada)')
    ap.add_argument('--dry-run', action='store_true', help='no escribe nada, solo informa')
    ap.add_argument('--sin-limpieza', action='store_true',
                    help='no ejecuta limpiar_artistas.py --in-place al terminar')
    args = ap.parse_args()

    todos = _todos_los_resumenes()
    if args.inicializar:
        _guardar_procesados(set(todos))
        print(f'{len(todos)} resúmenes marcados como incorporados en {PROCESADOS}')
        return
    procesados = _cargar_procesados()
    if procesados is None:
        print(f'Falta {PROCESADOS}. Si data/ ya contiene todos los resúmenes actuales, '
              f'ejecuta primero:  python3 scripts/3_merge_resumenes.py --inicializar')
        sys.exit(1)
    nuevos = [r for r in todos if r not in procesados]
    if not nuevos:
        print('No hay resúmenes nuevos.')
        return
    print(f'{len(nuevos)} resúmenes nuevos')

    artists, genres, labels, concerts, instruments, standalone = {}, {}, {}, {}, {}, {}
    parse_folder(RESUMENES_FOLDER, artists, genres, labels, concerts, instruments, standalone,
                 only=set(nuevos))

    dec   = L.Decisions(L.DECISIONS)
    canon = L.Canon(dec)
    ops   = {}
    for _ln, who, sec, pat, target in dec.ops:
        ops.setdefault((nkey(who), sec), []).append((pat, target))
    deleted = {}
    if os.path.exists(DELETED_JSON):
        with open(DELETED_JSON, 'r', encoding='utf-8') as f:
            deleted = json.load(f)
    del_entities = deleted.get('entities', {})
    del_entries  = deleted.get('entries', {})

    idx   = _indice('artists')
    files = {}                                    # ruta → MdFile abierto
    cola  = lotes.cargar_cola()
    stats = defaultdict(int)

    def ficha(nombre_canon, crear=True):
        """MdFile del artista canónico (existente o nuevo en pendiente/)."""
        p = idx.get(nkey(nombre_canon))
        nuevo = p is None
        if nuevo:
            if not crear or del_entities.get(f'artist:{slug(nombre_canon)}'):
                return None, False
            p = os.path.join(PENDING_FOLDER, 'artists', slug(nombre_canon) + '.md')
            idx[nkey(nombre_canon)] = p
            stats['artistas nuevos'] += 1
        if p not in files:
            files[p] = MdFile(p, 'artist', nombre_canon)
        return files[p], nuevo

    def aplicar_ops(raw, can, sec, title):
        """Decisiones 'Artista :: sección :: Título => …' con título exacto."""
        for who in {nkey(raw), nkey(can)}:
            for pat, target in ops.get((who, sec), []):
                if title == pat:
                    return target if target is not None else False
        return title

    tocados = {}                                  # ruta → (nombre, nuevo, originales, añadidos, fuentes)

    def anotar(md, nuevo, raw, sec, title, fuentes):
        t = tocados.setdefault(md.path, [md.name, False, set(), [], set()])
        t[1] = t[1] or nuevo
        if raw and nkey(raw) != nkey(md.name):
            t[2].add(raw)
        if sec:
            t[3].append((sec, title))
        t[4].update(fuentes)

    for a in artists.values():
        can = canon.resolve(a.name)
        if can is L.DELETED:
            stats['artistas descartados por decisión'] += 1
            continue
        md, nuevo = ficha(can)
        if md is None:
            stats['artistas borrados en el editor'] += 1
            continue
        del_here = del_entries.get(f"artists/{os.path.basename(md.path)}", {})
        # entradas (álbumes, canciones, curiosidades)
        for sec in ENTRY_SECTIONS:
            for title, desc in getattr(a, sec):
                t2 = aplicar_ops(a.name, can, sec, title)
                if t2 is False:
                    stats['entradas descartadas por decisión'] += 1; continue
                dest = md
                if t2.startswith('@'):
                    dest, _n = ficha(t2[1:].strip())
                    if dest is None:
                        continue
                    t2 = title
                if t2.strip().lower() in [x.lower() for x in del_here.get(sec, [])]:
                    stats['entradas borradas en el editor'] += 1; continue
                if dest.add_entry(sec, t2, desc):
                    stats[f'{sec} añadidas'] += 1
                    anotar(dest, nuevo if dest is md else False, a.name, sec, t2, a.files)
        # listas simples
        for sec, attr in (('genres', 'genres'), ('labels', 'labels'),
                          ('concerts', 'concerts'), ('instruments', 'instruments')):
            for it in getattr(a, attr):
                it = L.strip_roles(it) if sec != 'concerts' else it
                if md.add_list(sec, it):
                    anotar(md, nuevo, a.name, None, None, a.files)
        # relaciones miembro ↔ grupo, canonizadas con las decisiones [Grupo] Miembro
        for m in a.members:
            b, mm = canon.member(a.name, m)
            if b is L.DELETED or mm is L.DELETED or nkey(b) == nkey(mm):
                continue
            mmd, mnuevo = ficha(mm)
            if mmd is None:
                continue
            if md.add_list('members', mmd.name):
                stats['relaciones añadidas'] += 1
                anotar(md, nuevo, a.name, 'members', mmd.name, a.files)
            if mmd.add_list('member of', md.name):
                anotar(mmd, mnuevo, m, 'member of', md.name, a.files)
        for bnd in a.member_of:
            b, mm = canon.member(bnd, a.name)
            if b is L.DELETED or mm is L.DELETED or nkey(b) == nkey(mm):
                continue
            bmd, bnuevo = ficha(b)
            if bmd is None:
                continue
            if md.add_list('member of', bmd.name):
                stats['relaciones añadidas'] += 1
                anotar(md, nuevo, a.name, 'member of', bmd.name, a.files)
            if bmd.add_list('members', md.name):
                anotar(bmd, bnuevo, bnd, 'members', md.name, a.files)

    # géneros, sellos, conciertos, instrumentos: curiosidades + lista ## artists
    for etype, store, subdir, attr in [('genre', genres, 'genres', 'genres'), ('label', labels, 'labels', 'labels'),
                                       ('concert', concerts, 'concerts', 'concerts'),
                                       ('instrument', instruments, 'instruments', 'instruments')]:
        eidx = _indice(subdir)
        for e in store.values():
            if not eidx.get(nkey(e.name)) and del_entities.get(f'{etype}:{slug(e.name)}'):
                continue                                  # borrado en el editor web
            p = eidx.get(nkey(e.name)) or os.path.join(PENDING_FOLDER, subdir, slug(e.name) + '.md')
            eidx[nkey(e.name)] = p
            md = files.setdefault(p, MdFile(p, etype, e.name))
            for t, d in e.curiosities:
                if md.add_entry('curiosities', t, d):
                    stats[f'curiosidades de {subdir}'] += 1
        for a in artists.values():
            can = canon.resolve(a.name)
            if can is L.DELETED:
                continue
            amd = files.get(idx.get(nkey(can)))
            for it in getattr(a, attr):
                p = eidx.get(nkey(it))
                if p and amd is not None:
                    md = files.setdefault(p, MdFile(p, etype, it))
                    md.add_list('artists', amd.name)

    # curiosidades generales
    cur_path = os.path.join(DATA_FOLDER, 'curiosities.md')
    existentes = set()
    if os.path.exists(cur_path):
        with open(cur_path, 'r', encoding='utf-8') as f:
            existentes = {m.group(1).strip().lower() for l in f if (m := ENTRY_RE.match(l.strip()))}
    nuevas_gen = [(t, d) for t, d in standalone.items() if t.lower() not in existentes]

    # cola de revisión
    for path, (nombre, nuevo, origs, anadidos, fuentes) in tocados.items():
        lotes.encolar(cola, nombre, os.path.relpath(path), nuevo,
                      sorted(origs)[0] if origs else None, anadidos, sorted(fuentes)[0] if fuentes else None)
        for o in sorted(origs)[1:]:
            lotes.encolar(cola, nombre, os.path.relpath(path), nuevo, o, [], None)

    for k in sorted(stats):
        print(f'  {k}: {stats[k]}')
    print(f'  curiosidades generales nuevas: {len(nuevas_gen)}')
    print(f'  artistas a revisar en la cola: {len(tocados)}')
    if args.dry_run:
        print('(dry-run: no se ha escrito nada)')
        return

    for md in files.values():
        md.save()
    if nuevas_gen:
        with open(cur_path, 'a', encoding='utf-8') as f:
            for t, d in nuevas_gen:
                f.write(f'**{t}** : {d}\n')
    lotes.guardar_cola(cola)
    _guardar_procesados(procesados | set(nuevos))
    print('Cola de revisión:', lotes.estadisticas())

    if not args.sin_limpieza:
        # agrupa títulos (R3), ordena y aplica el resto de decisiones sobre lo añadido
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         'limpieza', 'limpiar_artistas.py'), '--in-place'],
                           capture_output=True, text=True)
        print((r.stdout.splitlines() or [''])[-1] if r.returncode == 0 else r.stderr[-2000:])


if __name__ == '__main__':
    main()
