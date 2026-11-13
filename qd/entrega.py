"""Exporta gold a los cuatro archivos que pide el desafío."""
import json
from pathlib import Path

from . import huella
from .lago import Lago


def correr(lago: Lago, destino: Path, costo: dict) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    con = lago.conectar()
    con.execute(f"""COPY (SELECT comentario_id, narrativa, postura
                          FROM {lago.leer('gold', 'comentarios_narrativa')} ORDER BY comentario_id)
                    TO '{destino / 'comentarios.csv'}' (HEADER)""")
    con.execute(f"""COPY (SELECT narrativa, titulo, frases_clave,
                                 strftime(fecha_origen, '%Y-%m-%dT%H:%M:%S-03:00') AS fecha_origen
                          FROM {lago.leer('gold', 'narrativas')} ORDER BY narrativa)
                    TO '{destino / 'narrativas.csv'}' (HEADER)""")
    grupos = lago.ruta("gold", "cuentas_grupo")
    origen_grupos = (f"LEFT JOIN read_parquet('{grupos}') g USING (cuenta_id)" if grupos.exists()
                     else "LEFT JOIN (SELECT NULL::VARCHAR AS cuenta_id, NULL::VARCHAR AS grupo) g USING (cuenta_id)")
    con.execute(f"""COPY (SELECT c.cuenta_id, coalesce(g.grupo, '') AS grupo
                          FROM {lago.leer('silver', 'cuentas')} c {origen_grupos} ORDER BY 1)
                    TO '{destino / 'cuentas.csv'}' (HEADER)""")
    # La huella de las salidas va en costo.json: `python -m qd.huella` la verifica re-corriendo.
    costo = {**costo, "salidas_sha256": huella.salidas(destino)}
    (destino / "costo.json").write_text(json.dumps(costo, ensure_ascii=False, indent=2), encoding="utf-8")
    con.close()
    return {"destino": str(destino)}
