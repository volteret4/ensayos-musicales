"""
merge_resumenes.py

Reads all .md files in resumenes/ (recursive), groups entries by entity
(artist, genre, label, venue, instrument, curiosity), deduplicates by title,
and writes merged markdown files to data/.

Output structure:
  data/artists/{slug}.md       — one per artist
  data/genres/{slug}.md        — one per named genre
  data/labels/{slug}.md        — one per named label
  data/venues/{slug}.md        — one per named venue
  data/instruments/{slug}.md   — one per named instrument
  data/curiosities.md          — unattributed curiosities

Original files in resumenes/ are NOT modified.
"""

import os
import re
from collections import defaultdict

RESUMENES_FOLDER = './resumenes'
DATA_FOLDER      = './data'

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.+)')


# ── slug ─────────────────────────────────────────────────────────────────────

def slug(name):
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s.strip('-') or 'unknown'


# ── Data containers ───────────────────────────────────────────────────────────

class ArtistData:
    def __init__(self, name):
        self.name        = name
        self.members     = []   # list of bare names (ordered, dedup'd)
        self.member_of   = []   # filled in by derive_member_of()
        self.genres      = []
        self.labels      = []
        self.venues      = []
        self.instruments = []
        self.albums      = {}   # title → description (first wins)
        self.songs       = {}
        self.curiosities = {}

    def add_list(self, section, name):
        target = getattr(self, section, None)
        if target is not None and name not in target:
            target.append(name)

    def add_entry(self, section, title, desc):
        target = getattr(self, section, None)
        if target is not None and title not in target:
            target[title] = desc


class EntityData:
    """Generic container for genre / label / venue / instrument."""
    def __init__(self, name):
        self.name        = name
        self.curiosities = {}   # title → description

    def add_entry(self, title, desc):
        if title not in self.curiosities:
            self.curiosities[title] = desc


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_resumenes(folder):
    artists    = {}   # name → ArtistData
    genres     = {}
    labels     = {}
    venues     = {}
    instruments= {}
    standalone = {}   # unattributed curiosities: title → desc

    def get_artist(name):
        if name not in artists:
            artists[name] = ArtistData(name)
        return artists[name]

    def get_entity(store, name):
        if name not in store:
            store[name] = EntityData(name)
        return store[name]

    store_for = {
        'genre':      genres,
        'label':      labels,
        'venue':      venues,
        'instrument': instruments,
    }

    for root, _dirs, files in os.walk(folder):
        for filename in sorted(files):
            if not filename.endswith('.md'):
                continue
            filepath = os.path.join(root, filename)

            ctx_type    = None   # 'artist' | 'genre' | 'label' | 'venue' | 'instrument' | 'standalone'
            ctx_name    = None
            section     = None

            with open(filepath, 'r', encoding='utf-8') as fh:
                for raw in fh:
                    line = raw.rstrip('\n')
                    s    = line.strip()

                    if not s:
                        continue

                    # ── Top-level headers ──────────────────────────────────
                    # # artist - Name  /  # genre - Name  etc.
                    m = re.match(
                        r'^#\s+(artist|genre|label|venue|instrument)\s+-\s+(.+)',
                        s, re.IGNORECASE
                    )
                    if m:
                        ctx_type = m.group(1).lower()
                        ctx_name = m.group(2).strip()
                        section  = None
                        if ctx_type == 'artist':
                            get_artist(ctx_name)
                        else:
                            get_entity(store_for[ctx_type], ctx_name)
                        continue

                    # # curiosity  (bare, no name)
                    if re.match(r'^#\s+curiosity\s*$', s, re.IGNORECASE):
                        ctx_type = 'standalone'
                        ctx_name = None
                        section  = 'curiosities'
                        continue

                    # Skip any other # headers (e.g. old-format leftovers)
                    if s.startswith('#'):
                        continue

                    # ── Sub-headers ────────────────────────────────────────
                    m = re.match(r'^##\s+(.+)', s, re.IGNORECASE)
                    if m:
                        section = m.group(1).strip().lower().replace(' ', '_')
                        continue

                    if ctx_type is None or section is None:
                        continue

                    # ── Standalone curiosities ─────────────────────────────
                    if ctx_type == 'standalone':
                        me = ENTRY_RE.match(s)
                        if me:
                            t, d = me.group(1).strip(), me.group(2).strip()
                            if t not in standalone:
                                standalone[t] = d
                        continue

                    # ── Artist sections ────────────────────────────────────
                    if ctx_type == 'artist':
                        artist = get_artist(ctx_name)
                        LIST_SECTIONS = {
                            'members', 'member_of', 'genres',
                            'labels', 'venues', 'instruments',
                        }
                        if section in LIST_SECTIONS:
                            name = s.lstrip('- ').strip()
                            if name:
                                artist.add_list(section, name)
                        else:
                            me = ENTRY_RE.match(s)
                            if me:
                                artist.add_entry(
                                    section,
                                    me.group(1).strip(),
                                    me.group(2).strip(),
                                )
                        continue

                    # ── Named entity sections (genre / label / venue / instrument) ──
                    entity = get_entity(store_for[ctx_type], ctx_name)
                    if section == 'curiosities':
                        me = ENTRY_RE.match(s)
                        if me:
                            entity.add_entry(me.group(1).strip(), me.group(2).strip())

    return artists, genres, labels, venues, instruments, standalone


# ── Derive member_of ──────────────────────────────────────────────────────────

def derive_member_of(artists):
    """
    For every member listed under a band's ## members, add the band name
    to that member's member_of list.  Creates stub ArtistData if the member
    has no own section yet (is_primary will be False in the DB).
    """
    for band_name, band in list(artists.items()):
        for member_name in band.members:
            if member_name not in artists:
                artists[member_name] = ArtistData(member_name)
            member = artists[member_name]
            if band_name not in member.member_of:
                member.member_of.append(band_name)


# ── Writers ───────────────────────────────────────────────────────────────────

def _lines_list(header, items):
    if not items:
        return []
    return [f'## {header}'] + list(items) + ['']


def _lines_entries(header, entries):
    if not entries:
        return []
    return [f'## {header}'] + [f'**{t}** : {d}' for t, d in entries.items()] + ['']


def write_artist(artist, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(artist.name) + '.md')
    lines = [f'# artist - {artist.name}', '']

    lines += _lines_list('member of',   artist.member_of)
    lines += _lines_list('members',     artist.members)
    lines += _lines_list('genres',      artist.genres)
    lines += _lines_list('labels',      artist.labels)
    lines += _lines_list('venues',      artist.venues)
    lines += _lines_list('instruments', artist.instruments)
    lines += _lines_entries('albums',      artist.albums)
    lines += _lines_entries('songs',       artist.songs)
    lines += _lines_entries('curiosities', artist.curiosities)

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).rstrip() + '\n')


def write_entity(etype, entity, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, slug(entity.name) + '.md')
    lines = [f'# {etype} - {entity.name}', '']
    lines += _lines_entries('curiosities', entity.curiosities)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).rstrip() + '\n')


def write_standalone_curiosities(standalone, out_dir):
    if not standalone:
        return
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'curiosities.md')
    lines = ['# curiosity', '']
    lines += [f'**{t}** : {d}' for t, d in standalone.items()]
    lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).rstrip() + '\n')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'Leyendo {RESUMENES_FOLDER}...')
    artists, genres, labels, venues, instruments, standalone = parse_resumenes(RESUMENES_FOLDER)

    derive_member_of(artists)

    # Determine which artists have their own section (is_primary)
    # vs. those only inferred from ## members lists
    # We track this by checking if the artist was originally in the parse result
    # before derive_member_of added stubs.  The simplest proxy: any artist whose
    # ArtistData has at least one piece of non-membership data is primary.
    # The DB script will also re-derive this from the file structure.

    print(f'  {len(artists):4d} artistas')
    print(f'  {len(genres):4d} géneros')
    print(f'  {len(labels):4d} sellos')
    print(f'  {len(venues):4d} venues')
    print(f'  {len(instruments):4d} instrumentos')
    print(f'  {len(standalone):4d} curiosidades sin atribuir')

    # Write artists
    artist_dir = os.path.join(DATA_FOLDER, 'artists')
    for artist in sorted(artists.values(), key=lambda a: a.name):
        write_artist(artist, artist_dir)

    # Write named entities
    for etype, store, subdir in [
        ('genre',      genres,      'genres'),
        ('label',      labels,      'labels'),
        ('venue',      venues,      'venues'),
        ('instrument', instruments, 'instruments'),
    ]:
        out_dir = os.path.join(DATA_FOLDER, subdir)
        for entity in sorted(store.values(), key=lambda e: e.name):
            write_entity(etype, entity, out_dir)

    # Write standalone curiosities
    write_standalone_curiosities(standalone, DATA_FOLDER)

    print(f'\nEscrito en {DATA_FOLDER}/')
    print(f'  artists/      {len(artists)} archivos')
    for subdir, store in [('genres', genres), ('labels', labels),
                          ('venues', venues), ('instruments', instruments)]:
        print(f'  {subdir+"/":13s} {len(store)} archivos')
    if standalone:
        print(f'  curiosities.md ({len(standalone)} entradas)')


if __name__ == '__main__':
    main()
