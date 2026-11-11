"""Ubicación de las capas del lago y conexión a DuckDB.

lake/<escenario>/
    bronze/<tabla>.parquet   datos tal cual llegaron + trazabilidad
    silver/<tabla>.parquet   datos tipados, limpios y validados
    gold/<tabla>.parquet     features y resultados del modelo
    catalogo.duckdb          vistas bronze.*, silver.*, gold.* sobre los Parquet
"""
from pathlib import Path

import duckdb

CAPAS = ("bronze", "silver", "gold")
ZONA = "America/Argentina/Buenos_Aires"


class Lago:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        for capa in CAPAS:
            (self.raiz / capa).mkdir(parents=True, exist_ok=True)

    def ruta(self, capa: str, tabla: str) -> Path:
        return self.raiz / capa / f"{tabla}.parquet"

    def conectar(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        con.execute(f"SET TimeZone = '{ZONA}'")
        return con

    def escribir(self, con, capa: str, tabla: str, consulta: str):
        destino = self.ruta(capa, tabla)
        con.execute(f"COPY ({consulta}) TO '{destino}' (FORMAT parquet, COMPRESSION zstd)")
        return destino

    def leer(self, capa: str, tabla: str) -> str:
        """Expresión FROM para usar dentro de una consulta."""
        return f"read_parquet('{self.ruta(capa, tabla)}')"

    def catalogar(self):
        """Vistas por capa en un archivo DuckDB, para explorar con cualquier cliente."""
        con = duckdb.connect(str(self.raiz / "catalogo.duckdb"))
        for capa in CAPAS:
            con.execute(f"CREATE SCHEMA IF NOT EXISTS {capa}")
            for archivo in sorted((self.raiz / capa).glob("*.parquet")):
                con.execute(f"CREATE OR REPLACE VIEW {capa}.{archivo.stem} AS "
                            f"SELECT * FROM read_parquet('{archivo.resolve()}')")
        con.close()
