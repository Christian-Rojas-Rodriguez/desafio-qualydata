"""Capa bronze: copia fiel de los archivos de origen en Parquet.

No se corrige nada. Todo queda como texto y se agregan columnas de trazabilidad
(_archivo, _fila, _hash, _ingesta) para poder reconstruir cualquier resultado.
Las líneas que el lector de CSV no puede interpretar van a bronze/rechazos_csv.
"""
from datetime import datetime, timezone
from pathlib import Path

from .lago import Lago

TABLAS = {  # tabla -> obligatoria
    "comentarios": True,
    "cuentas": True,
    "publicaciones": True,
    "fuentes": False,
}


def buscar_archivo(datos: Path, tabla: str):
    for patron in (f"{tabla}.csv.gz", f"{tabla}.csv", f"{tabla}.*"):
        hallados = sorted(p for p in datos.glob(patron) if p.is_file())
        if hallados:
            return hallados[0]
    return None


def correr(datos: Path, lago: Lago) -> dict:
    con = lago.conectar()
    ingesta = datetime.now(timezone.utc).isoformat(timespec="seconds")
    resumen = {}
    rechazos = []
    for tabla, obligatoria in TABLAS.items():
        archivo = buscar_archivo(datos, tabla)
        if archivo is None:
            if obligatoria:
                raise FileNotFoundError(f"Falta {tabla}.csv(.gz) en {datos}")
            resumen[tabla] = {"archivo": None, "filas": 0}
            continue
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE crudo AS
            SELECT * FROM read_csv('{archivo}', header = true, all_varchar = true,
                                   normalize_names = true, null_padding = true, parallel = false,
                                   store_rejects = true, rejects_table = 'rej_{tabla}',
                                   rejects_scan = 'scan_{tabla}')
        """)
        columnas = [c[0] for c in con.execute("DESCRIBE crudo").fetchall()]
        concat = ", ".join(f"coalesce(\"{c}\", '')" for c in columnas)
        lago.escribir(con, "bronze", tabla, f"""
            SELECT *,
                   '{archivo.name}' AS _archivo,
                   row_number() OVER () AS _fila,
                   md5(concat_ws('|', {concat})) AS _hash,
                   TIMESTAMPTZ '{ingesta}' AS _ingesta
            FROM crudo
        """)
        n = con.execute("SELECT count(*) FROM crudo").fetchall()[0][0]
        n_rej = con.execute(f"SELECT count(*) FROM rej_{tabla}").fetchall()[0][0]
        if n_rej:
            rechazos.append(f"""SELECT '{tabla}' AS tabla, line AS linea, error_type::VARCHAR AS tipo,
                                       error_message AS mensaje, csv_line AS contenido FROM rej_{tabla}""")
        resumen[tabla] = {"archivo": archivo.name, "filas": n, "lineas_ilegibles": n_rej}

    vacio = ("SELECT NULL::VARCHAR AS tabla, NULL::BIGINT AS linea, NULL::VARCHAR AS tipo, "
             "NULL::VARCHAR AS mensaje, NULL::VARCHAR AS contenido WHERE false")
    lago.escribir(con, "bronze", "rechazos_csv", " UNION ALL ".join(rechazos) or vacio)
    con.close()
    return resumen
