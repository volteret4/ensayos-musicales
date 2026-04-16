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
DROP TABLE IF EXISTS cross_references;
CREATE TABLE IF NOT EXISTS cross_references (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_artist_id INTEGER NOT NULL,
    target_artist_id INTEGER NOT NULL,
    item_type        TEXT    NOT NULL,   -- 'curiosity' | 'album' | 'song'
    item_name        TEXT    NOT NULL,
    source_file      TEXT    NOT NULL DEFAULT '',
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


def _best_sf(existing, new):
    """Return whichever source_file looks more like a YouTube URL."""
    if '|http' in (new or ''):
        return new
    return existing or new or ''


def collect_items(conn, aid_set):
    """Return list of (source_artist_id, item_type, item_name, full_text, source_file)."""
    items = []

    # Curiosities owned by an artist (one row per curiosity, already unique)
    for title, desc, ctx_id, sf in conn.execute(
        "SELECT title, description, context_id, source_file "
        "FROM curiosities WHERE context_type = 'artist'"
    ):
        if ctx_id in aid_set:
            items.append((ctx_id, 'curiosity', title, f'{title} {desc}', sf or ''))

    # Albums — may have multiple descriptions; merge text, keep best source_file
    album_map = {}
    for name, artist_id, desc, sf in conn.execute(
        'SELECT a.name, a.artist_id, d.description, d.source_file '
        'FROM albums a JOIN albums_data d ON d.album_id = a.id'
    ):
        if artist_id not in aid_set:
            continue
        key = (artist_id, name)
        if key not in album_map:
            album_map[key] = (f'{name} {desc}', sf or '')
        else:
            old_text, old_sf = album_map[key]
            album_map[key] = (old_text + ' ' + desc, _best_sf(old_sf, sf))
    for (artist_id, name), (text, sf) in album_map.items():
        items.append((artist_id, 'album', name, text, sf))

    # Songs — same dedup strategy
    song_map = {}
    for name, artist_id, desc, sf in conn.execute(
        'SELECT s.name, s.artist_id, d.description, d.source_file '
        'FROM songs s JOIN songs_data d ON d.song_id = s.id'
    ):
        if artist_id not in aid_set:
            continue
        key = (artist_id, name)
        if key not in song_map:
            song_map[key] = (f'{name} {desc}', sf or '')
        else:
            old_text, old_sf = song_map[key]
            song_map[key] = (old_text + ' ' + desc, _best_sf(old_sf, sf))
    for (artist_id, name), (text, sf) in song_map.items():
        items.append((artist_id, 'song', name, text, sf))

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
    for src_id, itype, iname, text, source_file in items:
        for tgt_id, tgt_name, pat in patterns:
            if tgt_id == src_id:
                continue
            if pat.search(text):
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO cross_references '
                        '(source_artist_id, target_artist_id, item_type, item_name, source_file) '
                        'VALUES (?,?,?,?,?)',
                        (src_id, tgt_id, itype, iname, source_file),
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
