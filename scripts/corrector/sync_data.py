#!/usr/bin/env python3
"""
sync_data.py — Sync data/ into data_corregida/

• Existing entities: merge new content (new list items, new entries not already present)
• New entities: copy to data_corregida/pendiente/{subdir}/  (skip if already there)
• Reactivates validated entities when new content is merged
"""
import os, re, json, shutil

SOURCE         = './data'
DEST           = './correcciones'
PENDING_DIR    = './pendiente'
VALIDATED_JSON = os.path.join(DEST, 'validated.json')

SUBDIRS = ['artists', 'genres', 'labels', 'concerts', 'instruments']
ETYPE   = {'artists': 'artist', 'genres': 'genre', 'labels': 'label',
           'concerts': 'concert', 'instruments': 'instrument'}

LIST_SECS = {'members', 'member_of', 'genres', 'labels', 'concerts', 'instruments'}
ENTRY_RE  = re.compile(r'^\*\*(.+?)\*\*\s*:\s*(.+)')
# Don't merge the derived ## artists section from entity source files
SKIP_ENTITY_SECS = {'artists'}


def slug(name):
    s = name.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return s.strip('-') or 'unknown'


def _sec_name(line):
    m = re.match(r'^##\s+(.+)', line.strip())
    return m.group(1).strip().lower().replace(' ', '_') if m else None


def _parse_sections(fp):
    """Parse MD file → {section_key: {'type': 'list'|'entry', 'items': list|dict}}"""
    result = {}
    cur = None
    with open(fp, 'r', encoding='utf-8') as f:
        for raw in f:
            s = raw.strip()
            if not s: continue
            sec = _sec_name(raw)
            if sec is not None:
                cur = sec; continue
            if s.startswith('#'):
                cur = None; continue
            if cur is None: continue
            if cur in LIST_SECS:
                result.setdefault(cur, {'type': 'list', 'items': []})['items'].append(
                    s.lstrip('- ').strip()
                )
            else:
                me = ENTRY_RE.match(s)
                if me:
                    result.setdefault(cur, {'type': 'entry', 'items': {}})['items'][
                        me.group(1).strip()
                    ] = me.group(2).strip()
    return result


def _read(fp):
    with open(fp, 'r', encoding='utf-8') as f: return f.readlines()

def _write(fp, lines):
    with open(fp, 'w', encoding='utf-8') as f: f.writelines(lines)


def _append_to_section(fp, sec, new_line):
    """Append new_line to an existing section in fp, creating the section if absent."""
    lines  = _read(fp)
    header = sec.replace('_', ' ')     # 'member_of' → 'member of' for ## header
    sec_start = None
    for i, line in enumerate(lines):
        if _sec_name(line) == sec:
            sec_start = i; break
    if sec_start is None:
        while lines and not lines[-1].strip(): lines.pop()
        lines += [f'\n## {header}\n', new_line]
    else:
        end = len(lines)
        for i in range(sec_start + 1, len(lines)):
            s = lines[i].strip()
            if s.startswith('##') or (s.startswith('#') and not s.startswith('##')):
                end = i; break
        while end > sec_start + 1 and not lines[end - 1].strip(): end -= 1
        lines.insert(end, new_line)
    _write(fp, lines)


def merge_into(src, dst, skip=None):
    """Merge new content from src into dst. Returns True if dst was modified."""
    skip = skip or set()
    src_secs = _parse_sections(src)
    dst_secs = _parse_sections(dst)
    changed  = False
    for sec, data in src_secs.items():
        if sec in skip: continue
        if data['type'] == 'list':
            dst_lower = {x.lower() for x in dst_secs.get(sec, {}).get('items', [])}
            for item in data['items']:
                if item and item.lower() not in dst_lower:
                    _append_to_section(dst, sec, f'- {item}\n')
                    dst_lower.add(item.lower())
                    changed = True
        else:
            dst_lower = {k.lower() for k in dst_secs.get(sec, {}).get('items', {})}
            for title, desc in data['items'].items():
                if title.lower() not in dst_lower:
                    _append_to_section(dst, sec, f'**{title}** : {desc}\n')
                    dst_lower.add(title.lower())
                    changed = True
    return changed


def load_validated():
    if os.path.exists(VALIDATED_JSON):
        with open(VALIDATED_JSON, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_validated(v):
    os.makedirs(DEST, exist_ok=True)
    with open(VALIDATED_JSON, 'w', encoding='utf-8') as f:
        json.dump(v, f, ensure_ascii=False, indent=2)


def main():
    os.makedirs(DEST, exist_ok=True)
    validated    = load_validated()
    updated, reactivated, new_pending = [], [], []

    for subdir in SUBDIRS:
        src_dir = os.path.join(SOURCE, subdir)
        dst_dir = os.path.join(DEST, subdir)
        pnd_dir = os.path.join(PENDING_DIR, subdir)
        if not os.path.isdir(src_dir): continue
        etype = ETYPE[subdir]
        skip  = SKIP_ENTITY_SECS if subdir != 'artists' else set()

        for fn in sorted(os.listdir(src_dir)):
            if not fn.endswith('.md'): continue
            src_path = os.path.join(src_dir, fn)
            dst_path = os.path.join(dst_dir, fn)
            pnd_path = os.path.join(pnd_dir, fn)

            if os.path.exists(dst_path):
                if merge_into(src_path, dst_path, skip=skip):
                    updated.append(f'{subdir}/{fn}')
                    key = f'{etype}:{fn[:-3]}'
                    if key in validated:
                        del validated[key]
                        reactivated.append(key)
            elif not os.path.exists(pnd_path):
                os.makedirs(pnd_dir, exist_ok=True)
                shutil.copy2(src_path, pnd_path)
                new_pending.append(f'{subdir}/{fn}')

    # curiosities.md (flat file, no ## sections)
    src_c = os.path.join(SOURCE, 'curiosities.md')
    dst_c = os.path.join(DEST, 'curiosities.md')
    if os.path.exists(src_c):
        if os.path.exists(dst_c):
            with open(src_c, 'r', encoding='utf-8') as f:
                src_e = {m.group(1).strip(): m.group(2).strip()
                         for line in f if (m := ENTRY_RE.match(line.strip()))}
            with open(dst_c, 'r', encoding='utf-8') as f:
                dst_k = {m.group(1).strip().lower()
                         for line in f if (m := ENTRY_RE.match(line.strip()))}
            new = {k: v for k, v in src_e.items() if k.lower() not in dst_k}
            if new:
                with open(dst_c, 'a', encoding='utf-8') as f:
                    for k, v in sorted(new.items()): f.write(f'**{k}** : {v}\n')
                updated.append('curiosities.md')
        else:
            shutil.copy2(src_c, dst_c)

    save_validated(validated)

    print('Sync completo:')
    print(f'  Actualizados:       {len(updated)}')
    print(f'  Reactivados:        {len(reactivated)}')
    print(f'  Nuevos pendientes:  {len(new_pending)}')
    for f in updated[:5]:      print(f'    ~ {f}')
    if len(updated) > 5:       print(f'    ... y {len(updated) - 5} más')
    for f in new_pending[:10]: print(f'    + {f}')
    if len(new_pending) > 10:  print(f'    ... y {len(new_pending) - 10} más')


if __name__ == '__main__':
    main()
