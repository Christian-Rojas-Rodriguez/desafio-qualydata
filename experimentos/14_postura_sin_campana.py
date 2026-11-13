"""¿Cuánto depende la postura de que haya una campaña detectada?

Repite la etapa de narrativas con la regla "el lado que empuja la campaña afirma"
apagada (solo LLM y marcadores) y compara el acierto de postura por narrativa.
Trabaja sobre copias de los lagos, en experimentos/cache/.

    python experimentos/14_postura_sin_campana.py
"""
import shutil
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, ".")
from qd import entrega, narrativas, postura  # noqa: E402
from qd.lago import Lago  # noqa: E402
from qd.validacion import puntuador  # noqa: E402

CACHE = Path("experimentos/cache/postura_sin_campana")
PARTES = [("practica", Path("lake/practica"), Path("datos/practica/verdad"))] + [
    (f"fold{i}", Path(f"lake/validacion/datos/fold{i}/train"), Path(f"salida/validacion/datos/fold{i}/train/verdad"))
    for i in range(5)]


def acierto(verdad: Path, ent: Path):
    return dict(duckdb.sql(f"""
        SELECT v.narrativa_id, round(avg((e.postura = v.postura)::int), 3)
        FROM read_csv('{verdad / 'comentarios.csv'}*', all_varchar=true) v
        JOIN read_csv('{ent / 'comentarios.csv'}', all_varchar=true) e USING (comentario_id)
        WHERE v.narrativa_id <> '' AND v.postura <> '' AND e.postura <> '' GROUP BY 1 ORDER BY 1""").fetchall())


def main():
    punt = puntuador()
    for nombre, lago_orig, verdad in PARTES:
        lago_dir = CACHE / nombre / "lago"
        if lago_dir.exists():
            shutil.rmtree(lago_dir)
        shutil.copytree(lago_orig, lago_dir)
        lago = Lago(lago_dir)
        filas = {}
        for regla, minimo in [("con campaña", postura.MIN_COORDINADOS), ("sin campaña", 10 ** 9)]:
            postura.MIN_COORDINADOS = minimo
            narrativas.correr(lago)
            ent = CACHE / nombre / regla.replace(" ", "_")
            entrega.correr(lago, ent, {})
            filas[regla] = (punt.score_narratives(verdad, ent)["postura_macro_f1"], acierto(verdad, ent))
            postura.MIN_COORDINADOS = 10
        print(f"\n{nombre}: postura macro-F1 con campaña={filas['con campaña'][0]:.3f}  "
              f"sin campaña={filas['sin campaña'][0]:.3f}")
        for n in filas["con campaña"][1]:
            a, b = filas["con campaña"][1][n], filas["sin campaña"][1].get(n)
            print(f"  {n}  {a:5.3f} -> {b:5.3f}" + ("   <-- cambia" if b is not None and abs(a - b) > 0.2 else ""))


if __name__ == "__main__":
    main()
