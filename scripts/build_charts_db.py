#!/usr/bin/env python3
"""
Construye db/charts.db combinando dos fuentes:
  1. musica_local.sqlite  → charts semanales / anuales (Billboard, UK, Spain, NME…)
  2. must_hear_rym_new.db → listas de críticos (Scaruffi, Rolling Stone, Pitchfork,
                             1001 Albums, AOTY, Sputnikmusic, Grammy, Kerrang!…)
     Se excluyen colecciones de RateYourMusic, music_genre_tree e image_ocr.

Uso:
    python3 scripts/build_charts_db.py
    python3 scripts/build_charts_db.py --charts-source ~/otra/musica_local.sqlite
    python3 scripts/build_charts_db.py --lists-source  ~/otra/must_hear.db
    python3 scripts/build_charts_db.py --output ./db/charts.db
"""

import sqlite3
import re
import os
import argparse

CHARTS_SOURCE = os.path.expanduser("~/gits/pollo/music-fuzzy/db/sqlite/musica_local.sqlite")
LISTS_SOURCE  = "./db/must_hear_rym_new.db"
OUTPUT_DB     = "./db/charts.db"

# Colecciones excluidas aunque no sean rateyourmusic
EXCLUDED_SLUGS = {"music_genre_tree", "rock_and_roll"}


# ── Normalización ─────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Normaliza nombre de artista para matching consistente."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r'^(the|a|an|los|las|el|la|le|les)\s+', '', n)
    n = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s.*', '', n)
    n = re.sub(r'\s*[(&]\s.*', '', n)
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


# ── Schema ────────────────────────────────────────────────────────────────────

def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS artists (
            id        INTEGER PRIMARY KEY,
            name      TEXT NOT NULL,
            name_norm TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_norm
            ON artists(name_norm);
        CREATE INDEX IF NOT EXISTS idx_artists_name
            ON artists(name COLLATE NOCASE);

        -- Charts semanales/anuales (Billboard, UK, Spain, NME…)
        CREATE TABLE IF NOT EXISTS chart_entries (
            id        INTEGER PRIMARY KEY,
            artist_id INTEGER NOT NULL REFERENCES artists(id),
            artista   TEXT NOT NULL,
            titulo    TEXT NOT NULL,
            chart     TEXT NOT NULL,
            year      INTEGER,
            position  INTEGER,
            semanas   INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_entries_artist ON chart_entries(artist_id);
        CREATE INDEX IF NOT EXISTS idx_entries_chart  ON chart_entries(chart);
        CREATE INDEX IF NOT EXISTS idx_entries_year   ON chart_entries(year);

        -- Listas de críticos / revistas (Scaruffi, Rolling Stone, Pitchfork…)
        CREATE TABLE IF NOT EXISTS lists (
            id     INTEGER PRIMARY KEY,
            slug   TEXT NOT NULL UNIQUE,
            name   TEXT NOT NULL,
            source TEXT,
            total  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_lists_slug ON lists(slug);

        CREATE TABLE IF NOT EXISTS list_entries (
            id               INTEGER PRIMARY KEY,
            list_id          INTEGER NOT NULL REFERENCES lists(id),
            artist_id        INTEGER REFERENCES artists(id),
            artist_name      TEXT NOT NULL,
            album_name       TEXT NOT NULL,
            year             INTEGER,
            rank             INTEGER,
            scaruffi_rating  REAL,
            aoty_score       INTEGER,
            metacritic_score INTEGER,
            sputnik_rating   REAL
        );
        CREATE INDEX IF NOT EXISTS idx_lentries_artist ON list_entries(artist_id);
        CREATE INDEX IF NOT EXISTS idx_lentries_list   ON list_entries(list_id);
    """)
    conn.commit()


# ── Artistas ──────────────────────────────────────────────────────────────────

def get_or_create_artist(conn, name):
    norm = normalize(name)
    if not norm:
        return None
    cur = conn.execute("SELECT id FROM artists WHERE name_norm = ?", (norm,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO artists(name, name_norm) VALUES(?, ?)", (name, norm)
    )
    return cur.lastrowid


# ── Parte 1: charts semanales/anuales ─────────────────────────────────────────

# (tabla, chart_name|None, col_art, col_tit, col_year, col_pos, col_sem)
CHART_SOURCES = [
    ("billboard_yearend_singles", "Billboard Year-End Hot 100",
     "artista", "título",  "año", "posición",      None),
    ("billboard_hot100_topten",   "Billboard Hot 100",
     "artista", "título",  "año", "posición_pico", "semanas_chart"),
    ("billboard_country_albums",  "Billboard Hot Country Albums",
     "artista", "álbum",   "año", "posición",      "semanas_en_1"),
    ("uk_charts_singles",         "UK Singles Chart",
     "artista", "título",  "año", "posición",      None),
    ("uk_charts_bestselling",     "UK Best Selling Singles",
     "artista", "título",  "año", "posición",      None),
    ("uk_indie_charts",           "UK Indie Singles Chart",
     "artista", "single",  "año", "posicion_main_chart", "semanas_numero_uno"),
    ("uk_vinyl_charts",           None,           # nombre dinámico
     "artista", "título",  None,  None,            "semanas_numero_uno"),
    ("nme_charts",                "NME Chart",
     "artista", "single",  "año", None,            "semanas_numero_uno"),
    ("spain_charts_singles",      None,           # nombre dinámico
     "artista", "título",  "año", "posición",      None),
    ("spain_charts_albums",       "Spain Albums Chart",
     "artista", "título",  "año", "posición",      None),
    ("uk_streaming_charts",       "UK Albums Streaming Chart",
     "artista", "álbum",   "año", "posición",      "semanas_en_chart"),
    ("uk_downloads_charts",       "UK Singles Downloads Chart",
     "artista", "single",  "año", "posición",      "semanas_en_chart"),
]


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def import_chart_table(src, dst, source_def):
    table, chart_name, col_art, col_tit, col_year, col_pos, col_sem = source_def

    if not _table_exists(src, table):
        print(f"  [{table}] no existe — saltando")
        return 0
    if src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
        print(f"  [{table}] vacía — saltando")
        return 0

    real_cols = {r[1] for r in src.execute(f"PRAGMA table_info({table})").fetchall()}
    select_cols = [col_art, col_tit]
    extras = {}
    for alias, col in [("year", col_year), ("pos", col_pos), ("sem", col_sem)]:
        if col and col in real_cols:
            extras[alias] = col
            select_cols.append(col)
    if chart_name is None:
        if table == "uk_vinyl_charts"   and "chart_type" in real_cols:
            select_cols.append("chart_type")
        elif table == "spain_charts_singles" and "tipo_chart" in real_cols:
            select_cols.append("tipo_chart")

    rows    = src.execute(
        f"SELECT {', '.join(select_cols)} FROM {table} WHERE {col_art} IS NOT NULL"
    ).fetchall()
    col_idx = {c: i for i, c in enumerate(select_cols)}
    inserted = 0

    for row in rows:
        artista = row[col_idx[col_art]]
        titulo  = row[col_idx[col_tit]] or ""
        year    = row[col_idx[extras["year"]]] if "year" in extras else None
        pos     = row[col_idx[extras["pos"]]]  if "pos"  in extras else None
        sem     = row[col_idx[extras["sem"]]]  if "sem"  in extras else None

        if chart_name is None:
            if table == "uk_vinyl_charts":
                ct   = row[col_idx.get("chart_type")] if "chart_type" in col_idx else "singles"
                name = f"UK Vinyl {'Albums' if ct == 'albums' else 'Singles'} Chart"
            elif table == "spain_charts_singles":
                tc   = row[col_idx.get("tipo_chart")] if "tipo_chart" in col_idx else ""
                name = f"Spain {tc} Chart" if tc else "Spain Singles Chart"
            else:
                name = table
        else:
            name = chart_name

        if pos is not None:
            try:
                pos = int(str(pos).strip('"').strip("'"))
            except (ValueError, TypeError):
                pos = None
        if year is not None:
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = None

        aid = get_or_create_artist(dst, artista)
        if not aid:
            continue
        dst.execute(
            "INSERT INTO chart_entries(artist_id,artista,titulo,chart,year,position,semanas)"
            " VALUES(?,?,?,?,?,?,?)",
            (aid, artista, titulo, name, year, pos, sem),
        )
        inserted += 1

    return inserted


# ── Parte 2: listas de críticos ───────────────────────────────────────────────

def _infer_source(slug: str, source_type: str) -> str:
    """Devuelve una etiqueta corta para la fuente de la colección."""
    if source_type in ("musicbrainz", "sputnikmusic"):
        return source_type
    for prefix, label in [
        ("scaruffi_",      "Scaruffi"),
        ("rolling_stone_", "Rolling Stone"),
        ("pitchfork_",     "Pitchfork"),
        ("aoty_",          "AOTY"),
        ("1001_albums_",   "1001 Albums"),
        ("grammy_",        "Grammy"),
        ("juno_",          "Juno Awards"),
        ("kerrang_",       "Kerrang!"),
        ("john_peel_",     "John Peel"),
        ("resident_advisor_", "Resident Advisor"),
        ("bandcamp_",      "Bandcamp"),
    ]:
        if slug.startswith(prefix):
            return label
    return source_type or "other"


def import_lists(lists_db_path: str, dst):
    if not os.path.exists(lists_db_path):
        print(f"  [listas] {lists_db_path} no encontrada — saltando")
        return 0, 0

    src = sqlite3.connect(lists_db_path)
    src.row_factory = sqlite3.Row

    collections = src.execute("""
        SELECT id, slug, name, source_type, total_albums
        FROM collections
        WHERE (source_type IS NULL OR source_type NOT IN ('rateyourmusic', 'image_ocr'))
    """).fetchall()

    n_lists = n_entries = 0

    for col in collections:
        if col["slug"] in EXCLUDED_SLUGS:
            continue

        source = _infer_source(col["slug"], col["source_type"] or "")
        cur = dst.execute(
            "INSERT INTO lists(slug, name, source, total) VALUES(?,?,?,?)",
            (col["slug"], col["name"], source, col["total_albums"]),
        )
        list_id = cur.lastrowid
        n_lists += 1

        rows = src.execute("""
            SELECT ca.rank,
                   al.name  AS album_name,
                   al.year,
                   al.scaruffi_rating,
                   al.aoty_critic_score,
                   al.metacritic_score,
                   al.sputnik_rating,
                   ar.name  AS artist_name
            FROM   collection_albums ca
            JOIN   albums  al ON al.id = ca.album_id
            JOIN   artists ar ON ar.id = al.artist_id
            WHERE  ca.collection_id = ?
            ORDER  BY ca.rank
        """, (col["id"],)).fetchall()

        for r in rows:
            aid = get_or_create_artist(dst, r["artist_name"])
            dst.execute(
                """INSERT INTO list_entries
                   (list_id, artist_id, artist_name, album_name, year, rank,
                    scaruffi_rating, aoty_score, metacritic_score, sputnik_rating)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (list_id, aid, r["artist_name"], r["album_name"],
                 r["year"], r["rank"],
                 r["scaruffi_rating"], r["aoty_critic_score"],
                 r["metacritic_score"], r["sputnik_rating"]),
            )
            n_entries += 1

    src.close()
    return n_lists, n_entries


# ── Build principal ───────────────────────────────────────────────────────────

def build(charts_path, lists_path, output_path):
    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"Borrada DB anterior: {output_path}")

    dst = sqlite3.connect(output_path)
    create_schema(dst)

    # — Parte 1: charts —
    print(f"\n[1/2] Charts desde: {charts_path}\n")
    src = sqlite3.connect(charts_path)
    src.row_factory = sqlite3.Row
    chart_total = 0
    for source_def in CHART_SOURCES:
        n = import_chart_table(src, dst, source_def)
        if n:
            label = source_def[1] or "dinámico"
            print(f"  [{source_def[0]}] → {n:>5}  ({label})")
            chart_total += n
    src.close()
    dst.commit()

    # — Parte 2: listas —
    print(f"\n[2/2] Listas desde: {lists_path}\n")
    n_lists, list_total = import_lists(lists_path, dst)
    dst.commit()

    if n_lists:
        print(f"  {n_lists} colecciones importadas → {list_total:>6} entradas")

    # — Resumen —
    n_artists = dst.execute("SELECT COUNT(*)    FROM artists").fetchone()[0]
    n_charts  = dst.execute("SELECT COUNT(DISTINCT chart) FROM chart_entries").fetchone()[0]
    n_lcols   = dst.execute("SELECT COUNT(*)    FROM lists").fetchone()[0]

    dst.close()

    print(f"\n{'─'*52}")
    print(f"  Artistas únicos:        {n_artists:>6}")
    print(f"  Entradas de charts:     {chart_total:>6}  ({n_charts} charts distintos)")
    print(f"  Colecciones de listas:  {n_lcols:>6}")
    print(f"  Entradas de listas:     {list_total:>6}")
    print(f"\n✓ Guardado en: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Construye db/charts.db desde musica_local.sqlite + must_hear_rym_new.db"
    )
    parser.add_argument("--charts-source", default=CHARTS_SOURCE,
                        help="Ruta a musica_local.sqlite")
    parser.add_argument("--lists-source",  default=LISTS_SOURCE,
                        help="Ruta a must_hear_rym_new.db")
    parser.add_argument("--output",        default=OUTPUT_DB,
                        help="Ruta de salida (default: ./db/charts.db)")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    build(args.charts_source, args.lists_source, args.output)


if __name__ == "__main__":
    main()
