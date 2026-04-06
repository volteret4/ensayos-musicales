"""
find_mentions.py

Scans all item descriptions in music_facts.db for mentions of other primary
artists.  Writes results to the cross_references table so that sqlite_to_web.py
can draw dashed edges between artists that reference each other.

Run after md_to_sqlite.py has populated the database.
"""

import re
import sqlite3

DB_PATH     = 'music_facts.db'
MIN_NAME_LEN = 5   # skip very short / generic artist names

SCHEMA = '''
CREATE TABLE IF NOT EXISTS cross_references (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_artist_id INTEGER NOT NULL,
    target_artist_id INTEGER NOT NULL,
    item_type        TEXT    NOT NULL,   -- 'curiosity' | 'album' | 'song'
    item_name        TEXT    NOT NULL,
    UNIQUE(source_artist_id, target_artist_id, item_name)
);
'''


def build_patterns(conn):
    """Return [(artist_id, name, compiled_pattern)] sorted by name length desc."""
    rows = conn.execute(
        'SELECT id, name FROM artists WHERE is_primary = 1'
    ).fetchall()
    result = []
    for aid, name in rows:
        if len(name) < MIN_NAME_LEN:
            continue
        pat = re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)
        result.append((aid, name, pat))
    # Longest names first so "Joy Division" matches before "Joy"
    result.sort(key=lambda x: -len(x[1]))
    return result


def collect_items(conn, aid_set):
    """Return list of (source_artist_id, item_type, item_name, full_text)."""
    items = []

    # Curiosities owned by an artist
    for title, desc, ctx_id in conn.execute(
        "SELECT title, description, context_id "
        "FROM curiosities WHERE context_type = 'artist'"
    ):
        if ctx_id in aid_set:
            items.append((ctx_id, 'curiosity', title, f'{title} {desc}'))

    # Albums
    for name, artist_id, desc in conn.execute(
        'SELECT a.name, a.artist_id, d.description '
        'FROM albums a JOIN albums_data d ON d.album_id = a.id'
    ):
        if artist_id in aid_set:
            items.append((artist_id, 'album', name, f'{name} {desc}'))

    # Songs
    for name, artist_id, desc in conn.execute(
        'SELECT s.name, s.artist_id, d.description '
        'FROM songs s JOIN songs_data d ON d.song_id = s.id'
    ):
        if artist_id in aid_set:
            items.append((artist_id, 'song', name, f'{name} {desc}'))

    return items


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute('DELETE FROM cross_references')
    conn.commit()

    patterns = build_patterns(conn)
    aid_set  = {aid for aid, _, _ in patterns}
    print(f'Patrones: {len(patterns)} artistas primarios (nombre ≥ {MIN_NAME_LEN} chars)')

    items = collect_items(conn, aid_set)
    print(f'Ítems a escanear: {len(items)}')

    inserted = 0
    for src_id, itype, iname, text in items:
        for tgt_id, tgt_name, pat in patterns:
            if tgt_id == src_id:
                continue
            if pat.search(text):
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO cross_references '
                        '(source_artist_id, target_artist_id, item_type, item_name) '
                        'VALUES (?,?,?,?)',
                        (src_id, tgt_id, itype, iname),
                    )
                    inserted += 1
                except Exception:
                    pass

    conn.commit()

    total = conn.execute('SELECT COUNT(*) FROM cross_references').fetchone()[0]
    pairs = conn.execute(
        'SELECT COUNT(*) FROM ('
        '  SELECT DISTINCT min(source_artist_id, target_artist_id), '
        '                  max(source_artist_id, target_artist_id) '
        '  FROM cross_references'
        ')'
    ).fetchone()[0]
    print(f'→ {total} menciones cruzadas, {pairs} pares únicos de artistas')
    conn.close()


if __name__ == '__main__':
    main()
