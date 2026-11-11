"""Pipeline QualyData: un comando de punta a punta.

    python -m qd --datos datos/practica                 # todas las capas disponibles
    python -m qd --datos datos/practica --hasta silver  # cortar en una capa
"""
import argparse
import json
import time
from pathlib import Path

from . import bronze, silver
from .lago import Lago

ETAPAS = ["bronze", "silver"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True, help="Carpeta con los CSV del set")
    ap.add_argument("--lago", type=Path, help="Destino de las capas (por defecto lake/<nombre del set>)")
    ap.add_argument("--hasta", choices=ETAPAS, default=ETAPAS[-1])
    args = ap.parse_args()
    lago = Lago(args.lago or Path("lake") / args.datos.name)

    tiempos = {}
    for etapa in ETAPAS[: ETAPAS.index(args.hasta) + 1]:
        t = time.time()
        if etapa == "bronze":
            resultado = bronze.correr(args.datos, lago)
            print("bronze:", json.dumps(resultado, ensure_ascii=False))
        elif etapa == "silver":
            resultado = silver.correr(lago)
            print("silver:", json.dumps(resultado["filas"]))
            for c in resultado["chequeos"]:
                print(f"  calidad  {c['tabla']:<14} {c['chequeo']:<34} {c['filas']}")
        tiempos[etapa] = round(time.time() - t, 2)
        print(f"  {etapa} en {tiempos[etapa]} s")
    lago.catalogar()
    (lago.raiz / "tiempos.json").write_text(json.dumps(tiempos, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
