#!/usr/bin/env python3
"""
lotes.py — Revisión por lotes de lo que entra desde los podcasts nuevos.

Flujo:
  1. scripts/3_merge_resumenes.py añade el contenido de los resúmenes nuevos a
     data/ y pendiente/ (ya canonizado con las decisiones existentes) y apunta
     cada artista tocado en la cola: correcciones/cola_revision.txt
  2. scripts/limpieza/revisar_lote.py (o el botón del editor web) coge N
     artistas de la cola, prepara una ficha de cada uno con los posibles
     duplicados que ya existen y se la pasa a Claude, que responde con
     decisiones en el mismo formato que correcciones/decisiones_artistas.txt.
     Cada respuesta se guarda como un lote en correcciones/lotes/.
  3. En el editor web (pestaña 🤖 Lotes) se aceptan, editan o rechazan las
     propuestas. «Aplicar» añade las aceptadas al fichero de decisiones y
     vuelve a ejecutar limpiar_artistas.py --in-place.

Solo usa la biblioteca estándar, para que funcione también dentro del
contenedor del editor (donde no hay CLI de Claude: allí se usa el modo manual,
copiando el prompt en claude.ai y pegando la respuesta).
"""
import os, re, json, sys, shutil, difflib, datetime, subprocess, tempfile

CORR        = 'correcciones'
DECISIONES  = os.path.join(CORR, 'decisiones_artistas.txt')
COLA        = os.path.join(CORR, 'cola_revision.txt')        # un JSON por línea
LOTES_DIR   = os.path.join(CORR, 'lotes')                    # lote_0001.txt (JSON)
SRC_DIRS    = ['data', 'pendiente']
LIST_SECS   = ['member of', 'members', 'genres', 'labels', 'concerts', 'instruments']
ENTRY_SECS  = ['albums', 'songs', 'curiosities']
ENTRY_RE    = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.*)$')

MODELO_DEFECTO = os.environ.get('LOTE_MODELO', 'opus')
TAM_DEFECTO    = int(os.environ.get('LOTE_TAM', '25'))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from limpiar_artistas import norm, strip_roles, split_title  # noqa: E402


def hoy():
    return datetime.date.today().isoformat()


# ── Fichero de decisiones ─────────────────────────────────────────────────────

LINEA_RE = re.compile(
    r'^(?:\[[^\]]+\]\s+)?[^\[\]]+?(?:\s::\s(?:albums|songs|curiosities|members|member of|genres|labels|concerts|instruments)\s::\s.+?)?\s=>\s.+$')


def linea_valida(linea):
    return bool(LINEA_RE.match(linea.strip())) and not linea.strip().startswith('#')


def anadir_decisiones(lineas, cabecera):
    """Añade líneas al fichero de decisiones bajo una cabecera '### …'."""
    lineas = [l.strip() for l in lineas if l and l.strip()]
    if not lineas:
        return 0
    with open(DECISIONES, 'a', encoding='utf-8') as f:
        f.write(f'\n### {cabecera}\n' + '\n'.join(lineas) + '\n')
    return len(lineas)


def registrar_edicion_web(linea):
    """Las ediciones hechas a mano en el editor también se guardan como decisión,
    para que los podcasts que lleguen después se corrijan igual."""
    if linea_valida(linea):
        anadir_decisiones([linea], f'editor web ({hoy()})')


# ── Cola de revisión ──────────────────────────────────────────────────────────

def cargar_cola():
    if not os.path.exists(COLA):
        return []
    with open(COLA, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def guardar_cola(items):
    os.makedirs(CORR, exist_ok=True)
    with open(COLA, 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')


def encolar(cola, artista, fichero, nuevo, original, anadidos, fuente):
    """Añade o amplía la entrada pendiente de un artista en la cola (en memoria)."""
    k = norm(artista)
    it = next((x for x in cola if x['estado'] == 'pendiente' and norm(x['artista']) == k), None)
    if it is None:
        it = {'artista': artista, 'fichero': fichero, 'nuevo': nuevo, 'originales': [],
              'anadido': [], 'fuentes': [], 'fecha': hoy(), 'estado': 'pendiente', 'lote': None}
        cola.append(it)
    it['fichero'] = fichero
    it['nuevo'] = it['nuevo'] or nuevo
    if original and original != artista and original not in it['originales']:
        it['originales'].append(original)
    for a in anadidos:
        if list(a) not in it['anadido']:
            it['anadido'].append(list(a))
    if fuente and fuente not in it['fuentes']:
        it['fuentes'].append(fuente)


def estadisticas():
    cola = cargar_cola()
    c = {'pendiente': 0, 'enviado': 0, 'revisado': 0}
    for it in cola:
        c[it['estado']] = c.get(it['estado'], 0) + 1
    return c


# ── Índice de artistas existentes ─────────────────────────────────────────────

def leer_ficha(path):
    ficha = {'nombre': '', 'lists': {}, 'entries': {}}
    sec = None
    if not os.path.exists(path):
        return ficha
    with open(path, encoding='utf-8') as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            m = re.match(r'^#\s+artist\s+-\s+(.+)$', s)
            if m:
                ficha['nombre'] = m.group(1).strip(); continue
            m = re.match(r'^##\s+(.+)$', s)
            if m:
                sec = m.group(1).strip().lower(); continue
            if sec in LIST_SECS:
                ficha['lists'].setdefault(sec, []).append(s.lstrip('- ').strip())
            elif sec in ENTRY_SECS:
                me = ENTRY_RE.match(s)
                if me:
                    ficha['entries'].setdefault(sec, []).append((me.group(1).strip(), me.group(2).strip()))
    return ficha


def indice_artistas():
    """[(nombre, 'data'|'pendiente', nº entradas, path)]"""
    idx = []
    for where in SRC_DIRS:
        d = os.path.join(where, 'artists')
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.md'):
                continue
            p = os.path.join(d, fn)
            nombre, n = '', 0
            with open(p, encoding='utf-8') as f:
                for l in f:
                    if l.startswith('# artist - '):
                        nombre = l[11:].strip()
                    elif l.startswith('**') or l.startswith('- '):
                        n += 1
            if nombre:
                idx.append((nombre, where, n, p))
    return idx


def parecidos(nombre, idx, norms=None, n=6):
    """Artistas existentes con nombre parecido (posibles duplicados o mala transcripción)."""
    k = norm(strip_roles(nombre))
    norms = norms or [norm(x[0]) for x in idx]
    cand = set(difflib.get_close_matches(k, norms, n=n, cutoff=0.72))
    words = k.split()
    if 2 <= len(words) <= 3 and len(words[-1]) > 3:          # posible persona: mismo apellido
        for i, nm in enumerate(norms):
            if nm.split()[-1:] == words[-1:] and nm != k:
                cand.add(nm)
                if len(cand) >= n + 3:
                    break
    if len(k) >= 5:                                            # contención ('X' ⊂ 'X and the Y')
        for nm in norms:
            if nm != k and len(nm) >= 4 and (f' {k} ' in f' {nm} ' or f' {nm} ' in f' {k} '):
                cand.add(nm)
    out = []
    for nombre2, where, cnt, _ in idx:
        if norm(nombre2) in cand and norm(nombre2) != k:
            out.append(f'{nombre2} [{where}, {cnt}]')
    return out[:n + 3]


# ── Prompt ────────────────────────────────────────────────────────────────────

SISTEMA = """Eres el revisor de una base de datos de música construida automáticamente a partir de
transcripciones (Whisper) de podcasts en inglés y español, resumidas después por otro modelo.
Los nombres llegan a menudo mal transcritos por fonética ("Crabwork" = Kraftwerk, "Mios" = Muse,
"Lee Amgala Gheri" = Liam Gallagher, "Tom York" = Thom Yorke), con roles entre paréntesis,
duplicados con variantes (acentos, "The", apodos, nombre real) o que ni siquiera son artistas.

Tu tarea: revisar las fichas que te paso y proponer SOLO las correcciones necesarias, en el
formato exacto del fichero de decisiones. No uses herramientas; responde solo con texto."""

FORMATO = """## Formato de respuesta (una decisión por línea, nada más)
Nombre tal cual => Nombre Canónico        renombrar / fusionar con un artista existente
Nombre tal cual => -                       eliminar (no es un artista, basura, fragmento)
[Grupo] Miembro => Nombre Canónico         corregir un miembro solo dentro de ese grupo
[Grupo] Miembro => -                       quitar esa relación miembro↔grupo (manager, pareja, productor, relación al revés)
Artista :: songs :: Título => Título Corregido (Año)
Artista :: albums :: Título => -           (sections: albums, songs, curiosities)
Artista :: curiosities :: Título => Otro Título Existente   (mismo hecho: se unifican sin perder fuentes)
Artista :: albums :: Título => @Otro Artista                (entrada atribuida al artista equivocado)

Tras cada línea puedes añadir un motivo breve en español:  "  # motivo".

## Qué buscar
1. Nombres mal transcritos por fonética: usa tu conocimiento musical para dar el nombre real
   (p. ej. "Rick Rubens" = Rick Rubin; "Barry Gordy" = Berry Gordy).
2. Duplicados: si en "Parecidos ya existentes" está el mismo artista con otra grafía, fusiona
   hacia ESE nombre exacto (el que tenga más entradas o la grafía oficial).
3. Entradas que no son una entidad real: fragmentos, "Members of X", "(two Englishmen)",
   "Unnamed guitarist", instrumentos sueltos… → "=> -".
4. Relaciones miembro↔grupo erróneas: managers, parejas, productores o invitados listados como
   miembros, o relaciones al revés → "[Grupo] Persona => -".
5. Títulos de canciones/álbumes MAL ESCRITOS, que no existen o atribuidos al artista equivocado.
   No hace falta limpiar comentarios ni "(Unknown Year)": el sistema ya los normaliza.
6. Curiosidades duplicadas (mismo hecho con distinto título): unifica el título.

## Reglas
- Las personas reales del mundo de la música que NO son músicos (productores, managers, A&R,
  periodistas, directores de vídeo) son fichas válidas: no las elimines.
- Solo corrige lo que sepas con seguridad. Si dudas, no escribas nada.
- Nunca propongas una línea cuyo destino sea igual al origen.
- Nombres de pila sueltos ("Mike", "Tom") solo se corrigen con [Grupo] (nunca globalmente).
- Títulos corregidos: título oficial + (año de publicación) si lo sabes con certeza.
- Homónimos (dos personas distintas con el mismo nombre): usa un paréntesis explícito,
  p. ej. "Mick Jones (Foreigner)". Un paréntesis que pones tú se conserva tal cual.

## Salida
Responde UNA sola vez, sin explicaciones, sin rectificar y sin texto antes o después.
Primera línea: DECISIONES. Después, solo las líneas de decisión (cada una con su "# motivo").
Si no hay nada que corregir, responde únicamente: SIN CAMBIOS
"""

EJEMPLOS = """## Ejemplos reales del fichero de decisiones
Crabwork => Kraftwerk
Mios => Muse
Nora Jones => Norah Jones
(three Englishmen) => -
Members of Sloan => -
[Oasis] Bonehead => Paul Arthurs
[Sex Pistols] Malcolm McLaren (manager) => -
[Arkells] Mike => Mike DeAngelis
Mick Jones (guitarist, songwriter) => Mick Jones (Foreigner)
Nirvana :: albums :: Evermind (Undefined Year) - Sound Defining Album => Nevermind (1991)
Metallica :: albums :: Albums Released in 2010s => -
Oasis :: curiosities :: Rockfield Studios Incident (May 1995) => Rockfield Studios Fight – Cricket Bat Incident (May 1995)
Paul McCartney :: songs :: Hey Jude (1968) => @The Beatles
"""


def ficha_texto(it, idx, norms):
    f = leer_ficha(it['fichero'])
    def clave(sec, t):     # el título puede haberse normalizado después (R3: año, comentarios)
        return (sec, norm(split_title(t)[0]))
    nuevos = {clave(s, t) for s, t in it.get('anadido', [])}
    donde = it['fichero'].split('/')[0]
    cab = f"### {f['nombre'] or it['artista']}  [{donde}{', FICHA NUEVA' if it.get('nuevo') else ''}]"
    lines = [cab]
    if it.get('originales'):
        lines.append('Escrito en los resúmenes como: ' + '; '.join(it['originales']))
    for sec in LIST_SECS:
        if f['lists'].get(sec):
            lines.append(f'{sec}: ' + '; '.join(f['lists'][sec]))
    for sec in ENTRY_SECS:
        ents = f['entries'].get(sec, [])
        if not ents:
            continue
        viejos = sorted({t for t, _ in ents if clave(sec, t) not in nuevos})
        if viejos:
            extra = f' (+{len(viejos) - 40} más)' if len(viejos) > 40 else ''
            lines.append(f'{sec} (ya existentes): ' + '; '.join(viejos[:40]) + extra)
        vistos = set()
        for t, d in ents:
            if clave(sec, t) in nuevos and (t, d[:60]) not in vistos:
                vistos.add((t, d[:60]))
                d = re.sub(r'\s+←.*$', '', d)
                lines.append(f'  ★ {sec} :: {t} — {d[:220]}')
    par = parecidos(f['nombre'] or it['artista'], idx, norms)
    if par:
        lines.append('Parecidos ya existentes: ' + '; '.join(par))
    return '\n'.join(lines)


def construir_prompt(items):
    idx = indice_artistas()
    norms = [norm(x[0]) for x in idx]
    fichas = '\n\n'.join(ficha_texto(it, idx, norms) for it in items)
    return (f"{FORMATO}\n{EJEMPLOS}\n## Fichas a revisar ({len(items)})\n"
            f"Las entradas marcadas con ★ son las que acaban de llegar de podcasts nuevos; "
            f"el resto ya estaba revisado (úsalo como contexto).\n\n{fichas}\n")


# ── Respuesta de Claude → propuestas ──────────────────────────────────────────

def parsear_respuesta(texto):
    props, descartadas = [], []
    if 'DECISIONES' in texto:                       # solo el último bloque de decisiones
        texto = texto[texto.rindex('DECISIONES') + len('DECISIONES'):]
    for raw in texto.splitlines():
        s = raw.strip().strip('`').strip()
        if not s or s.startswith('#') or '=>' not in s:
            continue
        s = re.sub(r'^[-*]\s+', '', s)
        motivo = ''
        m = re.match(r'^(.*?=>\s*.*?)\s+#\s*(.*)$', s)
        if m:
            s, motivo = m.group(1).strip(), m.group(2).strip()
        izq, der = [x.strip() for x in s.rsplit('=>', 1)]
        if izq.split(' :: ')[-1].strip() == der or re.sub(r'^\[[^\]]+\]\s+', '', izq) == der:
            descartadas.append(raw)                     # no cambia nada
            continue
        if linea_valida(s):
            props.append({'id': len(props) + 1, 'linea': s, 'motivo': motivo, 'estado': 'pendiente'})
        else:
            descartadas.append(raw)
    return props, descartadas


# ── Backends ──────────────────────────────────────────────────────────────────

def cli_disponible():
    return shutil.which('claude') is not None


def llamar_claude_cli(prompt, modelo=MODELO_DEFECTO, timeout=1800):
    """Usa el CLI de Claude Code (consume de tu plan, no requiere API key)."""
    cmd = ['claude', '-p', '--output-format', 'json', '--model', modelo, '--tools', '',
           '--no-session-persistence', '--system-prompt', SISTEMA]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       cwd=tempfile.gettempdir(), timeout=timeout)
    try:
        data = json.loads(r.stdout)
    except Exception:
        raise RuntimeError(f'claude -p falló ({r.returncode}): {(r.stderr or r.stdout)[:500]}')
    if data.get('is_error'):
        raise RuntimeError(f"claude -p devolvió error: {str(data.get('result'))[:500]}")
    u = data.get('usage') or {}
    uso = {'tokens_entrada': (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0)
                             + (u.get('cache_creation_input_tokens') or 0),
           'tokens_salida': u.get('output_tokens'), 'coste_usd': data.get('total_cost_usd')}
    return data.get('result', ''), uso


def llamar_api(prompt, modelo):
    """Alternativa con la API de Anthropic (pip install anthropic, ANTHROPIC_API_KEY)."""
    import anthropic
    alias = {'sonnet': 'claude-sonnet-5-5', 'opus': 'claude-opus-5-5', 'haiku': 'claude-haiku-4-5-20251001'}
    msg = anthropic.Anthropic().messages.create(
        model=alias.get(modelo, modelo), max_tokens=8000, system=SISTEMA,
        messages=[{'role': 'user', 'content': prompt}])
    texto = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
    return texto, {'tokens_entrada': msg.usage.input_tokens, 'tokens_salida': msg.usage.output_tokens}


# ── Lotes ─────────────────────────────────────────────────────────────────────

def ruta_prompt(n):
    return os.path.join(LOTES_DIR, f'lote_{int(n):04d}_prompt.md')


def ruta_respuesta(n):
    return os.path.join(LOTES_DIR, f'lote_{int(n):04d}_respuesta.md')


def lotes_esperando():
    return [l for l in listar_lotes() if l['estado'] == 'esperando_respuesta']


def _ruta_lote(n):
    return os.path.join(LOTES_DIR, f'lote_{int(n):04d}.txt')


def listar_lotes():
    if not os.path.isdir(LOTES_DIR):
        return []
    out = []
    for fn in sorted(os.listdir(LOTES_DIR)):
        if re.match(r'^lote_\d{4}\.txt$', fn):
            with open(os.path.join(LOTES_DIR, fn), encoding='utf-8') as f:
                out.append(json.load(f))
    return out


def cargar_lote(n):
    with open(_ruta_lote(n), encoding='utf-8') as f:
        return json.load(f)


def guardar_lote(lote):
    os.makedirs(LOTES_DIR, exist_ok=True)
    with open(_ruta_lote(lote['id']), 'w', encoding='utf-8') as f:
        json.dump(lote, f, ensure_ascii=False, indent=1)


def _estado_lote(lote):
    if lote.get('estado') == 'esperando_respuesta':
        return 'esperando_respuesta'
    ps = lote.get('propuestas', [])
    if any(p['estado'] == 'pendiente' for p in ps):
        return 'por_revisar'
    if any(p['estado'] == 'aceptada' for p in ps):
        return 'por_aplicar'
    return 'cerrado'


def crear_lote(tam=TAM_DEFECTO, backend='sesion', modelo=MODELO_DEFECTO, log=print):
    """Coge `tam` artistas de la cola y crea un lote.
    backend: sesion/manual (por defecto: solo prepara el prompt, lo revisa una sesión de
    Claude Code o claude.ai) | claude (CLI `claude -p`) | api (SDK anthropic, de pago).
    Devuelve el lote (o None si la cola está vacía)."""
    cola = cargar_cola()
    items = [it for it in cola if it['estado'] == 'pendiente'][:tam]
    if not items:
        log('La cola de revisión está vacía.')
        return None
    if backend in ('auto', 'sesion'):
        # por defecto nadie llama a Claude: el lote se revisa en una sesión de Claude Code
        # (/revisar-lotes, con tu plan) o pegando el prompt en claude.ai
        backend = 'manual'
    n = max([l['id'] for l in listar_lotes()] or [0]) + 1
    prompt = construir_prompt(items)
    lote = {'id': n, 'fecha': hoy(), 'backend': backend, 'modelo': modelo,
            'artistas': [it['artista'] for it in items], 'prompt': SISTEMA + '\n\n' + prompt,
            'respuesta': '', 'propuestas': [], 'descartadas': [], 'uso': {}, 'estado': ''}
    if backend == 'manual':
        lote['estado'] = 'esperando_respuesta'
        os.makedirs(LOTES_DIR, exist_ok=True)
        with open(ruta_prompt(n), 'w', encoding='utf-8') as f:
            f.write(lote['prompt'])
        log(f'Lote {n}: prompt en {ruta_prompt(n)} · respuesta en {ruta_respuesta(n)} y luego '
            f'revisar_lote.py --importar {n} {ruta_respuesta(n)}  (o pégala en el editor web)')
    else:
        log(f'Lote {n}: consultando a Claude ({backend}, {modelo}) con {len(items)} artistas…')
        texto, uso = (llamar_claude_cli(prompt, modelo) if backend == 'claude' else llamar_api(prompt, modelo))
        lote['respuesta'], lote['uso'] = texto, uso
        lote['propuestas'], lote['descartadas'] = parsear_respuesta(texto)
        lote['estado'] = _estado_lote(lote)
        log(f"Lote {n}: {len(lote['propuestas'])} propuestas · uso {uso}")
    guardar_lote(lote)
    for it in items:
        it['estado'], it['lote'] = 'enviado', n
    if lote['estado'] == 'cerrado':              # SIN CAMBIOS: todo revisado
        for it in items:
            it['estado'] = 'revisado'
    guardar_cola(cola)
    return lote


def importar_respuesta(n, texto):
    lote = cargar_lote(n)
    lote['respuesta'] = texto
    lote['propuestas'], lote['descartadas'] = parsear_respuesta(texto)
    lote['estado'] = ''
    lote['estado'] = _estado_lote(lote)
    guardar_lote(lote)
    if lote['estado'] == 'cerrado':
        _cerrar_items(n)
    return lote


def marcar_propuesta(n, pid, estado, linea=None):
    """estado: aceptada | rechazada | pendiente. `linea` permite editarla antes de aceptar."""
    lote = cargar_lote(n)
    for p in lote['propuestas']:
        if p['id'] == pid:
            if linea is not None:
                if not linea_valida(linea):
                    raise ValueError(f'Formato no válido: {linea}')
                p['linea'] = linea.strip()
            if p['estado'] != 'aplicada':
                p['estado'] = estado
    lote['estado'] = _estado_lote(lote)
    guardar_lote(lote)
    return lote


def anadir_propuesta(n, linea, motivo='añadida a mano'):
    lote = cargar_lote(n)
    if not linea_valida(linea):
        raise ValueError(f'Formato no válido: {linea}')
    pid = max([p['id'] for p in lote['propuestas']] or [0]) + 1
    lote['propuestas'].append({'id': pid, 'linea': linea.strip(), 'motivo': motivo, 'estado': 'aceptada'})
    lote['estado'] = _estado_lote(lote)
    guardar_lote(lote)
    return lote


def _cerrar_items(n):
    cola = cargar_cola()
    for it in cola:
        if it.get('lote') == n and it['estado'] == 'enviado':
            it['estado'] = 'revisado'
    guardar_cola(cola)


def aplicar_aceptadas(ejecutar_limpieza=True, log=print):
    """Pasa las propuestas aceptadas al fichero de decisiones y reaplica la limpieza."""
    total = 0
    for lote in listar_lotes():
        acc = [p for p in lote['propuestas'] if p['estado'] == 'aceptada']
        if acc:
            total += anadir_decisiones([p['linea'] for p in acc],
                                       f"lote {lote['id']:04d} ({lote['fecha']}) — revisado en web {hoy()}")
            for p in acc:
                p['estado'] = 'aplicada'
        lote['estado'] = _estado_lote(lote)
        guardar_lote(lote)
        if lote['estado'] == 'cerrado':
            _cerrar_items(lote['id'])
    log(f'{total} decisiones añadidas a {DECISIONES}')
    salida = ''
    if ejecutar_limpieza:
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'limpiar_artistas.py')
        r = subprocess.run([sys.executable, script, '--in-place'], capture_output=True, text=True)
        salida = (r.stdout + r.stderr).strip()
        if r.returncode != 0:
            raise RuntimeError(salida[-2000:])
        log(salida.splitlines()[-1] if salida else '')
    return total, salida
