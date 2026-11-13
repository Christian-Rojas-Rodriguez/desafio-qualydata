"""Gold: cuentas coordinadas y operaciones.

Una ráfaga sola no prueba coordinación: lo que delata a una operación es que las
mismas cuentas coinciden una y otra vez, más de lo esperable por azar.

1. Densidad: para cada comentario, cuántos comentarios hay en la misma publicación
   dentro de ±W. Coincidir en una publicación viral es esperable; en una tranquila, no.
2. Pares: para cada par de cuentas, coincidencias observadas (publicaciones donde
   comentan a menos de W) contra las esperadas por su actividad y la densidad en que
   comentan. Sorpresa = -log10 P(Poisson >= observado).
3. Núcleos: componentes del grafo de pares muy sorprendentes (umbral tipo Bonferroni).
   Con miles de pares, el azar arma cadenas sueltas (A-B, B-C, C-D) de cuentas genuinas;
   una campaña es densa. Un componente es núcleo si al menos `tamano_minimo` de sus
   cuentas tienen `grado_nucleo` pares fuertes dentro de él (el 2-core del grafo).
4. Expansión: una cuenta se suma a un núcleo si comenta junto al grupo, o le responde,
   mucho más de lo esperable. Se repite hasta que no entra nadie.
"""
import math

import igraph as ig
import numpy as np
import pyarrow as pa
from scipy.stats import poisson

from .lago import Lago

# Umbrales tipo Bonferroni: -log10 p >= log10(cantidad de pruebas) + margen, así se
# ajustan solos al tamaño del set. El margen de pares es negativo porque además se
# exige un componente de `tamano_minimo` cuentas, algo que el azar casi no produce.
PARAMS = {
    "ventana_s": 1800,
    "margen_par": -2.0,
    "tamano_minimo": 4,
    "grado_nucleo": 2,
    "margen_union": 0.0,
    "rondas_expansion": 3,
}


def sorpresa(observado, esperado):
    """-log10 P(X >= observado) con X ~ Poisson(esperado)."""
    observado = np.asarray(observado, dtype=float)
    esperado = np.maximum(np.asarray(esperado, dtype=float), 1e-12)
    return -poisson.logsf(observado - 1, esperado) / math.log(10)


def pares(con, lago: Lago, p: dict):
    W = p["ventana_s"]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE com AS
        SELECT comentario_id, cuenta_id, publicacion_id, respuesta_a, epoch(ts) AS t,
               count(*) OVER (PARTITION BY publicacion_id ORDER BY epoch(ts)
                              RANGE BETWEEN {W} PRECEDING AND {W} FOLLOWING) AS densidad
        FROM {lago.leer('silver', 'comentarios')} WHERE cuenta_id IS NOT NULL AND ts IS NOT NULL
    """)
    n_total = con.execute("SELECT count(*) FROM com").fetchall()[0][0]
    con.execute("""CREATE OR REPLACE TEMP TABLE actividad AS
                   SELECT cuenta_id, count(*) AS n, sum(densidad) AS masa FROM com GROUP BY 1""")
    # Cada respuesta entre dos cuentas distintas, en ambos sentidos.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE interaccion AS
        WITH r AS (SELECT h.cuenta_id AS h, p.cuenta_id AS p
                   FROM com h JOIN com p ON p.comentario_id = h.respuesta_a WHERE h.cuenta_id <> p.cuenta_id)
        SELECT h AS x, p AS y FROM r UNION ALL SELECT p AS x, h AS y FROM r
    """)
    con.execute("CREATE OR REPLACE TEMP TABLE interacciones AS SELECT x AS cuenta_id, count(*) AS total "
                "FROM interaccion GROUP BY 1")
    df = con.execute(f"""
        WITH co AS (
            SELECT a.cuenta_id AS a, b.cuenta_id AS b, count(DISTINCT a.publicacion_id) AS k
            FROM com a JOIN com b ON a.publicacion_id = b.publicacion_id AND a.cuenta_id < b.cuenta_id
                                  AND abs(a.t - b.t) <= {W}
            GROUP BY 1, 2 HAVING count(DISTINCT a.publicacion_id) >= 2
        )
        SELECT co.a, co.b, co.k, (xb.n * xa.masa + xa.n * xb.masa) / (2.0 * {n_total}) AS esperado
        FROM co JOIN actividad xa ON xa.cuenta_id = co.a JOIN actividad xb ON xb.cuenta_id = co.b
    """).df()
    df["sorpresa"] = sorpresa(df["k"], df["esperado"])
    return df, n_total


def sincronia_con_grupo(con, miembros: set, n_total: int, W: int):
    """Para cada cuenta fuera del grupo: sorpresa de comentar junto al grupo y de responderle."""
    con.register("miembros", pa.table({"cuenta_id": sorted(miembros)}))
    g_total = con.execute("SELECT count(*) FROM com JOIN miembros USING (cuenta_id)").fetchall()[0][0]
    df = con.execute(f"""
        WITH afuera AS (SELECT * FROM com ANTI JOIN miembros USING (cuenta_id)),
        grupo AS (SELECT com.* FROM com SEMI JOIN miembros USING (cuenta_id)),
        cerca AS (
            SELECT DISTINCT x.comentario_id
            FROM afuera x JOIN grupo g ON g.publicacion_id = x.publicacion_id AND abs(g.t - x.t) <= {W}
        ),
        respuestas AS (
            SELECT i.x AS cuenta_id, count(*) AS r
            FROM interaccion i SEMI JOIN miembros m ON m.cuenta_id = i.y
            GROUP BY 1
        )
        SELECT x.cuenta_id,
               count(c.comentario_id) AS juntos,
               sum(1 - exp(-{g_total} * x.densidad / {n_total})) AS esperado_juntos,
               any_value(coalesce(r.r, 0)) AS respuestas,
               any_value(coalesce(i.total, 0)) * {g_total} / {n_total} AS esperado_respuestas
        FROM afuera x
        LEFT JOIN cerca c USING (comentario_id)
        LEFT JOIN respuestas r ON r.cuenta_id = x.cuenta_id
        LEFT JOIN interacciones i ON i.cuenta_id = x.cuenta_id
        GROUP BY x.cuenta_id HAVING count(c.comentario_id) > 0 OR any_value(r.r) > 0
    """).df()
    con.unregister("miembros")
    df["sorpresa"] = sorpresa(df["juntos"], df["esperado_juntos"]) + \
        np.where(df["respuestas"] > 0, sorpresa(df["respuestas"], df["esperado_respuestas"]), 0.0)
    return df


def detectar(con, lago: Lago, p: dict):
    """Núcleos y expansión. Devuelve (grupos, nucleos, pares fuertes, resumen)."""
    df, n_total = pares(con, lago, p)

    umbral_par = math.log10(max(len(df), 10)) + p["margen_par"]
    fuertes = df[df["sorpresa"] >= umbral_par]
    g = ig.Graph.TupleList(fuertes[["a", "b"]].itertuples(index=False), directed=False)
    densas = [c >= p["grado_nucleo"] for c in g.coreness()]
    nucleos = sorted((sorted(g.vs[i]["name"] for i in comp) for comp in g.connected_components()
                      if sum(densas[i] for i in comp) >= p["tamano_minimo"]), key=lambda c: (-len(c), c[0]))
    grupos = [set(c) for c in nucleos]

    # Cada cuenta activa se pone a prueba contra cada grupo.
    n_cuentas = con.execute("SELECT count(*) FROM actividad").fetchall()[0][0]
    umbral_union = math.log10(max(n_cuentas * max(len(grupos), 1), 10)) + p["margen_union"]
    for _ in range(p["rondas_expansion"]):
        asignadas = set().union(*grupos) if grupos else set()
        candidatos = {}
        for i, miembros in enumerate(grupos):
            s = sincronia_con_grupo(con, miembros, n_total, p["ventana_s"])
            for cuenta, valor in zip(s["cuenta_id"], s["sorpresa"]):
                if cuenta not in asignadas and valor >= umbral_union and valor > candidatos.get(cuenta, (0, -1))[1]:
                    candidatos[cuenta] = (i, valor)
        if not candidatos:
            break
        for cuenta, (i, _) in candidatos.items():
            grupos[i].add(cuenta)

    resumen = {"pares_evaluados": len(df), "umbral_par": round(umbral_par, 2), "umbral_union": round(umbral_union, 2),
               "pares_fuertes": len(fuertes), "grupos": len(grupos),
               "cuentas": sum(len(m) for m in grupos), "tamanos": [len(m) for m in grupos]}
    return grupos, nucleos, fuertes, resumen


def correr(lago: Lago, p: dict = None) -> dict:
    p = {**PARAMS, **(p or {})}
    con = lago.conectar()
    grupos, nucleos, fuertes, resumen = detectar(con, lago, p)
    filas = [{"cuenta_id": c, "grupo": f"g{i + 1:02d}", "nucleo": c in nucleos[i]}
             for i, miembros in enumerate(grupos) for c in sorted(miembros)]
    tabla = pa.Table.from_pylist(filas, schema=pa.schema([("cuenta_id", pa.string()), ("grupo", pa.string()),
                                                          ("nucleo", pa.bool_())]))
    con.register("t_grupos", tabla)
    lago.escribir(con, "gold", "cuentas_grupo", "SELECT * FROM t_grupos")
    con.register("t_pares", pa.Table.from_pandas(fuertes, preserve_index=False))
    lago.escribir(con, "gold", "pares_coordinados", "SELECT * FROM t_pares ORDER BY sorpresa DESC")
    con.close()
    return resumen
