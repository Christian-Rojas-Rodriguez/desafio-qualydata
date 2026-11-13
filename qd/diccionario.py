"""Genera docs/datos.md: cada tabla del lago con sus filas, columnas y tipos.

    python -m qd.diccionario --lago lake/practica

Los tipos y las filas se leen del lago; las descripciones están acá abajo, así
que si una tabla cambia de columnas el documento se regenera sin quedar viejo.
"""
import argparse
from pathlib import Path

import duckdb

CAPAS = {
    "bronze": "Copia fiel de los CSV: todo como texto, más de dónde vino cada fila. Nunca se pierde nada.",
    "silver": "Datos limpios y tipados: fechas en hora argentina, números validados, texto normalizado, "
              "duplicados resueltos y cada problema anotado en `flags`.",
    "gold": "Resultados del análisis: narrativas, postura, coordinación. De acá sale la entrega.",
}

TABLAS = {
    "bronze/comentarios": "Comentarios tal cual llegan. `_archivo`, `_fila`, `_hash` e `_ingesta` permiten rastrear cada fila.",
    "bronze/cuentas": "Cuentas tal cual llegan.",
    "bronze/publicaciones": "Publicaciones tal cual llegan.",
    "bronze/fuentes": "Medios, radios, comunidades e instituciones.",
    "bronze/rechazos_csv": "Líneas que el lector de CSV no pudo interpretar (comillas rotas, columnas de más).",
    "silver/comentarios": "Un comentario por fila, limpio. Base de todo el análisis.",
    "silver/cuentas": "Cuentas con antigüedad calculada; incluye las que solo aparecen en comentarios (flag `sin_perfil`).",
    "silver/publicaciones": "Publicaciones con fecha tipada.",
    "silver/fuentes": "Fuentes limpias.",
    "silver/textos": "Un texto normalizado único por fila (58k textos para 200k comentarios: hay mucha repetición).",
    "silver/rechazos": "Filas descartadas en la deduplicación y por qué.",
    "silver/calidad": "Cuántas filas tienen cada problema de calidad.",
    "gold/embeddings": "Vector semántico (multilingual-e5-small, 384 dims) de cada texto único.",
    "gold/micro_clusters": "Grupos de textos casi iguales (Leiden sobre vecinos) y su tipo: narrativa, genérico o ruido.",
    "gold/comentarios_narrativa": "Narrativa y postura asignadas a cada comentario.",
    "gold/narrativas": "Una fila por narrativa: título, frases clave, origen, tamaño y cómo se decidió la postura.",
    "gold/cuentas_grupo": "Cuentas coordinadas y su operación; `nucleo` indica si entró por pares fuertes o por expansión.",
    "gold/supuestos": "Chequeos de lo que el pipeline da por cierto (salen del EDA); se recalculan en cada corrida, también sobre el set final.",
    "gold/pares_coordinados": "Pares de cuentas que coinciden más de lo esperable (k observado, esperado, sorpresa = -log10 p).",
}

COLUMNAS = {
    "ts": "Fecha y hora con zona horaria (America/Argentina/Buenos_Aires).",
    "texto_limpio": "Texto sin URLs, menciones ni emojis; hashtags separados en palabras.",
    "texto_norm": "Minúsculas, sin acentos (salvo ñ), sin signos, abreviaturas expandidas. Se usa para comparar.",
    "texto_id": "md5 de `texto_norm`: mismo texto normalizado, mismo id.",
    "flags": "Problemas de calidad de la fila (fecha imputada, cuenta desconocida, texto vacío...).",
    "es_respuesta": "Si `respuesta_a` apunta a otro comentario.",
    "tipo_cluster": "narrativa, generico (\"totalmente de acuerdo\") o ruido.",
    "sorpresa": "-log10 de la probabilidad de coincidir tantas veces por azar (Poisson).",
    "esperado": "Coincidencias esperables por azar según la actividad de las dos cuentas.",
    "k": "Publicaciones donde las dos cuentas comentaron a menos de 30 minutos.",
    "metodo_postura": "Cómo se decidió qué lado afirma: campaña, llm o marcadores.",
    "nucleo": "true si la cuenta entró por pares fuertes; false si se sumó por sincronía con el grupo.",
}


def generar(lago: Path) -> str:
    con = duckdb.connect()
    lineas = ["# Diccionario de datos", "",
              f"Generado con `python -m qd.diccionario --lago {lago}`. Filas del set de práctica.", "",
              "Todas las capas son Parquet (zstd) en `lake/<set>/<capa>/<tabla>.parquet`; "
              "`lake/<set>/catalogo.duckdb` las expone como vistas `bronze.*`, `silver.*` y `gold.*`.", ""]
    for capa, descripcion in CAPAS.items():
        lineas += [f"## {capa}", "", descripcion, ""]
        for ruta in sorted((lago / capa).glob("*.parquet")):
            nombre = f"{capa}/{ruta.stem}"
            filas = con.execute(f"SELECT count(*) FROM read_parquet('{ruta}')").fetchall()[0][0]
            cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{ruta}')").fetchall()
            lineas += [f"### `{nombre}` ({filas:,} filas)".replace(",", "."), "", TABLAS.get(nombre, ""), "",
                       "| Columna | Tipo | Descripción |", "|---|---|---|"]
            lineas += [f"| `{c[0]}` | {c[1]} | {COLUMNAS.get(c[0], '')} |" for c in cols]
            lineas.append("")
    return "\n".join(lineas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lago", type=Path, default=Path("lake/practica"))
    ap.add_argument("--salida", type=Path, default=Path("docs/datos.md"))
    args = ap.parse_args()
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(generar(args.lago), encoding="utf-8")
    print(f"escrito {args.salida}")


if __name__ == "__main__":
    main()
