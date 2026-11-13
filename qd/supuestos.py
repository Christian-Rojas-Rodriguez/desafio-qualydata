"""Gold: verifica en cada corrida lo que el pipeline da por cierto.

Los supuestos salen del EDA de la práctica (notebooks/01_eda_practica.ipynb). Ninguno
usa la verdad, así que también corren sobre el set final: si alguno no se cumple, el
resultado de la etapa que depende de él merece una mirada antes de entregarlo.
No frena el pipeline; avisa.
"""
import pyarrow as pa

from .lago import Lago


def chequeos(con, lago: Lago) -> list:
    sc, sx = lago.leer("silver", "comentarios"), lago.leer("silver", "textos")
    (n, resp, cruzan, antes, sin_padre, sin_fecha, sin_cuenta) = con.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE h.es_respuesta),
               count(*) FILTER (WHERE p.publicacion_id <> h.publicacion_id),
               count(*) FILTER (WHERE p.ts > h.ts),
               count(*) FILTER (WHERE h.es_respuesta AND p.comentario_id IS NULL),
               count(*) FILTER (WHERE h.ts IS NULL), count(*) FILTER (WHERE h.cuenta_id IS NULL)
        FROM {sc} h LEFT JOIN {sc} p ON p.comentario_id = h.respuesta_a
    """).fetchall()[0]
    textos = con.execute(f"SELECT count(*) FROM {sx}").fetchall()[0][0]
    filas = [
        ("respuestas que cruzan de publicación", cruzan, "0", cruzan == 0,
         "las respuestas heredan la narrativa del padre; la validación corta por publicación"),
        ("respuestas anteriores a su padre", antes, "0", antes == 0,
         "el orden temporal de la asignación y del origen"),
        ("% respuestas", round(100 * resp / max(n, 1), 1), ">= 5", resp >= 0.05 * n,
         "las narrativas se arman con el grafo de respuestas"),
        ("% respuestas con padre desconocido", round(100 * sin_padre / max(resp, 1), 1), "< 5",
         sin_padre < 0.05 * max(resp, 1), "grafo de respuestas incompleto"),
        ("textos únicos / comentarios", round(textos / max(n, 1), 2), "< 0.6", textos < 0.6 * n,
         "micro-clusters de plantillas; caché de embeddings"),
        ("% sin fecha", round(100 * sin_fecha / max(n, 1), 2), "< 1", sin_fecha < 0.01 * n,
         "coordinación por ventanas de tiempo y origen"),
        ("% sin cuenta", round(100 * sin_cuenta / max(n, 1), 2), "< 1", sin_cuenta < 0.01 * n,
         "coordinación por pares de cuentas"),
    ]
    gold = lago.raiz / "gold"
    if (gold / "comentarios_narrativa.parquet").exists():
        n_narr, ruido = con.execute(f"""
            SELECT count(DISTINCT narrativa) FILTER (WHERE narrativa <> ''), avg((narrativa = '')::int)
            FROM {lago.leer('gold', 'comentarios_narrativa')}""").fetchall()[0]
        filas += [
            ("narrativas encontradas", n_narr, "3 a 40", 3 <= n_narr <= 40, "resolución de Leiden"),
            ("% comentarios como ruido", round(100 * ruido, 1), "5 a 40", 0.05 <= ruido <= 0.40,
             "umbral de participación de los micro-clusters"),
        ]
    if (gold / "cuentas_grupo.parquet").exists():
        marcadas = con.execute(f"SELECT count(*) FROM {lago.leer('gold', 'cuentas_grupo')}").fetchall()[0][0]
        cuentas = con.execute(f"SELECT count(DISTINCT cuenta_id) FROM {sc}").fetchall()[0][0]
        filas.append(("% cuentas marcadas como coordinadas", round(100 * marcadas / max(cuentas, 1), 2), "< 3",
                      marcadas < 0.03 * cuentas, "precisión de coordinación: las campañas son pocas cuentas"))
    return [{"chequeo": c, "valor": float(v), "esperado": e, "ok": bool(ok), "depende": d} for c, v, e, ok, d in filas]


def correr(lago: Lago) -> dict:
    con = lago.conectar()
    filas = chequeos(con, lago)
    con.register("t_supuestos", pa.Table.from_pylist(filas))
    lago.escribir(con, "gold", "supuestos", "SELECT * FROM t_supuestos")
    con.close()
    for f in filas:
        if not f["ok"]:
            print(f"  AVISO supuesto: {f['chequeo']} = {f['valor']} (esperado {f['esperado']}); afecta: {f['depende']}")
    return {"chequeos": len(filas), "fallan": [f["chequeo"] for f in filas if not f["ok"]]}
