"""¿Qué cuentas genuinas marca coordinación en los subconjuntos y por qué entran?

Corre solo la etapa de coordinación (sin escribir en los lagos) sobre cada parte de la
validación y la compara con su verdad. Las decisiones se toman con las partes train.

    python experimentos/13_coordinacion_cv.py ["{'margen_par': -1.0}"] [--detalle]
"""
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, ".")
from qd import coordinacion  # noqa: E402
from qd.lago import Lago  # noqa: E402
from qd.validacion import puntuador  # noqa: E402

LAGOS = Path("lake/validacion")
SALIDA = Path("salida/validacion")


def partes():
    for modo in ("datos", "tema"):
        for fold in sorted((LAGOS / modo).iterdir()):
            for parte in ("train", "test"):
                if (fold / parte / "gold").exists():
                    yield modo, fold.name, parte


def evaluar(args):
    (modo, fold, parte), params = args
    lago = Lago(LAGOS / modo / fold / parte)
    p = {**coordinacion.PARAMS, **params}
    con = lago.conectar()
    con.execute("SET enable_progress_bar = false")
    grupos, nucleos, _, resumen = coordinacion.detectar(con, lago, p)
    actividad = dict(con.execute("SELECT cuenta_id, n FROM actividad").fetchall())
    con.close()
    verdad_dir = SALIDA / modo / fold / parte / "verdad"
    punt = puntuador()
    verdad = {r["cuenta_id"]: r["campana_id"] for r in punt.open_csv(verdad_dir / "cuentas.csv")}
    with tempfile.TemporaryDirectory() as tmp:
        with open(Path(tmp) / "cuentas.csv", "w") as f:
            f.write("cuenta_id,grupo\n")
            for i, m in enumerate(grupos):
                f.writelines(f"{c},g{i + 1:02d}\n" for c in m)
        c = punt.score_coordination(verdad_dir, Path(tmp))
    detalle = []
    for i, m in enumerate(grupos):
        campanas = [verdad.get(u) or "-" for u in m]
        mayoria = max(set(campanas), key=campanas.count)
        detalle.append({"grupo": i + 1, "n": len(m), "nucleo": len(nucleos[i]), "mayoria": mayoria,
                        "genuinas_nucleo": sum(1 for u in nucleos[i] if not verdad.get(u)),
                        "genuinas_exp": sum(1 for u in m - set(nucleos[i]) if not verdad.get(u)),
                        "act_mediana": sorted(actividad.get(u, 0) for u in m)[len(m) // 2]})
    return {"modo": modo, "fold": fold, "parte": parte, "pts": c["puntos"], "p": round(c["precision"], 3),
            "r": round(c["recall"], 3), "f1": round(c["f1"], 3), "b3": round(c["grupos_bcubed_f1"], 3),
            "campanas": len({v for v in verdad.values() if v}),
            "genuinas": sum(d["genuinas_nucleo"] + d["genuinas_exp"] for d in detalle),
            "umbral_par": resumen["umbral_par"], "umbral_union": resumen["umbral_union"], "grupos": detalle}


def main():
    params = eval(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else {}
    with ProcessPoolExecutor(4) as ex:
        filas = list(ex.map(evaluar, [(x, params) for x in partes()]))
    for parte in ("train", "test"):
        sel = [f for f in filas if f["parte"] == parte]
        print(f"\n{parte.upper()}  pts medio={sum(f['pts'] for f in sel) / len(sel):.2f}  "
              f"F1 medio={sum(f['f1'] for f in sel) / len(sel):.3f}  genuinas={sum(f['genuinas'] for f in sel)}")
        for f in sel:
            print(f"  {f['modo']:5} {f['fold']:9} pts={f['pts']:5.2f} P={f['p']:.2f} R={f['r']:.2f} "
                  f"B3={f['b3']:.2f} camp={f['campanas']} gen={f['genuinas']:2}  "
                  + " ".join(f"[{d['mayoria']} {d['n']}/{d['nucleo']}n g{d['genuinas_nucleo']}+{d['genuinas_exp']}]"
                             for d in f["grupos"]))
    if "--detalle" in sys.argv:
        Path("experimentos/cache").mkdir(exist_ok=True)
        Path("experimentos/cache/13_coordinacion_cv.json").write_text(json.dumps(filas, indent=1))


if __name__ == "__main__":
    main()
