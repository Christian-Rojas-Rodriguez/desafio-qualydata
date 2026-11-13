"""Página de resultados: qué circula, desde cuándo y quién lo empuja.

Lee las capas gold y silver de un lago y escribe un HTML autocontenido (los datos van
adentro; el diseño está en qd/tablero.html). No toca la entrega.

    python -m qd.tablero --lago lake/final --salida docs/resultados.html
"""
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .lago import Lago

PLANTILLA = Path(__file__).with_name("tablero.html")
BIN_H = 6                # resolución de las series de tiempo
SIMILITUD_TEMA = 0.3     # coseno entre narrativas (por publicaciones compartidas) para el mismo tema
PALABRAS_VACIAS = set("para por con los las del una que sus más mas tras sobre desde entre ante sin este esta "
                      "como pero piden dice dicen nuevo nueva hoy ayer".split())


def temas(narr_pub: dict, titulares: dict) -> list:
    """Agrupa narrativas que se discuten en las mismas publicaciones y nombra cada tema
    con las palabras más propias de los titulares de esas publicaciones."""
    ns = sorted(narr_pub)
    pubs = sorted({p for d in narr_pub.values() for p in d})
    M = np.zeros((len(ns), len(pubs)))
    for i, n in enumerate(ns):
        for p, c in narr_pub[n].items():
            M[i, pubs.index(p)] = c
    M /= np.linalg.norm(M, axis=1, keepdims=True)
    S = M @ M.T
    grupo = list(range(len(ns)))

    def raiz(i):
        while grupo[i] != i:
            i = grupo[i]
        return i
    for i in range(len(ns)):
        for j in range(i + 1, len(ns)):
            if S[i, j] >= SIMILITUD_TEMA:
                grupo[raiz(j)] = raiz(i)
    por_tema = defaultdict(list)
    for i, n in enumerate(ns):
        por_tema[raiz(i)].append(n)
    lista = sorted(por_tema.values(), key=lambda g: -sum(sum(narr_pub[n].values()) for n in g))

    def palabras(texto):
        return {w for w in re.findall(r"[a-záéíóúñü]+", texto.lower()) if len(w) > 3 and w not in PALABRAS_VACIAS}
    bolsas = []
    for g in lista:
        cuenta = Counter()
        for n in g:
            for p, c in narr_pub[n].items():
                for w in palabras(titulares.get(p, "")):
                    cuenta[w] += c
        bolsas.append(cuenta)
    df = Counter(w for b in bolsas for w in b)
    salida = []
    for g, b in zip(lista, bolsas):
        puntaje = {w: c * math.log((1 + len(bolsas)) / df[w]) for w, c in b.items()}
        top = [w for w, _ in sorted(puntaje.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
        salida.append({"palabras": top, "narrativas": sorted(g, key=lambda n: -sum(narr_pub[n].values()))})
    return salida


def grafo(con, lago: Lago, ancho=984, alto_grupos=300, alto_sueltos=84) -> dict:
    """Pares que superan el umbral de sorpresa, con posiciones ya calculadas (semilla fija).
    Arriba, una caja por operación; abajo, las cadenas sueltas que no llegan a ser un núcleo."""
    import random

    import igraph as ig
    pares = con.execute(f"SELECT a, b, k, esperado FROM {lago.leer('gold', 'pares_coordinados')}").fetchall()
    grupo = {c: (g, n) for c, g, n in con.execute(
        f"SELECT cuenta_id, grupo, nucleo FROM {lago.leer('gold', 'cuentas_grupo')}").fetchall()}
    cuentas = sorted({c for a, b, *_ in pares for c in (a, b)} | set(grupo))
    lista = ",".join(f"'{c}'" for c in cuentas)
    info = {c: (n, e) for c, n, e in con.execute(f"""
        SELECT c.cuenta_id, count(*), any_value(u.antiguedad_dias) FROM {lago.leer('silver', 'comentarios')} c
        LEFT JOIN {lago.leer('silver', 'cuentas')} u USING (cuenta_id) WHERE c.cuenta_id IN ({lista}) GROUP BY 1""").fetchall()}

    def ubicar(nodos, aristas, x0, y0, w, h, algoritmo, borde=12):
        g = ig.Graph(n=len(nodos), edges=[(nodos.index(a), nodos.index(b)) for a, b, _ in aristas])
        random.seed(0)
        xy = np.array(g.layout(algoritmo).coords) if len(nodos) > 1 else np.zeros((1, 2))
        rango = np.maximum(xy.max(0) - xy.min(0), 1e-9)
        xy = (xy - xy.min(0)) / rango
        return [{"id": c, "x": round(x0 + borde + xy[i, 0] * (w - 2 * borde), 1),
                 "y": round(y0 + borde + xy[i, 1] * (h - 2 * borde), 1),
                 "n": info.get(c, (0, None))[0], "edad": info.get(c, (0, None))[1]} for i, c in enumerate(nodos)]

    cajas, margen = [], 18
    ids_grupo = sorted({g for g, _ in grupo.values()})
    pesos = [math.sqrt(sum(1 for v in grupo.values() if v[0] == g)) for g in ids_grupo]
    x = 0.0
    for g, peso in zip(ids_grupo, pesos):
        w = (ancho - margen * (len(ids_grupo) - 1)) * peso / sum(pesos)
        nodos = sorted(c for c, v in grupo.items() if v[0] == g)
        aristas = [(a, b, k) for a, b, k, _ in pares if a in nodos and b in nodos]
        puntos = ubicar(nodos, aristas, x, 26, w, alto_grupos - 26, "fr")
        for q in puntos:
            q["nucleo"] = bool(grupo[q["id"]][1])
        pos = {q["id"]: i for i, q in enumerate(puntos)}
        cajas.append({"grupo": g, "x": round(x, 1), "w": round(w, 1), "nodos": puntos,
                      "aristas": [[pos[a], pos[b], k] for a, b, k in aristas]})
        x += w + margen
    sueltas = [(a, b, k) for a, b, k, _ in pares if a not in grupo and b not in grupo]
    nodos = sorted({c for a, b, _ in sueltas for c in (a, b)})
    gs = ig.Graph(n=len(nodos), edges=[(nodos.index(a), nodos.index(b)) for a, b, _ in sueltas])
    comps = sorted(gs.connected_components(), key=lambda c: (-len(c), nodos[c[0]]))
    puntos, x, paso = [], 0.0, ancho / max(sum(len(c) for c in comps), 1)
    for comp in comps:
        sub = [nodos[i] for i in comp]
        w = paso * len(sub)
        puntos += ubicar(sub, [(a, b, k) for a, b, k in sueltas if a in sub], x, alto_grupos + 30, w, alto_sueltos - 30, "kk", 5)
        x += w
    pos = {q["id"]: i for i, q in enumerate(puntos)}
    return {"ancho": ancho, "alto": alto_grupos + alto_sueltos, "corte": alto_grupos, "cajas": cajas,
            "sueltos": {"nodos": puntos, "aristas": [[pos[a], pos[b], k] for a, b, k in sueltas],
                        "componentes": len(comps), "mayor": max((len(c) for c in comps), default=0)}}


def datos(lago: Lago, entrega: Path) -> dict:
    con = lago.conectar()
    sc, cn = lago.leer("silver", "comentarios"), lago.leer("gold", "comentarios_narrativa")
    inicio, fin, n_com = con.execute(
        f"SELECT epoch(date_trunc('day', min(ts))), epoch(max(ts)), count(*) FROM {sc}").fetchall()[0]
    n_bins = math.ceil((fin - inicio) / (BIN_H * 3600))

    narr = con.execute(f"""SELECT narrativa, titulo, frases_clave, epoch(fecha_origen), comentarios, apoya, rechaza,
                                  metodo_postura FROM {lago.leer('gold', 'narrativas')} ORDER BY narrativa""").fetchall()
    series = defaultdict(lambda: {"apoya": [0] * n_bins, "rechaza": [0] * n_bins})
    for n, post, b, c in con.execute(f"""
            SELECT e.narrativa, e.postura, floor((epoch(c.ts) - {inicio}) / {BIN_H * 3600})::INT, count(*)
            FROM {cn} e JOIN {sc} c USING (comentario_id) WHERE e.narrativa <> '' GROUP BY ALL""").fetchall():
        if post in ("apoya", "rechaza") and 0 <= b < n_bins:
            series[n][post][b] = c
    narr_pub = defaultdict(dict)
    for n, p, c in con.execute(f"""SELECT e.narrativa, c.publicacion_id, count(*) FROM {cn} e JOIN {sc} c
                                   USING (comentario_id) WHERE e.narrativa <> '' GROUP BY ALL""").fetchall():
        narr_pub[n][p] = c
    titulares = dict(con.execute(f"SELECT publicacion_id, coalesce(titular, '') FROM {lago.leer('silver', 'publicaciones')}").fetchall())
    ruido = con.execute(f"SELECT count(*) FROM {cn} WHERE narrativa = ''").fetchall()[0][0]

    narrativas = [{"id": n, "titulo": t, "frases": f.split("|") if f else [], "origen": o, "n": tot,
                   "apoya": a, "rechaza": r, "metodo": m, "emergente": o >= inicio + 86400,
                   "serie": series[n]} for n, t, f, o, tot, a, r, m in narr]

    # Operaciones: cada cuenta es una fila de puntos (sus comentarios en el tiempo). Para
    # comparar, la misma cantidad de cuentas genuinas con actividad parecida (semilla fija).
    grupos = []
    edad_genuina = con.execute(f"""SELECT median(antiguedad_dias) FROM {lago.leer('silver', 'cuentas')}
        WHERE cuenta_id NOT IN (SELECT cuenta_id FROM {lago.leer('gold', 'cuentas_grupo')})""").fetchall()[0][0]
    actividad = dict(con.execute(f"SELECT cuenta_id, count(*) FROM {sc} WHERE cuenta_id IS NOT NULL GROUP BY 1").fetchall())
    miembros = defaultdict(list)
    for c, g in con.execute(f"SELECT cuenta_id, grupo FROM {lago.leer('gold', 'cuentas_grupo')} ORDER BY 1").fetchall():
        miembros[g].append(c)
    marcadas = {c for m in miembros.values() for c in m}
    genuinas = sorted(c for c in actividad if c not in marcadas)
    rng = np.random.default_rng(0)

    def filas(cuentas):
        ts = defaultdict(list)
        lista = ",".join(f"'{c}'" for c in cuentas)
        for c, t in con.execute(f"SELECT cuenta_id, epoch(ts) FROM {sc} WHERE cuenta_id IN ({lista}) ORDER BY ts").fetchall():
            ts[c].append(round(t))
        return sorted(ts.values(), key=lambda v: v[0])

    for g in sorted(miembros):
        cuentas = miembros[g]
        lista = ",".join(f"'{c}'" for c in cuentas)
        empuja = con.execute(f"""SELECT e.narrativa, avg((e.postura = 'apoya')::INT), count(*) FROM {cn} e JOIN {sc} c
            USING (comentario_id) WHERE c.cuenta_id IN ({lista}) AND e.narrativa <> ''
            GROUP BY 1 ORDER BY 3 DESC LIMIT 1""").fetchall()[0]
        total = con.execute(f"SELECT count(*) FROM {sc} WHERE cuenta_id IN ({lista})").fetchall()[0]
        edad = con.execute(f"SELECT median(antiguedad_dias) FROM {lago.leer('silver', 'cuentas')} "
                           f"WHERE cuenta_id IN ({lista})").fetchall()[0][0]
        k, esperado = con.execute(f"""SELECT median(k), median(esperado) FROM {lago.leer('gold', 'pares_coordinados')}
            WHERE a IN ({lista}) AND b IN ({lista})""").fetchall()[0]
        lo, hi = min(actividad[c] for c in cuentas), max(actividad[c] for c in cuentas)
        candidatas = [c for c in genuinas if lo <= actividad[c] <= hi]
        control = list(rng.choice(candidatas, size=min(len(cuentas), len(candidatas)), replace=False))
        grupos.append({"id": g, "cuentas": len(cuentas), "comentarios": total[0], "edad_mediana": edad,
                       "narrativa": empuja[0], "apoya": empuja[1], "en_narrativa": empuja[2],
                       "k": k, "esperado": esperado, "filas": filas(cuentas), "control": filas(control)})
    red = grafo(con, lago)
    con.close()

    costo = json.loads((entrega / "costo.json").read_text(encoding="utf-8")) if (entrega / "costo.json").exists() else {}
    return {"inicio": inicio, "fin": fin, "bin_h": BIN_H, "comentarios": n_com, "ruido": ruido,
            "cuentas": len(actividad), "edad_genuina": edad_genuina, "narrativas": narrativas,
            "temas": temas(narr_pub, titulares), "grupos": grupos, "grafo": red,
            "costo": {k: costo.get(k) for k in ("segundos", "usd_ia", "tokens_ia", "codigo", "hardware")}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lago", type=Path, default=Path("lake/final"))
    ap.add_argument("--entrega", type=Path, default=Path("entrega"))
    ap.add_argument("--salida", type=Path, default=Path("docs/resultados.html"))
    args = ap.parse_args()
    d = datos(Lago(args.lago), args.entrega)
    html = PLANTILLA.read_text(encoding="utf-8").replace("/*DATOS*/null", json.dumps(d, ensure_ascii=False))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(html, encoding="utf-8")
    print(f"escrito {args.salida}")


if __name__ == "__main__":
    main()
