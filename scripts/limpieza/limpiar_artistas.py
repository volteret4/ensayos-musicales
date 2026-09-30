#!/usr/bin/env python3
"""
limpiar_artistas.py — Aplica correcciones/decisiones_artistas.txt a las fichas de artista

Lee data/ y pendiente/ y reescribe las fichas aplicando las decisiones (qué
artista se fusiona con cuál, cuál se elimina, qué entradas sobran) junto a las
reglas generales R1–R8 descritas al principio del fichero de decisiones.

Es idempotente: ejecutarlo varias veces sobre datos ya limpios no cambia nada,
así que se puede lanzar cada vez que se añaden decisiones nuevas (a mano, desde
el editor web o aceptando propuestas de un lote de revisión).

Uso:
    python3 scripts/limpieza/limpiar_artistas.py --in-place  # reescribe data/ y pendiente/
    python3 scripts/limpieza/limpiar_artistas.py             # copia en limpio/ (para comparar)
    python3 scripts/limpieza/limpiar_artistas.py --dry-run   # solo informe
"""
import os, re, sys, shutil, sqlite3, argparse, unicodedata, importlib.util
from collections import defaultdict, Counter

SRC_DIRS   = ['data', 'pendiente']
OUT        = 'limpio'
TMP_OUT    = '.limpieza_tmp'
DECISIONS  = 'correcciones/decisiones_artistas.txt'
REPORT     = 'correcciones/INFORME_limpieza.md'
CHARTS_DB  = 'db/charts.db'
OTHER_SUBS = ['genres', 'labels', 'concerts', 'instruments']

LIST_SECS  = ['member of', 'members', 'genres', 'labels', 'concerts', 'instruments']
ENTRY_SECS = ['albums', 'songs', 'curiosities']
ENRICH     = ['awards', 'charts', 'lists']
ENTRY_RE   = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.*)$')


# ── Normalización ─────────────────────────────────────────────────────────────

def norm(n):
    """Clave de comparación (R2): sin acentos, mayúsculas, apóstrofes, 'The', puntuación."""
    n = unicodedata.normalize('NFKD', n)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = n.lower().replace('&', ' and ').replace('+', ' and ')
    n = re.sub(r"[’'‘`´\".,!?:;*]", '', n)
    n = re.sub(r'^the\s+', '', n)
    return re.sub(r'[^a-z0-9$]+', ' ', n).strip()


def strip_roles(n):
    """R7: quita anotaciones de rol '(drums)', '(former)'… y sufijos ' - left 1986'."""
    b = re.sub(r'\s*\([^()]*\)', ' ', n)
    b = re.sub(r'\s+-\s+.*$', '', b)
    b = re.sub(r'\s+', ' ', b).strip()
    return b or n


def slug(name):
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s.strip('-') or 'unknown'


# ── Lectura de fichas ─────────────────────────────────────────────────────────

class Entity:
    def __init__(self, name, where, path):
        self.name, self.where, self.path = name, where, path
        self.lists   = defaultdict(list)          # sec -> [str]
        self.entries = defaultdict(list)          # sec -> [(title, body)]
        self.enrich  = defaultdict(list)          # sec -> [raw line]


def read_entity(path, where):
    ent, sec = None, None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            s = raw.rstrip('\n').strip()
            if not s:
                continue
            m = re.match(r'^#\s+artist\s+-\s+(.+)$', s)
            if m:
                ent = Entity(m.group(1).strip(), where, path)
                continue
            m = re.match(r'^##\s+(.+)$', s)
            if m:
                sec = m.group(1).strip().lower()
                continue
            if ent is None or sec is None:
                continue
            if sec in LIST_SECS:
                item = s.lstrip('- ').strip()
                if item:
                    ent.lists[sec].append(item)
            elif sec in ENRICH:
                ent.enrich[sec].append(s)
            else:
                me = ENTRY_RE.match(s)
                if me:
                    ent.entries[sec].append((me.group(1).strip(), me.group(2).strip()))
    return ent


def load_entities():
    """R1: una ficha de pendiente/ que ya existe en data/ solo aporta lo que data/ no tenga."""
    ents = []
    for where in SRC_DIRS:
        d = os.path.join(where, 'artists')
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.md'):
                e = read_entity(os.path.join(d, fn), where)
                if e:
                    ents.append(e)
    return ents


# ── Decisiones ────────────────────────────────────────────────────────────────

class Decisions:
    def __init__(self, path):
        self.glob, self.scoped, self.ops = {}, {}, []
        self.used = set()
        # destinos con paréntesis elegidos a propósito ('Manfred Mann (músico)'):
        # son nombres definitivos, R7 no debe quitarles el paréntesis después
        self.explicit = set()
        for ln, raw in enumerate(open(path, encoding='utf-8'), 1):
            s = raw.strip()
            if not s or s.startswith('#') or '=>' not in s:
                continue
            left, right = [x.strip() for x in s.rsplit('=>', 1)]
            target = None if right == '-' else right
            if ' :: ' in left:
                parts = [p.strip() for p in left.split(' :: ')]
                if len(parts) == 3:
                    self.ops.append((ln, parts[0], parts[1].lower(), parts[2], target))
                continue
            if target and '(' in target:
                self.explicit.add(norm(target))
            m = re.match(r'^\[(.+?)\]\s+(.+)$', left)
            if m:
                self.scoped[(norm(m.group(1)), norm(m.group(2)))] = (target, ln)
            else:
                self.glob[norm(left)] = (target, ln)

    def lookup(self, name):
        if norm(name) in self.explicit and norm(name) not in self.glob:
            return True, name
        for k in (norm(name), norm(strip_roles(name))):
            if k in self.glob:
                t, ln = self.glob[k]
                self.used.add(ln)
                return True, t
        return False, None

    def lookup_scoped(self, band_names, member):
        for b in band_names:
            for k in (norm(member), norm(strip_roles(member))):
                if (norm(b), k) in self.scoped:
                    t, ln = self.scoped[(norm(b), k)]
                    self.used.add(ln)
                    return True, t
        return False, None


DELETED = object()


class Canon:
    """Resuelve nombre → nombre canónico (o DELETED)."""
    def __init__(self, dec):
        self.dec = dec
        self.display = {}            # norm(canon) -> nombre mostrado elegido

    def resolve(self, name, depth=0):
        found, t = self.dec.lookup(name)
        if found:
            if t is None:
                return DELETED
            if depth < 6 and norm(t) != norm(name):
                r = self.resolve(t, depth + 1)
                # un destino con paréntesis explícito se respeta tal cual
                return t if (r is not DELETED and '(' in t and norm(r) == norm(strip_roles(t))) else r
            return t
        return strip_roles(name)

    def member(self, band_raw, member_raw):
        band_c = self.resolve(band_raw)
        names = [band_raw] + ([band_c] if band_c is not DELETED else [])
        found, t = self.dec.lookup_scoped(names, member_raw)
        if found:
            return band_c, (DELETED if t is None else self.resolve(t))
        return band_c, self.resolve(member_raw)


# ── R3: agrupación de títulos de canciones/álbumes ────────────────────────────

ANNOT = re.compile(r'\d{4}|year|unspecified|specified|unknown|undated|n/?a\b|xxxx|yyyy|not given|'
                   r'mentioned|cover|version|demo|single|remix|live|edition|reissue|album|\bep\b|'
                   r'soundtrack|survey|unreleased|original|debut|implied|circa|c\.|early|late|'
                   r'mid-|\d0s', re.I)


def split_title(t):
    """→ (base, year|None). Quita '(1986)', '(Year not specified)', ' - comentario'."""
    year = None
    base = t.strip()
    base = re.sub(r'\s+[-–—]\s+.*$', '', base)
    while True:
        m = re.search(r'\s*\(([^()]*)\)\s*$', base)
        if not m or not ANNOT.search(m.group(1)) or m.start() == 0:   # '(Título entre paréntesis)'
            break
        y = re.match(r'^(?:c\.?\s*|circa\s*)?(?:[A-Za-z]+\.?\s+(?:\d{1,2},?\s+)?)?(1[89]\d\d|20\d\d)\b(?!s)',
                     m.group(1).strip())
        if y and not year:
            year = y.group(1)
        base = base[:m.start()].strip()
    return (base or t.strip()), year


def group_titles(entries):
    """R3: devuelve entries con títulos unificados."""
    groups = defaultdict(list)
    for i, (t, b) in enumerate(entries):
        base, year = split_title(t)
        groups[norm(base) or t].append((i, base, year))
    new = list(entries)
    for key, items in groups.items():
        years = Counter(y for _, _, y in items if y)
        if len(years) > 1:
            # años distintos explícitos: cada año su grupo, los sin año al más frecuente
            main = years.most_common(1)[0][0]
            for i, base, y in items:
                y = y or main
                new[i] = (f'{base} ({y})', entries[i][1])
            continue
        year = next(iter(years), None)
        base = Counter(b for _, b, _ in items).most_common(1)[0][0]
        title = f'{base} ({year})' if year else base
        if len(items) > 1 or ANNOT.search(entries[items[0][0]][0]):
            for i, _, _ in items:
                new[i] = (title, entries[i][1])
    return new


# ── Operaciones sobre entradas ────────────────────────────────────────────────

def match_titles(entries, pat):
    exact = [i for i, (t, _) in enumerate(entries) if t == pat]
    if exact:
        return exact
    pref = [i for i, (t, _) in enumerate(entries) if t.startswith(pat)]
    if pref:
        return pref
    pl = pat.lower()
    return [i for i, (t, _) in enumerate(entries) if t.lower().startswith(pl)]


# ── R4: charts / lists desde db/charts.db con coincidencia exacta ─────────────

def load_enricher():
    """Devuelve enrich(nombre) → (charts, lists), o None si no hay charts.db o faltan
    dependencias (p. ej. dentro del contenedor del editor): entonces se conservan
    las secciones ## charts / ## lists que ya tuviera cada ficha."""
    try:
        return _load_enricher()
    except Exception as e:
        print(f'(charts no recalculados: {e})')
        return None


def _load_enricher():
    if not os.path.exists(CHARTS_DB):
        raise FileNotFoundError(CHARTS_DB)
    spec = importlib.util.spec_from_file_location('m4', 'scripts/4_awards_charts.py')
    m4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m4)
    m4.load_collection_urls('db/must_hear_rym_new.db')
    conn = sqlite3.connect(CHARTS_DB)
    conn.row_factory = sqlite3.Row

    def enrich(name):
        n = m4.normalize(name)
        row = conn.execute('SELECT id FROM artists WHERE name_norm = ?', (n,)).fetchone() if n else None
        if not row:
            return [], []
        aid = row['id']
        charts = conn.execute('SELECT titulo, chart, year, position, semanas FROM chart_entries '
                              'WHERE artist_id = ? ORDER BY chart, year, position', (aid,)).fetchall()
        lists = conn.execute(
            '''SELECT le.album_name, le.year, le.rank, le.scaruffi_rating, le.aoty_score,
                      le.metacritic_score, le.sputnik_rating, li.name AS list_name, li.source
               FROM list_entries le JOIN lists li ON li.id = le.list_id
               WHERE le.artist_id = ? ORDER BY li.source, li.name, le.rank''', (aid,)).fetchall()
        return ([m4.format_chart_entry(dict(c)) for c in charts],
                [m4.format_list_entry(dict(e)) for e in lists])
    return enrich


# ── Principal ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--in-place', action='store_true',
                    help='reescribe data/ y pendiente/ en vez de generar limpio/')
    args = ap.parse_args()
    out_dir = TMP_OUT if args.in_place else OUT
    if os.path.isdir(TMP_OUT):
        shutil.rmtree(TMP_OUT)

    dec = Decisions(DECISIONS)
    canon = Canon(dec)
    ents = load_entities()
    log = defaultdict(list)

    # 1. nombre canónico de cada ficha
    data_norms = {norm(e.name) for e in ents if e.where == 'data'}
    for e in ents:
        e.canon = canon.resolve(e.name)

    # 2. operaciones de entrada (antes de fusionar), por nombre original o canónico
    moves = []
    by_norm = defaultdict(list)
    for e in ents:
        by_norm[norm(e.name)].append(e)
        if e.canon is not DELETED and norm(e.canon) != norm(e.name):
            by_norm[norm(e.canon)].append(e)
    for ln, who, sec, pat, target in dec.ops:
        k = norm(who)
        hits = 0
        for e in by_norm.get(k, []):
            store = e.entries if sec in ENTRY_SECS else e.lists
            items = store.get(sec, [])
            if sec in LIST_SECS:
                idx = [i for i, t in enumerate(items) if t == pat or t.startswith(pat)]
            else:
                idx = match_titles(items, pat)
            for i in sorted(idx, reverse=True):
                hits += 1
                if target is None:
                    items.pop(i)
                elif target.startswith('@'):
                    moves.append((target[1:].strip(), sec, items.pop(i)))
                elif sec in ENTRY_SECS:
                    items[i] = (target, items[i][1])
        if hits:
            dec.used.add(ln)

    # 3. agrupar fichas por nombre canónico
    groups = defaultdict(list)
    for e in ents:
        if e.canon is DELETED:
            log['eliminados'].append(e.name)
            continue
        groups[norm(e.canon)].append(e)
    display = {}
    for k, es in groups.items():
        cands = Counter()
        for e in es:
            # el nombre tal cual lo escribió una decisión o la variante con más contenido
            size = sum(len(v) for v in e.entries.values()) + sum(len(v) for v in e.lists.values())
            name = e.canon if norm(e.name) != norm(e.canon) else e.name
            cands[name] += size + (1000 if e.canon != strip_roles(e.name) else 0) \
                + (5 if e.where == 'data' else 0)
        best = max(cands, key=lambda n: (cands[n], sum(ord(c) > 127 for c in n), n))
        # una decisión 'Chemical Brothers => The Chemical Brothers' fija la grafía aunque
        # para norm() sean el mismo nombre
        fijo = dec.glob.get(k)
        if fijo and fijo[0] and norm(fijo[0]) == k:
            best = fijo[0]
        display[k] = best
        for e in es:
            if e.name != best:
                log['fusionados'].append((e.name, best))

    def disp(name):
        return display.get(norm(name), name)

    # 4. relaciones miembro/grupo (R6)
    rels = set()
    for e in ents:
        for m in e.lists.get('members', []):
            rels.add((e.name, m))
        for b in e.lists.get('member of', []):
            rels.add((b, e.name))
    final_rels = set()
    for band, member in rels:
        b, m = canon.member(band, member)
        if b is DELETED or m is DELETED:
            continue
        if norm(b) == norm(m):
            continue
        final_rels.add((norm(b), norm(m)))
        for n in (b, m):
            if norm(n) not in display:
                display[norm(n)] = n
                groups[norm(n)] = []

    # 5. construir fichas finales
    out = {}
    for k, es in groups.items():
        name = display[k]
        f = {'name': name, 'where': 'data' if (any(e.where == 'data' for e in es) or k in data_norms)
             else 'pendiente', 'lists': defaultdict(list), 'entries': defaultdict(list),
             'awards': [], 'old_charts': [], 'old_lists': []}
        for e in es:
            if norm(e.name) == k:
                f['old_charts'] = f['old_charts'] or list(e.enrich.get('charts', []))
                f['old_lists'] = f['old_lists'] or list(e.enrich.get('lists', []))
            for sec in ['genres', 'labels', 'concerts', 'instruments']:
                for it in e.lists.get(sec, []):
                    it = strip_roles(it) if sec != 'concerts' else it
                    if norm(it) not in (norm(x) for x in f['lists'][sec]):
                        f['lists'][sec].append(it)
            for sec in ENTRY_SECS:
                for t, b in e.entries.get(sec, []):
                    if (t, b) not in f['entries'][sec]:
                        f['entries'][sec].append((t, b))
            if norm(e.name) == k and e.enrich.get('awards') and not f['awards']:   # R8
                f['awards'] = list(e.enrich['awards'])
        out[k] = f
    for tgt, sec, item in moves:
        k = norm(canon.resolve(tgt) if canon.resolve(tgt) is not DELETED else tgt)
        if k not in out:
            display[k] = tgt
            out[k] = {'name': tgt, 'where': 'pendiente', 'lists': defaultdict(list),
                      'entries': defaultdict(list), 'awards': [], 'old_charts': [], 'old_lists': []}
        out[k]['entries'][sec].append(item)
    for b, m in final_rels:
        out[b]['lists']['members'].append(display[m])
        out[m]['lists']['member of'].append(display[b])
    for f in out.values():
        for sec in ('albums', 'songs'):
            f['entries'][sec] = group_titles(f['entries'][sec])
            seen, uniq = set(), []
            for t, b in f['entries'][sec]:
                if (t, b) not in seen:
                    seen.add((t, b)); uniq.append((t, b))
            f['entries'][sec] = sorted(uniq, key=lambda x: norm(x[0]))

    # 6. R5: sin datos de transcript ni relaciones → fuera
    for k in list(out):
        f = out[k]
        if not any(f['entries'][s] for s in ENTRY_SECS) and not f['lists']['members'] \
                and not f['lists']['member of']:
            log['vacios'].append(f['name'])
            del out[k]

    # 7. escribir
    enrich = load_enricher()
    nchart = nlist = 0
    if not args.dry_run:
        for where in SRC_DIRS:
            d = os.path.join(out_dir, where, 'artists')
            if os.path.isdir(d):
                shutil.rmtree(d)
            os.makedirs(d)
    slugs = defaultdict(list)
    for k, f in sorted(out.items(), key=lambda x: x[1]['name'].lower()):
        if enrich:
            charts, lists = enrich(f['name'])
        else:
            charts, lists = f['old_charts'], f['old_lists']
        nchart += bool(charts); nlist += bool(lists)
        lines = [f"# artist - {f['name']}\n\n"]
        for sec in LIST_SECS:
            items = sorted(set(f['lists'][sec]), key=str.lower)
            if items:
                lines.append(f'## {sec}\n' + ''.join(f'- {i}\n' for i in items) + '\n')
        for sec in ENTRY_SECS:
            if f['entries'][sec]:
                lines.append(f'## {sec}\n' + ''.join(f'**{t}** : {b}\n' for t, b in f['entries'][sec]) + '\n')
        for sec, items in (('awards', f['awards']), ('charts', charts), ('lists', lists)):
            if items:
                lines.append(f'## {sec}\n' + '\n'.join(items) + '\n\n')
        fn = slug(f['name']) + '.md'
        slugs[fn].append(f['name'])
        if len(slugs[fn]) > 1:          # dos artistas distintos con el mismo fichero: no pisar
            fn = f"{slug(f['name'])}-{len(slugs[fn])}.md"
        if not args.dry_run:
            with open(os.path.join(out_dir, f['where'], 'artists', fn), 'w', encoding='utf-8') as fh:
                fh.write(''.join(lines).rstrip('\n') + '\n')

    # 8. resto de entidades: copia con la sección ## artists canonizada
    if not args.dry_run:
        for where in SRC_DIRS:
            for sub in OTHER_SUBS:
                src, dst = os.path.join(where, sub), os.path.join(out_dir, where, sub)
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                if not os.path.isdir(src):
                    continue
                os.makedirs(dst)
                for fn in os.listdir(src):
                    txt, sec, res = open(os.path.join(src, fn), encoding='utf-8').read().split('\n'), None, []
                    for l in txt:
                        m = re.match(r'^##\s+(.+)$', l.strip())
                        if m:
                            sec = m.group(1).strip().lower()
                        elif sec == 'artists' and l.strip().startswith('- '):
                            c = canon.resolve(l.strip()[2:])
                            if c is DELETED or norm(c) not in out:
                                continue
                            l = f'- {display.get(norm(c), c)}'
                            if l in res:
                                continue
                        res.append(l)
                    open(os.path.join(dst, fn), 'w', encoding='utf-8').write('\n'.join(res))
            c = os.path.join(where, 'curiosities.md')
            if os.path.exists(c):
                shutil.copy2(c, os.path.join(out_dir, where, 'curiosities.md'))
        if args.in_place:
            # sustitución de data/ y pendiente/ por el resultado (sin tocar nada más)
            for where in SRC_DIRS:
                for sub in ['artists'] + OTHER_SUBS:
                    new = os.path.join(TMP_OUT, where, sub)
                    if not os.path.isdir(new):
                        continue
                    old = os.path.join(where, sub)
                    if os.path.isdir(old):
                        shutil.rmtree(old)
                    shutil.move(new, old)
            shutil.rmtree(TMP_OUT)

    # 9. informe
    total_in = len(ents)
    rep = [f'# Informe de limpieza de artistas\n',
           f'- Fichas de entrada: {total_in} (data + pendiente)',
           f'- Artistas resultantes: {len(out)}',
           f'- Eliminados por decisión: {len(log["eliminados"])}',
           f'- Fusionados/renombrados: {len(log["fusionados"])}',
           f'- Eliminados por quedar vacíos (R5): {len(log["vacios"])}',
           f'- Con charts recalculados: {nchart}; con listas: {nlist}',
           f'- Relaciones miembro↔grupo: {len(final_rels)}', '']
    unused = [raw.strip() for ln, raw in enumerate(open(DECISIONS, encoding='utf-8'), 1)
              if '=>' in raw and not raw.strip().startswith('#') and ln not in dec.used]
    rep += [f'## Decisiones que no encontraron nada ({len(unused)})', *[f'- `{u}`' for u in unused], '']
    clash = {fn: ns for fn, ns in slugs.items() if len(ns) > 1}
    rep += [f'## Colisiones de nombre de fichero ({len(clash)})', *[f'- {fn}: {ns}' for fn, ns in clash.items()], '']
    rep += ['## Fusionados / renombrados', *[f'- {a} → {b}' for a, b in sorted(set(log["fusionados"]), key=lambda x: x[1].lower())], '']
    rep += ['## Eliminados', *[f'- {a}' for a in sorted(set(log["eliminados"]), key=str.lower)], '']
    rep += ['## Eliminados por vacíos (R5)', *[f'- {a}' for a in sorted(set(log["vacios"]), key=str.lower)], '']
    report = REPORT if args.in_place else os.path.join(OUT, 'INFORME.md')
    os.makedirs(os.path.dirname(report), exist_ok=True)
    with open(report, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(rep) + '\n')
    print('\n'.join(rep[:10]))
    print(f'Decisiones sin efecto: {len(unused)} · colisiones: {len(clash)}')


if __name__ == '__main__':
    main()
