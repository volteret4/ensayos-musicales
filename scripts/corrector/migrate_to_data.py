#!/usr/bin/env python3
"""
migrate_to_data.py — Migración única: copia el contenido de correcciones/ a data/.

correcciones/ ha sido la copia de trabajo del corrector con ediciones manuales.
Después de esta migración, data/ es la única fuente de verdad y correcciones/
solo conserva validated.json y deleted.json.

Uso:
    python3 scripts/corrector/migrate_to_data.py             # ejecutar
    python3 scripts/corrector/migrate_to_data.py --dry-run   # solo mostrar cambios
    python3 scripts/corrector/migrate_to_data.py --cleanup   # también elimina dirs redundantes
"""
import os, shutil, argparse

SOURCE  = './correcciones'
DEST    = './data'
SUBDIRS = ['artists', 'genres', 'labels', 'concerts', 'instruments']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo muestra qué se haría, sin hacer cambios')
    parser.add_argument('--cleanup', action='store_true',
                        help='Elimina los directorios ahora redundantes en correcciones/')
    args = parser.parse_args()
    dry = args.dry_run

    copied = overwritten = 0

    for subdir in SUBDIRS:
        src_dir = os.path.join(SOURCE, subdir)
        dst_dir = os.path.join(DEST, subdir)
        if not os.path.isdir(src_dir):
            continue
        for fn in sorted(os.listdir(src_dir)):
            if not fn.endswith('.md'):
                continue
            src_path = os.path.join(src_dir, fn)
            dst_path = os.path.join(dst_dir, fn)
            if os.path.exists(dst_path):
                print(f'  overwrite: {subdir}/{fn}')
                overwritten += 1
            else:
                print(f'  copy new:  {subdir}/{fn}')
                copied += 1
            if not dry:
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src_path, dst_path)

    # curiosities.md
    src_c = os.path.join(SOURCE, 'curiosities.md')
    dst_c = os.path.join(DEST, 'curiosities.md')
    if os.path.exists(src_c):
        if os.path.exists(dst_c):
            print('  overwrite: curiosities.md')
            overwritten += 1
        else:
            print('  copy new:  curiosities.md')
            copied += 1
        if not dry:
            shutil.copy2(src_c, dst_c)

    prefix = '[DRY RUN] ' if dry else ''
    print(f'\n{prefix}Migración: {overwritten} sobreescritos, {copied} nuevos.')

    if not dry:
        if args.cleanup:
            print('\nEliminando directorios redundantes en correcciones/...')
            for subdir in SUBDIRS:
                d = os.path.join(SOURCE, subdir)
                if os.path.isdir(d):
                    shutil.rmtree(d)
                    print(f'  rm -rf {d}')
            c_file = os.path.join(SOURCE, 'curiosities.md')
            if os.path.exists(c_file):
                os.remove(c_file)
                print(f'  rm {c_file}')
            # Eliminar el directorio correcciones/data/ anidado (causa del bug de duplicados)
            nested = os.path.join(SOURCE, 'data')
            if os.path.isdir(nested):
                shutil.rmtree(nested)
                print(f'  rm -rf {nested}')
        else:
            print('\nPara eliminar los directorios ahora redundantes en correcciones/, ejecuta:')
            for subdir in SUBDIRS:
                d = os.path.join(SOURCE, subdir)
                if os.path.isdir(d):
                    print(f'  rm -rf {d}')
            c_file = os.path.join(SOURCE, 'curiosities.md')
            if os.path.exists(c_file):
                print(f'  rm {c_file}')
            nested = os.path.join(SOURCE, 'data')
            if os.path.isdir(nested):
                print(f'  rm -rf {nested}')
            print('\nO vuelve a ejecutar con --cleanup para hacerlo automáticamente.')


if __name__ == '__main__':
    main()
