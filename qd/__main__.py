"""Pipeline QualyData: un comando de punta a punta.

    python -m qd --datos datos/practica --entrega salida/practica
    python -m qd --datos datos/final --entrega entrega
    python -m qd --datos datos/practica --hasta silver   # cortar en una etapa
"""
import argparse
import json
import platform
import time
from pathlib import Path

from . import bronze, coordinacion, embeddings, entrega, llm, narrativas, silver, supuestos
from .lago import Lago

ETAPAS = ["bronze", "silver", "embeddings", "coordinacion", "narrativas", "supuestos", "entrega"]


def hardware() -> str:
    import os
    memoria = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    return f"{platform.machine()} {platform.system()}, {os.cpu_count()} núcleos, {memoria:.0f} GB RAM, " \
           f"aceleración {embeddings.dispositivo()}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True, help="Carpeta con los CSV del set")
    ap.add_argument("--entrega", type=Path, default=Path("entrega"), help="Carpeta de salida de la entrega")
    ap.add_argument("--lago", type=Path, help="Destino de las capas (por defecto lake/<nombre del set>)")
    ap.add_argument("--hasta", choices=ETAPAS, default=ETAPAS[-1])
    args = ap.parse_args()
    lago = Lago(args.lago or Path("lake") / args.datos.name)

    tiempos = {}
    inicio = time.time()
    for etapa in ETAPAS[: ETAPAS.index(args.hasta) + 1]:
        t = time.time()
        if etapa == "bronze":
            print("bronze:", json.dumps(bronze.correr(args.datos, lago), ensure_ascii=False))
        elif etapa == "silver":
            resultado = silver.correr(lago)
            print("silver:", json.dumps(resultado["filas"]))
            for c in resultado["chequeos"]:
                print(f"  calidad  {c['tabla']:<14} {c['chequeo']:<34} {c['filas']}")
        elif etapa == "embeddings":
            print("embeddings:", json.dumps(embeddings.correr(lago)))
        elif etapa == "coordinacion":
            print("coordinacion:", json.dumps(coordinacion.correr(lago)))
        elif etapa == "narrativas":
            print("narrativas:", json.dumps(narrativas.correr(lago)))
        elif etapa == "supuestos":
            print("supuestos:", json.dumps(supuestos.correr(lago), ensure_ascii=False))
        elif etapa == "entrega":
            con = lago.conectar()
            n = con.execute(f"SELECT count(*) FROM {lago.leer('silver', 'comentarios')}").fetchall()[0][0]
            con.close()
            segundos = round(time.time() - inicio, 1)
            tokens = llm.USO["tokens_entrada"] + llm.USO["tokens_salida"]
            uso_llm = (f"LLM local {llm.USO['modelo']} ({llm.USO['llamadas']} llamadas, solo para elegir "
                       "el lado que afirma y titular cada narrativa)" if llm.USO["llamadas"] else "sin LLM")
            costo = {"comentarios_procesados": n, "segundos": segundos, "tokens_ia": tokens, "usd_ia": 0.0,
                     "usd_por_mil_comentarios": 0.0, "hardware": hardware(),
                     "almacenamiento": "DuckDB sobre Parquet, capas bronze/silver/gold",
                     "notas": f"embeddings locales ({embeddings.MODELO}); {uso_llm}", "etapas_segundos": tiempos}
            print("entrega:", json.dumps(entrega.correr(lago, args.entrega, costo)))
        tiempos[etapa] = round(time.time() - t, 2)
        print(f"  {etapa} en {tiempos[etapa]} s")
    lago.catalogar()
    (lago.raiz / "tiempos.json").write_text(json.dumps(tiempos, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
