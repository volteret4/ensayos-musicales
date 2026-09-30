#!/usr/bin/env python3
"""
revisar_lote.py — Prepara (y opcionalmente pide a Claude) lotes de revisión de artistas nuevos.

Lo normal es NO llamar a Claude desde aquí: se preparan los lotes y se revisan en una
sesión de Claude Code con tu plan, con el comando  /revisar-lotes N  (ver
.claude/commands/revisar-lotes.md), o pegando el prompt en claude.ai.

Cada lote coge `--tam` artistas de correcciones/cola_revision.txt (los que ha
tocado 3_merge_resumenes.py al incorporar podcasts nuevos) y guarda las
propuestas de Claude en correcciones/lotes/lote_NNNN.txt. Después se revisan
(aceptar / editar / rechazar) en el editor web, pestaña 🤖 Lotes.

Uso:
    python3 scripts/limpieza/revisar_lote.py --lotes 3        # prepara 3 lotes (prompts en correcciones/lotes/)
    python3 scripts/limpieza/revisar_lote.py --esperando      # lotes preparados sin respuesta
    python3 scripts/limpieza/revisar_lote.py --importar 7 correcciones/lotes/lote_0007_respuesta.md
    python3 scripts/limpieza/revisar_lote.py --backend claude # opcional: llamar a `claude -p`
    python3 scripts/limpieza/revisar_lote.py --estado         # cómo va la cola
    python3 scripts/limpieza/revisar_lote.py --aplicar        # aplica lo aceptado sin abrir la web

Backends: sesion (por defecto: solo prepara), claude (CLI `claude -p`), api (SDK anthropic
+ ANTHROPIC_API_KEY, de pago). Variables: LOTE_TAM (25), LOTE_MODELO (opus, solo claude/api).
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lotes  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--lotes', type=int, default=1, help='cuántos lotes pedir (0 = ninguno)')
    ap.add_argument('--tam', type=int, default=lotes.TAM_DEFECTO, help='artistas por lote')
    ap.add_argument('--backend', default='sesion', choices=['sesion', 'manual', 'claude', 'api'])
    ap.add_argument('--modelo', default=lotes.MODELO_DEFECTO, help='opus | sonnet | haiku | id de modelo')
    ap.add_argument('--importar', nargs=2, metavar=('LOTE', 'FICHERO'),
                    help='importa la respuesta pegada de claude.ai para un lote manual')
    ap.add_argument('--estado', action='store_true', help='muestra el estado de la cola y los lotes')
    ap.add_argument('--esperando', action='store_true', help='lista los lotes preparados sin respuesta')
    ap.add_argument('--aplicar', action='store_true', help='aplica las propuestas ya aceptadas')
    ap.add_argument('--ver', type=int, metavar='LOTE', help='muestra las propuestas de un lote')
    ap.add_argument('--aceptar', nargs='+', metavar='X',
                    help='LOTE y los ids a aceptar (o "todas"): --aceptar 3 1 2 5')
    ap.add_argument('--rechazar', nargs='+', metavar='X', help='LOTE y los ids a rechazar')
    args = ap.parse_args()

    if args.estado:
        print('Cola:', lotes.estadisticas())
        for l in lotes.listar_lotes():
            c = {}
            for p in l['propuestas']:
                c[p['estado']] = c.get(p['estado'], 0) + 1
            print(f"  lote {l['id']:04d} {l['fecha']} {l['backend']:7} {l['estado']:20} {c}")
        return
    if args.ver:
        l = lotes.cargar_lote(args.ver)
        print(f"Lote {l['id']} ({l['estado']}) · artistas: {', '.join(l['artistas'])}")
        for p in l['propuestas']:
            print(f"  [{p['id']:>2}] {p['estado']:9} {p['linea']}" + (f"   # {p['motivo']}" if p['motivo'] else ''))
        return
    for opt, estado in ((args.aceptar, 'aceptada'), (args.rechazar, 'rechazada')):
        if opt:
            n = int(opt[0])
            l = lotes.cargar_lote(n)
            ids = [p['id'] for p in l['propuestas'] if p['estado'] == 'pendiente'] \
                if opt[1:] == ['todas'] else [int(x) for x in opt[1:]]
            for pid in ids:
                lotes.marcar_propuesta(n, pid, estado)
            print(f'Lote {n}: {len(ids)} propuestas {estado}s')
            return
    if args.esperando:
        for l in lotes.lotes_esperando():
            print(f"lote {l['id']:04d}  {lotes.ruta_prompt(l['id'])}  →  {lotes.ruta_respuesta(l['id'])}")
        return
    if args.importar:
        n, fichero = args.importar
        with open(fichero, encoding='utf-8') as f:
            l = lotes.importar_respuesta(int(n), f.read())
        print(f"Lote {l['id']}: {len(l['propuestas'])} propuestas importadas")
        return
    if args.aplicar:
        lotes.aplicar_aceptadas()
        return

    for i in range(args.lotes):
        try:
            lote = lotes.crear_lote(args.tam, args.backend, args.modelo)
        except Exception as e:
            print(f'Error en el lote: {e}')
            sys.exit(1)
        if lote is None:
            break
    print('Cola:', lotes.estadisticas())


if __name__ == '__main__':
    main()
