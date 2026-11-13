"""¿Cómo decidir qué lado afirma cuando las dos lecturas del LLM no coinciden?

Hoy, si el LLM elige "A" en las dos lecturas invertidas (sesgo de posición), deciden los
marcadores de refutación, que aciertan como una moneda. Alternativa: leer la probabilidad
que el modelo da a "A" y "B" en cada lectura y sumar las dos, así el sesgo de posición se
cancela y siempre hay una respuesta.

1. Junta los dos lados de cada narrativa (regla de campaña apagada, para ver todas) en la
   práctica, los 5 train y el train del corte temporal, con el lado verdadero.
2. Compara los desempates sobre esos lados.

    python experimentos/15_desempate_postura.py [--solo-evaluar]
"""
import json
import shutil
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, ".")
from qd import llm, narrativas, postura  # noqa: E402
from qd.lago import Lago  # noqa: E402

CACHE = Path("experimentos/cache/desempate_postura")
PARTES = [("practica", Path("lake/practica"), Path("datos/practica/verdad"))] + [
    (f"fold{i}", Path(f"lake/validacion/datos/fold{i}/train"), Path(f"salida/validacion/datos/fold{i}/train/verdad"))
    for i in range(5)] + [
    ("dias", Path("lake/validacion/dias/corte/train"), Path("salida/validacion/dias/corte/train/verdad"))]


def juntar():
    casos = []
    original = postura.elegir_lado
    for nombre, lago_orig, verdad in PARTES:
        lago_dir = CACHE / nombre
        if lago_dir.exists():
            shutil.rmtree(lago_dir)
        shutil.copytree(lago_orig, lago_dir)
        vistos = []

        def espiar(l0, l1):
            apoya, info = original(l0, l1)
            vistos.append((l0, l1, apoya, info["metodo"]))
            return apoya, {**info, "metodo": f"{info['metodo']}#{len(vistos) - 1}"}

        postura.elegir_lado, postura.MIN_COORDINADOS = espiar, 10 ** 9
        narrativas.correr(Lago(lago_dir))
        postura.elegir_lado, postura.MIN_COORDINADOS = original, 10
        gold = lago_dir / "gold"
        filas = duckdb.sql(f"""
            SELECT n.narrativa, n.metodo_postura, avg((e.postura = v.postura)::int), count(*)
            FROM read_parquet('{gold / 'comentarios_narrativa.parquet'}') e
            JOIN read_parquet('{gold / 'narrativas.parquet'}') n USING (narrativa)
            JOIN read_csv('{verdad / 'comentarios.csv'}*', all_varchar=true) v USING (comentario_id)
            WHERE v.postura <> '' AND e.postura <> '' GROUP BY 1, 2 ORDER BY 1""").fetchall()
        for narr, metodo, acc, n in filas:
            l0, l1, apoya, _ = vistos[int(metodo.split("#")[1])]
            casos.append({"parte": nombre, "narrativa": narr, "n": n, "acierto": acc, "metodo_hoy": metodo.split("#")[0],
                          "verdad": apoya if acc >= 0.5 else 1 - apoya, "coordinados": [l0["coordinados"], l1["coordinados"]],
                          "lados": [{k: l[k] for k in ("limpio", "norm")} for l in (l0, l1)]})
    (CACHE / "casos.json").write_text(json.dumps(casos, ensure_ascii=False))
    return casos


def prob_a(a, b):
    """P("A") / (P("A") + P("B")) con el JSON de respuesta ya empezado."""
    import mlx.core as mx
    if llm._modelo is None:
        from mlx_lm import load
        llm._modelo = load(llm.MODELO_MLX)
    modelo, tok = llm._modelo
    entrada = tok.apply_chat_template([{"role": "user", "content": llm.PROMPT.format(a=llm._muestra(a), b=llm._muestra(b))}],
                                      add_generation_prompt=True, tokenize=False) + '{"afirmacion": "'
    logits = modelo(mx.array([tok.encode(entrada)]))[0, -1]
    ia, ib = tok.encode('"A')[-1], tok.encode('"B')[-1]
    pa, pb = mx.softmax(logits[mx.array([ia, ib])].astype(mx.float32)).tolist()
    return pa


def evaluar(casos):
    filas = []
    for c in casos:
        l0, l1 = c["lados"]
        if not l0["limpio"] or not l1["limpio"]:
            continue
        lectura = llm.elegir_afirmacion(l0["limpio"], l1["limpio"])
        p1, p2 = prob_a(l0["limpio"], l1["limpio"]), prob_a(l1["limpio"], l0["limpio"])
        r0, r1 = postura.tasa_refutacion(l0["norm"]), postura.tasa_refutacion(l1["norm"])
        c0, c1 = c["coordinados"]
        campana = (0 if c0 > c1 else 1) if max(c0, c1) >= 10 and max(c0, c1) >= 0.8 * (c0 + c1) else None
        filas.append({**{k: c[k] for k in ("parte", "narrativa", "n", "verdad")},
                      "campana": campana, "lectura": None if lectura is None else lectura["lado"],
                      "marcadores": 0 if r0 <= r1 else 1, "p1": p1, "p2": p2,
                      "prob": 0 if p1 + (1 - p2) >= 1 else 1})
    (CACHE / "evaluacion.json").write_text(json.dumps(filas, ensure_ascii=False))
    reglas = {
        "hoy (campaña > lectura > marcadores)": lambda f: f["campana"] if f["campana"] is not None
        else f["lectura"] if f["lectura"] is not None else f["marcadores"],
        "sin campaña: lectura > marcadores": lambda f: f["lectura"] if f["lectura"] is not None else f["marcadores"],
        "sin campaña: lectura > prob": lambda f: f["lectura"] if f["lectura"] is not None else f["prob"],
        "sin campaña: prob": lambda f: f["prob"],
        "campaña > lectura > prob": lambda f: f["campana"] if f["campana"] is not None
        else f["lectura"] if f["lectura"] is not None else f["prob"],
        "campaña > prob": lambda f: f["campana"] if f["campana"] is not None else f["prob"],
    }
    print(f"\n{len(filas)} decisiones; la lectura no decide en {sum(f['lectura'] is None for f in filas)}")
    print(f"{'parte':9} {'narr':5} {'n':>5} verdad camp lect marc  p(A|0 1º) p(A|1 1º) prob")
    for f in filas:
        print(f"{f['parte']:9} {f['narrativa']:5} {f['n']:5} {f['verdad']:6} {str(f['campana']):4} {str(f['lectura']):4} "
              f"{f['marcadores']:4}  {f['p1']:9.3f} {f['p2']:9.3f} {f['prob']:4}")
    for nombre, regla in reglas.items():
        ok = [regla(f) == f["verdad"] for f in filas]
        pond = sum(f["n"] for f, o in zip(filas, ok) if o) / sum(f["n"] for f in filas)
        indecisas = [o for f, o in zip(filas, ok) if f["lectura"] is None]
        print(f"{nombre:40} aciertos {sum(ok)}/{len(ok)}  ponderado {pond:.3f}  "
              f"en las que la lectura no decide {sum(indecisas)}/{len(indecisas)}")


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    casos = json.loads((CACHE / "casos.json").read_text()) if "--solo-evaluar" in sys.argv else juntar()
    evaluar(casos)
