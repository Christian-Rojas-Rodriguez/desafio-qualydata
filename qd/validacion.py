"""Validación cruzada sin fugas sobre un set con verdad (la práctica).

El pipeline no aprende de etiquetas: lo que se "entrena" son nuestras decisiones
(parámetros, reglas). Hay fuga si elegimos una decisión mirando las mismas
etiquetas con las que después reportamos. Por eso:

- La unidad de corte es la publicación: las respuestas nunca salen de su
  publicación, así que un hilo queda entero de un lado. Cortar por comentario
  partiría hilos y dejaría respuestas sin padre.
- Los folds se estratifican por tema, para que cada uno tenga todos los temas.
- Las cuentas que comentan en train y en test son las mismas personas; eso no es
  fuga porque el pipeline no ve etiquetas, pero por eso también se evalúa con
  temas ocultos (cada tema trae sus propias campañas).

Modos:
  etiquetas  5 folds 80/20: una sola corrida sobre todo el set (como el viernes) y
             las métricas se calculan aparte con las etiquetas de train y de test.
             Las decisiones se toman mirando train; test se reporta.
  datos      5 folds 80/20: el pipeline corre por separado sobre el 80% y sobre el
             20% de las publicaciones, con parámetros congelados. Prueba que los
             umbrales se adapten a otro tamaño.
  tema       un tema oculto por fold: el pipeline corre solo sobre ese tema.
             Es lo más parecido a "el final trae otros temas y campañas".

    python -m qd.validacion --modo etiquetas
    python -m qd.validacion --modo datos --folds 5
    python -m qd.validacion --modo tema
"""
import argparse
import importlib.util
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent


def puntuador():
    spec = importlib.util.spec_from_file_location("puntuar", RAIZ / "evaluacion" / "puntuar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def conectar(datos: Path):
    con = duckdb.connect()
    v = datos / "verdad"
    for nombre, ruta in [("c", datos / "comentarios.csv.gz"), ("cu", datos / "cuentas.csv.gz"),
                         ("p", datos / "publicaciones.csv.gz"), ("vc", v / "comentarios.csv.gz"),
                         ("vcu", v / "cuentas.csv.gz"), ("vn", v / "narrativas.csv"),
                         ("vca", v / "campanas.csv")]:
        con.execute(f"CREATE VIEW {nombre} AS SELECT * FROM read_csv('{ruta}', all_varchar=true, header=true)")
    return con


def publicaciones_por_tema(con) -> dict:
    """Tema de cada publicación (por mayoría de sus comentarios con narrativa)."""
    filas = con.execute("""
        SELECT c.publicacion_id, vn.tema, count(*) AS k
        FROM c JOIN vc USING (comentario_id) JOIN vn ON vn.narrativa_id = vc.narrativa_id
        GROUP BY 1, 2 ORDER BY 1, 3 DESC, 2
    """).fetchall()
    tema = {}
    for pub, t, _ in filas:
        tema.setdefault(pub, t)
    for (pub,) in con.execute("SELECT DISTINCT publicacion_id FROM p").fetchall():
        tema.setdefault(pub, "sin_tema")
    return tema


def folds_publicaciones(tema: dict, k: int, semilla: int) -> dict:
    """Fold de cada publicación, estratificado por tema."""
    azar = random.Random(semilla)
    fold = {}
    for t in sorted(set(tema.values())):
        pubs = sorted(p for p, x in tema.items() if x == t)
        azar.shuffle(pubs)
        for i, p in enumerate(pubs):
            fold[p] = i % k
    return fold


def folds_cuentas(con, k: int, semilla: int) -> dict:
    """Fold de cada cuenta, estratificado por campaña (para el modo etiquetas)."""
    azar = random.Random(semilla)
    filas = con.execute("SELECT cuenta_id, coalesce(campana_id, '') FROM vcu ORDER BY 1").fetchall()
    fold = {}
    for camp in sorted({c for _, c in filas}):
        cuentas = [u for u, c in filas if c == camp]
        azar.shuffle(cuentas)
        for i, u in enumerate(cuentas):
            fold[u] = i % k
    return fold


def escribir_verdad(con, destino: Path, subconjunto: bool):
    """Verdad restringida a las tablas temporales sel_com y sel_cuentas.

    Con `subconjunto` (el pipeline solo vio esa parte de los datos):
    - el origen real es el primer comentario de la narrativa dentro de la parte;
    - una cuenta de campaña cuenta como coordinada solo si en la parte comenta en
      la narrativa de su campaña. Las cuentas de campaña también comentan en otros
      temas como cobertura; si la parte no incluye su operación, no hay nada que
      detectar y se excluyen de la evaluación (ni acierto ni error).
    """
    destino.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT vc.* FROM vc SEMI JOIN sel_com USING (comentario_id) ORDER BY 1) "
                f"TO '{destino / 'comentarios.csv'}' (HEADER)")
    cuentas = "SELECT vcu.* FROM vcu SEMI JOIN sel_cuentas USING (cuenta_id)"
    if subconjunto:
        cuentas += """ WHERE vcu.campana_id IS NULL OR vcu.cuenta_id IN (
            SELECT s.cuenta_id FROM sel_com s JOIN vc USING (comentario_id) JOIN vcu x ON x.cuenta_id = s.cuenta_id
            JOIN vca ON vca.campana_id = x.campana_id AND vca.narrativa_id = vc.narrativa_id)"""
    con.execute(f"COPY ({cuentas} ORDER BY 1) TO '{destino / 'cuentas.csv'}' (HEADER)")
    origen = ("(SELECT min(c.fecha) FROM c JOIN vc USING (comentario_id) SEMI JOIN sel_com USING (comentario_id) "
              "WHERE vc.narrativa_id = vn.narrativa_id)") if subconjunto else "vn.fecha_origen"
    con.execute(f"""
        COPY (SELECT * REPLACE ({origen} AS fecha_origen) FROM vn
              WHERE narrativa_id IN (SELECT DISTINCT narrativa_id FROM vc SEMI JOIN sel_com USING (comentario_id)))
        TO '{destino / 'narrativas.csv'}' (HEADER)
    """)


def escribir_datos(con, origen: Path, destino: Path):
    """CSV crudos (con su suciedad) restringidos a las publicaciones de sel_pub."""
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, consulta in [
        ("publicaciones", "SELECT p.* FROM p SEMI JOIN sel_pub USING (publicacion_id)"),
        ("comentarios", "SELECT c.* FROM c SEMI JOIN sel_pub USING (publicacion_id)"),
        ("cuentas", "SELECT cu.* FROM cu SEMI JOIN sel_cuentas USING (cuenta_id)"),
    ]:
        con.execute(f"COPY ({consulta}) TO '{destino / (nombre + '.csv.gz')}' (HEADER, COMPRESSION gzip)")
    if (origen / "fuentes.csv").exists():
        shutil.copy(origen / "fuentes.csv", destino / "fuentes.csv")


def seleccionar(con, pubs: list):
    con.execute("CREATE OR REPLACE TEMP TABLE sel_pub (publicacion_id VARCHAR)")
    con.executemany("INSERT INTO sel_pub VALUES (?)", [(p,) for p in pubs])
    con.execute("CREATE OR REPLACE TEMP TABLE sel_com AS SELECT comentario_id, cuenta_id FROM c "
                "SEMI JOIN sel_pub USING (publicacion_id)")
    con.execute("CREATE OR REPLACE TEMP TABLE sel_cuentas AS SELECT DISTINCT cuenta_id FROM sel_com "
                "WHERE cuenta_id IS NOT NULL")


def correr_pipeline(datos: Path, entrega: Path, lago: Path) -> float:
    if lago.exists():
        shutil.rmtree(lago)
    t = time.time()
    env = {**os.environ, "QD_LLM": os.environ.get("QD_LLM", "mlx")}
    r = subprocess.run([sys.executable, "-m", "qd", "--datos", str(datos), "--entrega", str(entrega),
                        "--lago", str(lago)], cwd=RAIZ, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit(f"falló el pipeline sobre {datos}")
    return round(time.time() - t, 1)


def medir(punt, verdad: Path, entrega: Path) -> dict:
    n = punt.score_narratives(verdad, entrega)
    c = punt.score_coordination(verdad, entrega)
    # Diagnósticos que el puntaje oficial no muestra.
    reales = {r["narrativa_id"] for r in punt.open_csv(verdad / "narrativas.csv")}
    ids = {r["comentario_id"] for r in punt.open_csv(verdad / "comentarios.csv")}
    predichas = {r["narrativa"] for r in punt.open_csv(entrega / "comentarios.csv")
                 if r["comentario_id"] in ids and r["narrativa"].strip().lower() not in punt.EMPTY}
    verdad_cuentas = {r["cuenta_id"]: r["campana_id"] for r in punt.open_csv(verdad / "cuentas.csv")}
    marcadas = {r["cuenta_id"] for r in punt.open_csv(entrega / "cuentas.csv")
                if (r.get("grupo") or "").strip().lower() not in punt.EMPTY and r["cuenta_id"] in verdad_cuentas}
    return {
        "total": round(n["puntos"] + c["puntos"], 2), "narrativas_pts": n["puntos"], "coordinacion_pts": c["puntos"],
        "bcubed_f1": n["bcubed_f1"], "ruido_f1": n["ruido_f1"], "postura_f1": n["postura_macro_f1"],
        "origen": n["origen"], "cuentas_p": c["precision"], "cuentas_r": c["recall"], "cuentas_f1": c["f1"],
        "grupos_bcubed": c["grupos_bcubed_f1"],
        "narrativas_reales": len(reales), "narrativas_predichas": len(predichas),
        "campanas_reales": len({x for x in verdad_cuentas.values() if x}),
        "genuinas_marcadas": sum(1 for u in marcadas if not verdad_cuentas[u]),
    }


def resumir(filas: list, parte: str) -> dict:
    sel = [f for f in filas if f["parte"] == parte]
    claves = [k for k in sel[0] if isinstance(sel[0][k], (int, float)) and k != "fold"]
    return {k: (round(statistics.mean(f[k] for f in sel), 3),
                round(statistics.stdev(f[k] for f in sel), 3) if len(sel) > 1 else 0.0) for k in claves}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, default=RAIZ / "datos" / "practica")
    ap.add_argument("--modo", choices=["etiquetas", "datos", "tema"], required=True)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--entrega", type=Path, default=RAIZ / "salida" / "practica",
                    help="Corrida completa a evaluar en el modo etiquetas")
    ap.add_argument("--salida", type=Path, default=RAIZ / "salida" / "validacion")
    ap.add_argument("--sin-train", action="store_true", help="En datos/tema, no correr el pipeline sobre train")
    ap.add_argument("--solo-medir", action="store_true",
                    help="En datos/tema, no volver a correr: medir las entregas que ya están")
    args = ap.parse_args()

    punt = puntuador()
    con = conectar(args.datos)
    tema = publicaciones_por_tema(con)
    base = args.salida / args.modo
    filas = []

    if args.modo == "tema":
        particiones = [(t, [p for p, x in tema.items() if x == t], [p for p, x in tema.items() if x != t])
                       for t in sorted(set(tema.values())) if t != "sin_tema"]
    else:
        fold = folds_publicaciones(tema, args.folds, args.semilla)
        particiones = [(f"fold{i}", [p for p, x in fold.items() if x == i], [p for p, x in fold.items() if x != i])
                       for i in range(args.folds)]

    if args.modo == "etiquetas":
        f_cuentas = folds_cuentas(con, args.folds, args.semilla)
        for i, (nombre, test, train) in enumerate(particiones):
            for parte, pubs, cuentas in [("test", test, [u for u, x in f_cuentas.items() if x == i]),
                                         ("train", train, [u for u, x in f_cuentas.items() if x != i])]:
                seleccionar(con, pubs)
                con.execute("CREATE OR REPLACE TEMP TABLE sel_cuentas (cuenta_id VARCHAR)")
                con.executemany("INSERT INTO sel_cuentas VALUES (?)", [(u,) for u in cuentas])
                verdad = base / nombre / parte / "verdad"
                escribir_verdad(con, verdad, subconjunto=False)
                filas.append({"fold": nombre, "parte": parte, **medir(punt, verdad, args.entrega)})
                print(nombre, parte, filas[-1]["total"], flush=True)
    else:
        for nombre, test, train in particiones:
            for parte, pubs in [("test", test), ("train", train)]:
                if parte == "train" and args.sin_train:
                    continue
                seleccionar(con, pubs)
                carpeta = base / nombre / parte
                escribir_verdad(con, carpeta / "verdad", subconjunto=True)
                lago = RAIZ / "lake" / "validacion" / args.modo / nombre / parte
                if args.solo_medir:
                    costo = json.loads((carpeta / "entrega" / "costo.json").read_text(encoding="utf-8"))
                    segundos = costo["segundos"]
                else:
                    escribir_datos(con, args.datos, carpeta / "datos")
                    segundos = correr_pipeline(carpeta / "datos", carpeta / "entrega", lago)
                n_com = con.execute("SELECT count(*) FROM sel_com").fetchall()[0][0]
                filas.append({"fold": nombre, "parte": parte, "comentarios": n_com, "segundos": segundos,
                              **medir(punt, carpeta / "verdad", carpeta / "entrega")})
                print(nombre, parte, n_com, "comentarios", filas[-1]["total"], f"({segundos} s)", flush=True)

    resumen = {"modo": args.modo, "semilla": args.semilla, "folds": filas,
               "test": resumir(filas, "test")}
    if any(f["parte"] == "train" for f in filas):
        resumen["train"] = resumir(filas, "train")
    base.mkdir(parents=True, exist_ok=True)
    (base / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{args.modo}: media ± desvío")
    for parte in ("train", "test"):
        if parte in resumen:
            print(f"  {parte:<5} " + "  ".join(f"{k}={m}±{s}" for k, (m, s) in resumen[parte].items()
                                              if k in ("total", "bcubed_f1", "ruido_f1", "postura_f1", "origen",
                                                       "cuentas_f1", "grupos_bcubed", "genuinas_marcadas")))


if __name__ == "__main__":
    main()
