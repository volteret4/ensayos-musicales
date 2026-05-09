#!/usr/bin/env python3
"""
Enriquece los .md de resumenes/ con secciones ## awards y ## charts.

Premios:  Wikidata SPARQL  (siempre online)
Charts:   db/charts.db     (local, construida con build_charts_db.py)
          → fallback a Wikidata si la DB local no existe

Uso:
    python3 scripts/3_awards_charts.py
    python3 scripts/3_awards_charts.py --file resumenes/.../archivo.md
    python3 scripts/3_awards_charts.py --force       # sobreescribe secciones existentes
    python3 scripts/3_awards_charts.py --dry-run     # no modifica archivos
    python3 scripts/3_awards_charts.py --no-charts   # solo premios
    python3 scripts/3_awards_charts.py --no-awards   # solo charts
"""

import os
import re
import time
import sqlite3
import argparse
import requests

RESUMENES_FOLDER = './resumenes'
CHARTS_DB        = './db/charts.db'
SPARQL_URL       = "https://query.wikidata.org/sparql"
SEARCH_URL       = "https://www.wikidata.org/w/api.php"
HEADERS          = {"User-Agent": "EnsayosMusicales/1.0 (ensayos@musicales.org)"}

# Wikidata chart properties — usadas solo si no existe charts.db
CHART_PROPS = {
    "P2219": "US Billboard Hot 100",
    "P2206": "US Billboard 200",
    "P2223": "UK Singles Chart",
    "P2533": "UK Albums Chart",
    "P4892": "US Hot Country Songs",
    "P2222": "US Hot R&B Songs",
    "P2225": "UK Indie Chart",
}

_last_request = 0.0


# ── Utilidades ────────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Normaliza nombre de artista para matching (mismo algoritmo que build_charts_db.py)."""
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r'^(the|a|an|los|las|el|la|le|les)\s+', '', n)
    n = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s.*', '', n)
    n = re.sub(r'\s*[(&]\s.*', '', n)
    n = re.sub(r"[^\w\s]", "", n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def _get(url, params):
    global _last_request
    elapsed = time.time() - _last_request
    if elapsed < 1.2:
        time.sleep(1.2 - elapsed)
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            _last_request = time.time()
            return r.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(3)
    return {}


def sparql(query):
    data = _get(SPARQL_URL, {"query": query, "format": "json"})
    return data.get("results", {}).get("bindings", [])


# ── Wikidata: búsqueda de QID ─────────────────────────────────────────────────

def search_qid(name):
    data = _get(SEARCH_URL, {
        "action": "wbsearchentities",
        "format": "json",
        "language": "en",
        "search": name,
        "type": "item",
        "limit": 8,
    })
    music_kw = {
        "band", "singer", "musician", "group", "rapper", "duo", "rock", "pop",
        "jazz", "composer", "songwriter", "punk", "metal", "hip", "electronic",
        "dj", "producer", "artist", "indie", "soul", "blues", "country",
    }
    for result in data.get("search", []):
        if any(kw in result.get("description", "").lower() for kw in music_kw):
            return result["id"]
    results = data.get("search", [])
    return results[0]["id"] if results else None


# ── Premios (Wikidata) ────────────────────────────────────────────────────────

def get_awards(qid):
    query = f"""
SELECT DISTINCT ?awardType ?awardLabel ?year ?workLabel WHERE {{
  {{
    wd:{qid} p:P166 ?stmt .
    ?stmt ps:P166 ?award .
    BIND("won" AS ?awardType)
    OPTIONAL {{ ?stmt pq:P585 ?date . BIND(YEAR(?date) AS ?year) }}
    OPTIONAL {{ ?stmt pq:P1686 ?work . }}
  }} UNION {{
    wd:{qid} p:P1411 ?stmt .
    ?stmt ps:P1411 ?award .
    BIND("nominated" AS ?awardType)
    OPTIONAL {{ ?stmt pq:P585 ?date . BIND(YEAR(?date) AS ?year) }}
    OPTIONAL {{ ?stmt pq:P1686 ?work . }}
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
ORDER BY ?year ?awardType
"""
    rows = sparql(query)
    awards, seen = [], set()
    for row in rows:
        label = row.get("awardLabel", {}).get("value", "")
        if not label or re.match(r'^Q\d+$', label):
            continue
        atype = row.get("awardType", {}).get("value", "")
        year  = row.get("year",      {}).get("value", "")
        work  = row.get("workLabel", {}).get("value", "")
        if re.match(r'^Q\d+$', work):
            work = ""
        key = (label, year, work, atype)
        if key not in seen:
            seen.add(key)
            awards.append({"type": atype, "award": label, "year": year, "work": work})
    return awards


# ── Charts: DB local ──────────────────────────────────────────────────────────

def _find_artist_id(conn, artist_name):
    """Busca artist_id en charts.db con fallback a matching parcial."""
    norm = normalize(artist_name)
    if not norm:
        return None
    row = conn.execute(
        "SELECT id FROM artists WHERE name_norm = ?", (norm,)
    ).fetchone()
    if row:
        return row["id"]
    # fallback: el candidato normalizado más cercano en longitud
    candidates = conn.execute(
        "SELECT id, name_norm FROM artists "
        "WHERE name_norm LIKE ? OR ? LIKE '%' || name_norm || '%'",
        (f"%{norm}%", norm),
    ).fetchall()
    if candidates:
        best = min(candidates, key=lambda r: abs(len(r["name_norm"]) - len(norm)))
        return best["id"]
    return None


def query_local_charts(artist_name, db_path):
    """Devuelve entradas de chart_entries para el artista."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    aid = _find_artist_id(conn, artist_name)
    if not aid:
        conn.close()
        return []
    entries = conn.execute(
        """SELECT titulo, chart, year, position, semanas
           FROM chart_entries WHERE artist_id = ?
           ORDER BY chart, year, position""",
        (aid,),
    ).fetchall()
    conn.close()
    return [dict(e) for e in entries]


def query_local_lists(artist_name, db_path):
    """Devuelve entradas de list_entries para el artista."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    aid = _find_artist_id(conn, artist_name)
    if not aid:
        conn.close()
        return []
    entries = conn.execute(
        """SELECT le.album_name, le.year, le.rank,
                  le.scaruffi_rating, le.aoty_score,
                  le.metacritic_score, le.sputnik_rating,
                  li.name AS list_name, li.source
           FROM list_entries le
           JOIN lists li ON li.id = le.list_id
           WHERE le.artist_id = ?
           ORDER BY li.source, li.name, le.rank""",
        (aid,),
    ).fetchall()
    conn.close()
    return [dict(e) for e in entries]


# ── Charts: Wikidata fallback ─────────────────────────────────────────────────

def get_chart_peaks_wikidata(qid):
    props_str = " ".join(f"wdt:{p}" for p in CHART_PROPS)
    query = f"""
SELECT ?titleLabel ?chartProp ?peak WHERE {{
  ?item wdt:P175 wd:{qid} .
  VALUES ?chartProp {{ {props_str} }}
  ?item ?chartProp ?peak .
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en" .
    ?item rdfs:label ?titleLabel .
  }}
}}
ORDER BY ?peak
LIMIT 80
"""
    rows = sparql(query)
    charts, seen = [], set()
    for row in rows:
        title     = row.get("titleLabel", {}).get("value", "")
        chart_uri = row.get("chartProp",  {}).get("value", "")
        peak      = row.get("peak",       {}).get("value", "")
        if not title or re.match(r'^Q\d+$', title) or not peak:
            continue
        prop_id    = chart_uri.split("/")[-1]
        chart_name = CHART_PROPS.get(prop_id, prop_id)
        key = (title.lower(), chart_name)
        if key not in seen:
            seen.add(key)
            charts.append({"titulo": title, "chart": chart_name, "position": peak,
                           "year": None, "semanas": None})
    charts.sort(key=lambda x: int(x["position"]) if str(x["position"]).isdigit() else 999)
    return charts


# ── Formateo markdown ─────────────────────────────────────────────────────────

def format_award(a):
    title = a["award"]
    if a["year"]:
        title += f" ({a['year']})"
    if a["work"]:
        title += f" — {a['work']}"
    status = "Won" if a["type"] == "won" else "Nominated"
    return f"**{title}** : {status}."


def format_chart_entry(e):
    titulo   = e.get("titulo") or e.get("title", "")
    chart    = e["chart"]
    position = e.get("position")
    year     = e.get("year")
    semanas  = e.get("semanas")

    parts = []
    if position:
        parts.append(f"#{position}")
    if year:
        parts.append(str(year))
    if semanas:
        parts.append(f"{semanas} semanas")

    detail = ", ".join(parts) if parts else "entrada"
    return f"**\"{titulo}\" — {chart}** : {detail}."


def format_list_entry(e):
    album     = e["album_name"]
    year      = e.get("year")
    list_name = e["list_name"]
    rank      = e.get("rank")

    # Score: prioridad scaruffi > aoty > metacritic > sputnik
    score_str = ""
    if e.get("scaruffi_rating"):
        score_str = f", {e['scaruffi_rating']}/10 Scaruffi"
    elif e.get("aoty_score"):
        score_str = f", {e['aoty_score']} AOTY"
    elif e.get("metacritic_score"):
        score_str = f", {e['metacritic_score']} Metacritic"
    elif e.get("sputnik_rating"):
        score_str = f", {e['sputnik_rating']} Sputnik"

    year_str = f" ({year})" if year else ""
    rank_str = f"#{rank}" if rank else "listed"
    return f"**\"{album}\"{year_str} — {list_name}** : {rank_str}{score_str}."


# ── Reconstrucción del markdown ───────────────────────────────────────────────

def strip_subsection(block_lines, name):
    result, skip = [], False
    for line in block_lines:
        if re.match(rf'^## {name}\s*$', line):
            skip = True
            continue
        if skip and re.match(r'^## ', line):
            skip = False
        if not skip:
            result.append(line)
    return result


def rebuild_content(content, enrichments, force):
    lines  = content.split('\n')
    output = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = re.match(r'^# artist - (.+)$', line)
        if m:
            artist_name = m.group(1).strip()
            output.append(line)
            i += 1

            block = []
            while i < len(lines) and not re.match(r'^# ', lines[i]):
                block.append(lines[i])
                i += 1

            has_awards = any(re.match(r'^## awards\s*$', l) for l in block)
            has_charts = any(re.match(r'^## charts\s*$', l) for l in block)
            has_lists  = any(re.match(r'^## lists\s*$',  l) for l in block)

            if force:
                block      = strip_subsection(block, "awards")
                block      = strip_subsection(block, "charts")
                block      = strip_subsection(block, "lists")
                has_awards = has_charts = has_lists = False

            output.extend(block)

            data   = enrichments.get(artist_name, {})
            awards = data.get("awards", [])
            charts = data.get("charts", [])
            lists  = data.get("lists",  [])

            if awards and not has_awards:
                output.append('')
                output.append('## awards')
                for a in awards:
                    output.append(format_award(a))

            if charts and not has_charts:
                output.append('')
                output.append('## charts')
                for c in charts:
                    output.append(format_chart_entry(c))

            if lists and not has_lists:
                output.append('')
                output.append('## lists')
                for e in lists:
                    output.append(format_list_entry(e))
        else:
            output.append(line)
            i += 1

    return '\n'.join(output)


# ── Procesado de archivo ──────────────────────────────────────────────────────

def process_file(filepath, force, dry_run, no_awards, no_charts, charts_db):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    artists = re.findall(r'^# artist - (.+)$', content, re.MULTILINE)
    if not artists:
        return

    already_awards = '## awards' in content
    already_charts = '## charts' in content
    already_lists  = '## lists'  in content
    needs_awards   = not no_awards and (force or not already_awards)
    needs_charts   = not no_charts and (force or not already_charts)
    needs_lists    = not no_charts and (force or not already_lists)

    if not needs_awards and not needs_charts and not needs_lists:
        print(f"--- Saltando (ya enriquecido): {os.path.basename(filepath)} ---")
        return

    use_local_db   = charts_db and os.path.exists(charts_db)
    charts_source  = f"local DB" if use_local_db else "Wikidata"

    print(f"\n=== {os.path.basename(filepath)} ===")
    print(f"Artistas: {', '.join(artists)}"
          f"  |  charts → {charts_source}")

    enrichments = {}
    for artist in artists:
        print(f"  {artist}...", end=' ', flush=True)
        try:
            awards = []
            charts = []
            lists  = []

            # Premios: siempre Wikidata
            if needs_awards:
                qid = search_qid(artist)
                if qid:
                    awards = get_awards(qid)
                    if needs_charts and not use_local_db:
                        charts = get_chart_peaks_wikidata(qid)
                    print(f"({qid})", end=' ', flush=True)
                else:
                    print("(QID no encontrado)", end=' ', flush=True)

            # Charts y listas: DB local tiene prioridad
            if use_local_db:
                if needs_charts:
                    charts = query_local_charts(artist, charts_db)
                if needs_lists:
                    lists = query_local_lists(artist, charts_db)

            print(f"→ {len(awards)} premios, {len(charts)} charts, {len(lists)} listas")
            if awards or charts or lists:
                enrichments[artist] = {"awards": awards, "charts": charts, "lists": lists}

        except Exception as e:
            print(f"error: {e}")

    if not enrichments:
        return

    new_content = rebuild_content(content, enrichments, force)

    if not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  ✓ Guardado")
    else:
        print("  (dry-run, no se escribe)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enriquece resumenes con ## awards y ## charts"
    )
    parser.add_argument('--folder',     default=RESUMENES_FOLDER)
    parser.add_argument('--file',       help='Procesar un único .md')
    parser.add_argument('--charts-db',  default=CHARTS_DB,
                        help=f'Ruta a charts.db (default: {CHARTS_DB})')
    parser.add_argument('--force',      action='store_true',
                        help='Reemplazar secciones existentes')
    parser.add_argument('--dry-run',    action='store_true',
                        help='No modificar archivos')
    parser.add_argument('--no-awards',  action='store_true',
                        help='Omitir sección ## awards')
    parser.add_argument('--no-charts',  action='store_true',
                        help='Omitir sección ## charts')
    args = parser.parse_args()

    if not os.path.exists(args.charts_db):
        print(f"⚠ charts.db no encontrada en {args.charts_db}")
        print("  → charts se obtendrán de Wikidata (más lento)")
        print("  → Ejecuta primero: python3 scripts/build_charts_db.py\n")

    kwargs = dict(
        force=args.force, dry_run=args.dry_run,
        no_awards=args.no_awards, no_charts=args.no_charts,
        charts_db=args.charts_db,
    )

    if args.file:
        process_file(args.file, **kwargs)
        return

    for root, _, files in os.walk(args.folder):
        for filename in sorted(files):
            if not filename.endswith('.md'):
                continue
            try:
                process_file(os.path.join(root, filename), **kwargs)
            except Exception as e:
                print(f"Error en {filename}: {e}")


if __name__ == "__main__":
    main()
