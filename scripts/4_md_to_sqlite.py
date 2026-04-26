"""
md_to_sqlite.py

Reads all .md files from data/ (produced by merge_resumenes.py) and builds
music_facts.db with a fully normalised schema.

Schema overview:
  artists, genres, labels, concerts, instruments        — entity tables
  band_members, artist_genres, artist_labels,
  artist_concerts, artist_instruments                   — junction tables
  albums  + albums_data                                 — per-artist albums
  songs   + songs_data                                  — per-artist songs
  curiosities                                           — facts with context_type / context_id
"""

import os
import re
import sqlite3

DB_PATH     = 'db/music_facts.db'
DATA_FOLDER = os.environ.get('MUSIC_DATA_FOLDER', './resumenes')

ENTRY_RE = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.+)')


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = '''
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS artists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    is_primary INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS genres (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS labels (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS concerts (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS instruments (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS band_members (
    band_id   INTEGER NOT NULL REFERENCES artists(id),
    member_id INTEGER NOT NULL REFERENCES artists(id),
    PRIMARY KEY (band_id, member_id)
);
CREATE TABLE IF NOT EXISTS artist_genres (
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    genre_id  INTEGER NOT NULL REFERENCES genres(id),
    PRIMARY KEY (artist_id, genre_id)
);
CREATE TABLE IF NOT EXISTS artist_labels (
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    label_id  INTEGER NOT NULL REFERENCES labels(id),
    PRIMARY KEY (artist_id, label_id)
);
CREATE TABLE IF NOT EXISTS artist_concerts (
    artist_id  INTEGER NOT NULL REFERENCES artists(id),
    concert_id INTEGER NOT NULL REFERENCES concerts(id),
    PRIMARY KEY (artist_id, concert_id)
);
CREATE TABLE IF NOT EXISTS artist_instruments (
    artist_id     INTEGER NOT NULL REFERENCES artists(id),
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    PRIMARY KEY (artist_id, instrument_id)
);

CREATE TABLE IF NOT EXISTS albums (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    UNIQUE (name, artist_id)
);
CREATE TABLE IF NOT EXISTS albums_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    album_id    INTEGER NOT NULL REFERENCES albums(id),
    description TEXT    NOT NULL,
    source_file TEXT    NOT NULL DEFAULT '',
    UNIQUE (album_id, description, source_file)
);

CREATE TABLE IF NOT EXISTS songs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id),
    UNIQUE (name, artist_id)
);
CREATE TABLE IF NOT EXISTS songs_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id     INTEGER NOT NULL REFERENCES songs(id),
    description TEXT    NOT NULL,
    source_file TEXT    NOT NULL DEFAULT '',
    UNIQUE (song_id, description, source_file)
);

CREATE TABLE IF NOT EXISTS curiosities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL,
    context_type TEXT    NOT NULL DEFAULT 'general',
    context_id   INTEGER NOT NULL DEFAULT 0,
    source_file  TEXT    NOT NULL DEFAULT '',
    UNIQUE (title, context_type, context_id, source_file)
);
'''


# ── Helpers ───────────────────────────────────────────────────────────────────

def split_source(raw, fallback):
    """Split embedded ' ← podcast | url' from description.
    Returns (clean_description, source_file_str).
    source_file_str format: 'podcast_name|url' or fallback path if no source."""
    if ' ← ' in raw:
        desc_part, src_part = raw.split(' ← ', 1)
        fields = [x.strip() for x in src_part.split(' | ', 1)]
        name = fields[0]
        url  = fields[1] if len(fields) > 1 else ''
        sf   = f'{name}|{url}' if url else (name if name else fallback)
        return desc_part.strip(), sf
    return raw.strip(), fallback


def get_or_insert(c, table, name):
    c.execute(f'INSERT OR IGNORE INTO {table} (name) VALUES (?)', (name,))
    return c.execute(f'SELECT id FROM {table} WHERE name = ?', (name,)).fetchone()[0]


def ensure_artist(c, name, is_primary=True):
    """Insert artist if absent; upgrade to primary if flag is set."""
    c.execute(
        'INSERT OR IGNORE INTO artists (name, is_primary) VALUES (?, ?)',
        (name, 1 if is_primary else 0),
    )
    if is_primary:
        c.execute('UPDATE artists SET is_primary = 1 WHERE name = ?', (name,))
    return c.execute('SELECT id FROM artists WHERE name = ?', (name,)).fetchone()[0]


# ── File parser ───────────────────────────────────────────────────────────────

# Section names that contain bare-name lists (not **Title** : desc entries)
LIST_SECTIONS = {'members', 'member_of', 'genres', 'labels', 'concerts', 'instruments'}


def parse_file(filepath, conn):
    c   = conn.cursor()
    rel = os.path.relpath(filepath, DATA_FOLDER)

    ctx_type = None   # 'artist' | 'genre' | 'label' | 'venue' | 'instrument' | 'standalone'
    ctx_id   = None
    section  = None

    with open(filepath, 'r', encoding='utf-8') as fh:
        for raw in fh:
            s = raw.strip()
            if not s:
                continue

            # ── Top-level header: # artist - Name  /  # genre - Name  etc. ──
            m = re.match(
                r'^#\s+(artist|genre|label|concert|instrument)\s+-\s+(.+)',
                s, re.IGNORECASE,
            )
            if m:
                ctx_type = m.group(1).lower()
                name     = m.group(2).strip()
                section  = None
                if ctx_type == 'artist':
                    ctx_id = ensure_artist(c, name, is_primary=True)
                else:
                    table  = ctx_type + 's'
                    ctx_id = get_or_insert(c, table, name)
                continue

            # ── Standalone curiosity block: # curiosity ────────────────────
            if re.match(r'^#\s+curiosity\s*$', s, re.IGNORECASE):
                ctx_type = 'standalone'
                ctx_id   = None
                section  = 'curiosities'
                continue

            # ── Sub-header: ## section ─────────────────────────────────────
            m = re.match(r'^##\s+(.+)', s, re.IGNORECASE)
            if m:
                section = m.group(1).strip().lower().replace(' ', '_')
                continue

            # Skip any other # header lines
            if s.startswith('#'):
                continue

            if ctx_type is None or section is None:
                continue

            # ── Standalone curiosities ─────────────────────────────────────
            if ctx_type == 'standalone':
                me = ENTRY_RE.match(s)
                if me:
                    desc, sf = split_source(me.group(2).strip(), rel)
                    c.execute(
                        'INSERT OR IGNORE INTO curiosities '
                        '(title, description, context_type, context_id, source_file) '
                        'VALUES (?,?,?,?,?)',
                        (me.group(1).strip(), desc, 'general', 0, sf),
                    )
                continue

            # ── Artist sections ────────────────────────────────────────────
            if ctx_type == 'artist':
                if section in LIST_SECTIONS:
                    name = s.lstrip('- ').strip()
                    if not name:
                        continue

                    if section == 'members':
                        mid = ensure_artist(c, name, is_primary=False)
                        c.execute(
                            'INSERT OR IGNORE INTO band_members (band_id, member_id) VALUES (?,?)',
                            (ctx_id, mid),
                        )

                    elif section == 'member_of':
                        band_id = ensure_artist(c, name, is_primary=True)
                        c.execute(
                            'INSERT OR IGNORE INTO band_members (band_id, member_id) VALUES (?,?)',
                            (band_id, ctx_id),
                        )

                    elif section == 'genres':
                        gid = get_or_insert(c, 'genres', name)
                        c.execute(
                            'INSERT OR IGNORE INTO artist_genres (artist_id, genre_id) VALUES (?,?)',
                            (ctx_id, gid),
                        )

                    elif section == 'labels':
                        lid = get_or_insert(c, 'labels', name)
                        c.execute(
                            'INSERT OR IGNORE INTO artist_labels (artist_id, label_id) VALUES (?,?)',
                            (ctx_id, lid),
                        )

                    elif section == 'concerts':
                        cid = get_or_insert(c, 'concerts', name)
                        c.execute(
                            'INSERT OR IGNORE INTO artist_concerts (artist_id, concert_id) VALUES (?,?)',
                            (ctx_id, cid),
                        )

                    elif section == 'instruments':
                        iid = get_or_insert(c, 'instruments', name)
                        c.execute(
                            'INSERT OR IGNORE INTO artist_instruments (artist_id, instrument_id) VALUES (?,?)',
                            (ctx_id, iid),
                        )

                else:
                    me = ENTRY_RE.match(s)
                    if not me:
                        continue
                    title        = me.group(1).strip()
                    desc, sf     = split_source(me.group(2).strip(), rel)

                    if section == 'albums':
                        c.execute(
                            'INSERT OR IGNORE INTO albums (name, artist_id) VALUES (?,?)',
                            (title, ctx_id),
                        )
                        album_id = c.execute(
                            'SELECT id FROM albums WHERE name=? AND artist_id=?',
                            (title, ctx_id),
                        ).fetchone()[0]
                        c.execute(
                            'INSERT OR IGNORE INTO albums_data (album_id, description, source_file) VALUES (?,?,?)',
                            (album_id, desc, sf),
                        )

                    elif section == 'songs':
                        c.execute(
                            'INSERT OR IGNORE INTO songs (name, artist_id) VALUES (?,?)',
                            (title, ctx_id),
                        )
                        song_id = c.execute(
                            'SELECT id FROM songs WHERE name=? AND artist_id=?',
                            (title, ctx_id),
                        ).fetchone()[0]
                        c.execute(
                            'INSERT OR IGNORE INTO songs_data (song_id, description, source_file) VALUES (?,?,?)',
                            (song_id, desc, sf),
                        )

                    elif section == 'curiosities':
                        c.execute(
                            'INSERT OR IGNORE INTO curiosities '
                            '(title, description, context_type, context_id, source_file) '
                            'VALUES (?,?,?,?,?)',
                            (title, desc, 'artist', ctx_id, sf),
                        )
                continue

            # ── Named entity sections (genre / label / venue / instrument) ──
            if section == 'curiosities':
                me = ENTRY_RE.match(s)
                if me:
                    desc, sf = split_source(me.group(2).strip(), rel)
                    c.execute(
                        'INSERT OR IGNORE INTO curiosities '
                        '(title, description, context_type, context_id, source_file) '
                        'VALUES (?,?,?,?,?)',
                        (me.group(1).strip(), desc, ctx_type, ctx_id, sf),
                    )

    conn.commit()


# ── Main ──────────────────────────────────────────────────────────────────────

def build_db():
    if not os.path.isdir(DATA_FOLDER):
        print(f'No se encuentra {DATA_FOLDER}. Ejecuta primero merge_resumenes.py')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()

    file_count = 0
    for root, dirs, files in os.walk(DATA_FOLDER):
        dirs.sort()
        for filename in sorted(files):
            if filename.endswith('.md'):
                parse_file(os.path.join(root, filename), conn)
                file_count += 1

    c = conn.cursor()
    print(f'\nBase de datos → {DB_PATH}  ({file_count} archivos leídos)\n')
    rows = [
        ('artists',             'SELECT COUNT(*) FROM artists'),
        ('  primary',           'SELECT COUNT(*) FROM artists WHERE is_primary=1'),
        ('  member-only',       'SELECT COUNT(*) FROM artists WHERE is_primary=0'),
        ('genres',              'SELECT COUNT(*) FROM genres'),
        ('labels',              'SELECT COUNT(*) FROM labels'),
        ('concerts',            'SELECT COUNT(*) FROM concerts'),
        ('instruments',         'SELECT COUNT(*) FROM instruments'),
        ('band_members',        'SELECT COUNT(*) FROM band_members'),
        ('artist_genres',       'SELECT COUNT(*) FROM artist_genres'),
        ('artist_labels',       'SELECT COUNT(*) FROM artist_labels'),
        ('artist_concerts',     'SELECT COUNT(*) FROM artist_concerts'),
        ('artist_instruments',  'SELECT COUNT(*) FROM artist_instruments'),
        ('albums',              'SELECT COUNT(*) FROM albums'),
        ('albums_data',         'SELECT COUNT(*) FROM albums_data'),
        ('songs',               'SELECT COUNT(*) FROM songs'),
        ('songs_data',          'SELECT COUNT(*) FROM songs_data'),
        ('curiosities',         'SELECT COUNT(*) FROM curiosities'),
        ('  artist',            "SELECT COUNT(*) FROM curiosities WHERE context_type='artist'"),
        ('  genre',             "SELECT COUNT(*) FROM curiosities WHERE context_type='genre'"),
        ('  label',             "SELECT COUNT(*) FROM curiosities WHERE context_type='label'"),
        ('  concert',           "SELECT COUNT(*) FROM curiosities WHERE context_type='concert'"),
        ('  instrument',        "SELECT COUNT(*) FROM curiosities WHERE context_type='instrument'"),
        ('  general',           "SELECT COUNT(*) FROM curiosities WHERE context_type='general'"),
    ]
    for label, query in rows:
        n = c.execute(query).fetchone()[0]
        print(f'  {label:<22} {n:6d}')

    conn.close()


if __name__ == '__main__':
    build_db()
