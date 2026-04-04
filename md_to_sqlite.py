import os
import re
import sqlite3

DB_PATH = 'music_facts.db'
RESUMENES_FOLDER = './resumenes'

# Groups: (type, artists_raw_or_None, member_raw_or_None, title, description)
# Formats:
#   __type__ @Band @@Member **Title** : desc   (member entries)
#   __type__ @Artist **Title** : desc           (standard)
#   __type__ **Title** : desc                   (no artist)
ENTRY_RE = re.compile(
    r'^__(.+?)__'
    r'(?:\s*@([^@*\n]+?))?'   # group 2: @Artist (stops at @@, *, newline)
    r'(?:\s*@@([^*\n]+?))?'   # group 3: @@Member (optional, member entries only)
    r'\s*\*\*(.+?)\*\*'       # group 4: descriptive title
    r'\s*:\s*'
    r'(.+)',                   # group 5: description
    re.IGNORECASE,
)

TYPE_CONFIG = {
    'artist':                  ('artists',      'artists_data',      'artist_id'),
    'album':                   ('albums',       'albums_data',       'album_id'),
    'song':                    ('songs',        'songs_data',        'song_id'),
    'genre':                   ('genres',       'genres_data',       'genre_id'),
    'event':                   ('events',       'events_data',       'event_id'),
    'instrument':              ('instruments',  'instruments_data',  'instrument_id'),
    'venue':                   ('venues',       'venues_data',       'venue_id'),
    'member':                  ('members',      'members_data',      'member_id'),
    'influence':               ('influences',   'influences_data',   'influence_id'),
    'curiosity':               ('curiosities',  'curiosities_data',  'curiosity_id'),
    # legacy alias
    'general music curiosity': ('curiosities',  'curiosities_data',  'curiosity_id'),
}


def table_config(type_name):
    if type_name in TYPE_CONFIG:
        return TYPE_CONFIG[type_name]
    slug = re.sub(r'\s+', '_', type_name)
    return (slug + 's', slug + 's_data', slug + '_id')


def ensure_data_table(c, type_name):
    obj_table, data_table, fk = table_config(type_name)
    c.execute(f'''
        CREATE TABLE IF NOT EXISTS {obj_table} (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    c.execute(f'''
        CREATE TABLE IF NOT EXISTS {data_table} (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            {fk}          INTEGER NOT NULL REFERENCES {obj_table}(id),
            description   TEXT NOT NULL,
            source_folder TEXT NOT NULL DEFAULT '',
            source_file   TEXT NOT NULL,
            UNIQUE ({fk}, description, source_file)
        )
    ''')
    # Migration: add source_folder if table existed without it
    existing_cols = {row[1] for row in c.execute(f'PRAGMA table_info({data_table})')}
    if 'source_folder' not in existing_cols:
        c.execute(f"ALTER TABLE {data_table} ADD COLUMN source_folder TEXT NOT NULL DEFAULT ''")


def ensure_meta_tables(c):
    c.execute('''
        CREATE TABLE IF NOT EXISTS source_artists (
            source_file TEXT NOT NULL,
            artist_id   INTEGER NOT NULL REFERENCES artists(id),
            PRIMARY KEY (source_file, artist_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS artist_relations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id         INTEGER NOT NULL REFERENCES artists(id),
            related_artist_id INTEGER NOT NULL REFERENCES artists(id),
            context           TEXT NOT NULL,
            source_file       TEXT NOT NULL,
            UNIQUE (artist_id, related_artist_id, source_file)
        )
    ''')
    # Direct junction: _data row → artist(s) declared with @Artist in the md file
    c.execute('''
        CREATE TABLE IF NOT EXISTS entry_artists (
            data_table  TEXT    NOT NULL,
            data_id     INTEGER NOT NULL,
            artist_id   INTEGER NOT NULL REFERENCES artists(id),
            PRIMARY KEY (data_table, data_id, artist_id)
        )
    ''')
    # member_data row → artist entry for the @@Member person
    c.execute('''
        CREATE TABLE IF NOT EXISTS member_artist_links (
            members_data_id INTEGER NOT NULL,
            artist_id       INTEGER NOT NULL REFERENCES artists(id),
            PRIMARY KEY (members_data_id, artist_id)
        )
    ''')


def collect_entries():
    entries = []
    for root, _dirs, files in os.walk(RESUMENES_FOLDER):
        for filename in sorted(files):
            if not filename.endswith('.md'):
                continue
            filepath = os.path.join(root, filename)
            rel = os.path.relpath(filepath, RESUMENES_FOLDER)
            folder = os.path.dirname(rel) or '.'
            with open(filepath, 'r', encoding='utf-8') as fh:
                for line in fh:
                    m = ENTRY_RE.match(line.strip())
                    if m:
                        entries.append((
                            m.group(1).strip().lower(),                    # type_name
                            m.group(4).strip(),                            # title
                            m.group(5).strip(),                            # description
                            m.group(2).strip() if m.group(2) else None,    # artists_raw
                            m.group(3).strip() if m.group(3) else None,    # member_raw
                            folder,
                            rel,
                        ))
    return entries


def build_db():
    entries = collect_entries()
    if not entries:
        print(f"No se encontraron entradas en {RESUMENES_FOLDER}")
        return

    known_types = {e[0] for e in entries}
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    c = conn.cursor()

    for type_name in known_types:
        ensure_data_table(c, type_name)
    ensure_meta_tables(c)
    # Migration: add member_name column to members_data for @@Member links
    if 'member' in known_types:
        existing_cols = {row[1] for row in c.execute('PRAGMA table_info(members_data)')}
        if 'member_name' not in existing_cols:
            c.execute("ALTER TABLE members_data ADD COLUMN member_name TEXT")
    conn.commit()

    # ── Insert entries ─────────────────────────────────────────────────────
    added, skipped = {}, {}
    for type_name, title, desc, artists_raw, member_raw, folder, source in entries:
        obj_table, data_table, fk = table_config(type_name)
        c.execute(f'INSERT OR IGNORE INTO {obj_table} (name) VALUES (?)', (title,))
        (obj_id,) = c.execute(f'SELECT id FROM {obj_table} WHERE name = ?', (title,)).fetchone()
        before = conn.total_changes
        if type_name == 'member':
            c.execute(
                f'INSERT OR IGNORE INTO {data_table} ({fk}, description, source_folder, source_file, member_name) VALUES (?,?,?,?,?)',
                (obj_id, desc, folder, source, member_raw),
            )
        else:
            c.execute(
                f'INSERT OR IGNORE INTO {data_table} ({fk}, description, source_folder, source_file) VALUES (?,?,?,?)',
                (obj_id, desc, folder, source),
            )
        if conn.total_changes > before:
            added[type_name] = added.get(type_name, 0) + 1
            data_id = c.lastrowid
            # Store direct artist links from @Artist field
            if artists_raw and type_name != 'artist':
                for artist_name in [a.strip() for a in artists_raw.split(',') if a.strip()]:
                    c.execute('INSERT OR IGNORE INTO artists (name) VALUES (?)', (artist_name,))
                    (aid,) = c.execute('SELECT id FROM artists WHERE name = ?', (artist_name,)).fetchone()
                    c.execute(
                        'INSERT OR IGNORE INTO entry_artists (data_table, data_id, artist_id) VALUES (?,?,?)',
                        (data_table, data_id, aid),
                    )
            # Store @@Member → artist link
            if member_raw and type_name == 'member':
                for mname in [a.strip() for a in member_raw.split(',') if a.strip()]:
                    c.execute('INSERT OR IGNORE INTO artists (name) VALUES (?)', (mname,))
                    (m_aid,) = c.execute('SELECT id FROM artists WHERE name = ?', (mname,)).fetchone()
                    c.execute(
                        'INSERT OR IGNORE INTO member_artist_links (members_data_id, artist_id) VALUES (?,?)',
                        (data_id, m_aid),
                    )
        else:
            skipped[type_name] = skipped.get(type_name, 0) + 1
    conn.commit()

    # ── source_artists: which artists appear in each source file ───────────
    c.execute('DELETE FROM source_artists')
    c.execute('''
        INSERT OR IGNORE INTO source_artists (source_file, artist_id)
        SELECT DISTINCT source_file, artist_id FROM artists_data
    ''')
    conn.commit()

    # ── artist_relations: scan non-artist descriptions for artist mentions ─
    c.execute('DELETE FROM artist_relations')

    # Sort by name length desc so "Red Hot Chili Peppers" is matched before "Red Hot"
    artists = sorted(
        c.execute('SELECT id, name FROM artists').fetchall(),
        key=lambda r: len(r[1]), reverse=True,
    )
    non_artist_data_tables = [
        r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name LIKE '%_data' AND name != 'artists_data'"
        )
    ]
    rel_count = 0
    for dt in non_artist_data_tables:
        rows = c.execute(f'SELECT id, description, source_file FROM {dt}').fetchall()
        for _, desc, source_file in rows:
            owner_ids = {r[0] for r in c.execute(
                'SELECT artist_id FROM source_artists WHERE source_file = ?', (source_file,)
            )}
            if not owner_ids:
                continue
            desc_lower = desc.lower()
            for artist_id, artist_name in artists:
                if artist_id in owner_ids:
                    continue
                if artist_name.lower() in desc_lower:
                    for owner_id in owner_ids:
                        c.execute('''
                            INSERT OR IGNORE INTO artist_relations
                            (artist_id, related_artist_id, context, source_file)
                            VALUES (?,?,?,?)
                        ''', (owner_id, artist_id, desc[:300], source_file))
                        rel_count += 1
    conn.commit()
    mal_count = conn.execute('SELECT COUNT(*) FROM member_artist_links').fetchone()[0]
    conn.close()

    print(f'\nBase de datos → {DB_PATH}')
    for t in sorted(known_types):
        _, dt, _ = table_config(t)
        a, s = added.get(t, 0), skipped.get(t, 0)
        print(f'  {dt:30s}  +{a:3d} nuevos  {s:3d} ya existían')
    print(f'  artist_relations               +{rel_count:3d} relaciones detectadas')
    print(f'  member_artist_links            +{mal_count:3d} vínculos miembro→artista')


if __name__ == '__main__':
    build_db()
