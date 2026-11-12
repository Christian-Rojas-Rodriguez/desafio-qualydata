"""Capa silver: datos tipados, limpios y validados.

Principio: no se pierde ningún comentario que tenga id, porque la entrega debe
cubrirlos a todos. Los problemas se corrigen o imputan y quedan anotados en la
columna `flags`. Solo van a silver/rechazos las filas inutilizables (sin id o
duplicadas). silver/calidad resume cada validación con su conteo.
"""
import json

import pyarrow as pa

from . import texto
from .lago import Lago

ESQUEMA_ATRIBUTOS = pa.schema([
    ("texto_crudo", pa.string()), ("texto_limpio", pa.string()), ("texto_norm", pa.string()),
    ("n_tokens", pa.int32()), ("es_pregunta", pa.bool_()), ("hashtags", pa.list_(pa.string())),
    ("emojis", pa.list_(pa.string())), ("n_urls", pa.int32()), ("n_menciones", pa.int32()),
    ("prop_mayusculas", pa.float32()),
])

FORMATOS_FECHA = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                  "%d-%m-%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"]


def columnas(con, tabla_bronze: str) -> set:
    return {c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {tabla_bronze}").fetchall()}


def col(disponibles: set, nombre: str, vacio_es_nulo: bool = True) -> str:
    if nombre not in disponibles:
        return "NULL::VARCHAR"
    return f"nullif(trim(\"{nombre}\"), '')" if vacio_es_nulo else f"\"{nombre}\""


def fecha_sql(expr: str, solo_fecha: bool = False) -> str:
    """Interpreta ISO con o sin zona, formatos dd/mm/aaaa y epoch; fuera de 2000-2100 es inválida."""
    formatos = ", ".join(f"'{f}'" for f in FORMATOS_FECHA)
    parsed = f"""coalesce(
        try_cast({expr} AS TIMESTAMPTZ),
        try_strptime({expr}, [{formatos}])::TIMESTAMPTZ,
        CASE WHEN regexp_full_match({expr}, '\\d{{9,13}}(\\.\\d+)?') THEN
             to_timestamp(CASE WHEN try_cast({expr} AS DOUBLE) > 1e11 THEN try_cast({expr} AS DOUBLE) / 1000
                               ELSE try_cast({expr} AS DOUBLE) END) END)"""
    rango = f"CASE WHEN {parsed} BETWEEN TIMESTAMPTZ '2000-01-01' AND TIMESTAMPTZ '2100-01-01' THEN {parsed} END"
    return f"({rango})::DATE" if solo_fecha else rango


def entero_sql(expr: str) -> str:
    return f"CASE WHEN try_cast(replace({expr}, '.', '') AS BIGINT) >= 0 THEN try_cast(replace({expr}, '.', '') AS BIGINT) END"


def flags_sql(condiciones: dict) -> str:
    casos = ", ".join(f"CASE WHEN {cond} THEN '{nombre}' END" for nombre, cond in condiciones.items())
    return f"list_filter([{casos}], lambda x: x IS NOT NULL)"


def deduplicar(con, tabla: str, id_expr: str, fuente: str, cols: str):
    """Crea temp `{tabla}_ok` (una fila por id) y devuelve SQL de rechazos."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {tabla}_base AS
        SELECT {id_expr} AS id, {cols}, _fila, _hash,
               row_number() OVER (PARTITION BY {id_expr} ORDER BY _fila) AS rn,
               count(*) OVER (PARTITION BY {id_expr}, _hash) AS n_igual
        FROM {fuente}
    """)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {tabla}_ok AS SELECT * EXCLUDE (rn, n_igual) "
                f"FROM {tabla}_base WHERE id IS NOT NULL AND rn = 1")
    return f"""SELECT '{tabla}' AS tabla, _fila, _hash, id,
                      CASE WHEN id IS NULL THEN 'sin_id'
                           WHEN n_igual > 1 THEN 'duplicado_exacto'
                           ELSE 'id_duplicado_con_otro_contenido' END AS motivo
               FROM {tabla}_base WHERE id IS NULL OR rn > 1"""


def atributos_texto(con) -> None:
    textos = [r[0] for r in con.execute("SELECT DISTINCT coalesce(texto, '') FROM comentarios_ok").fetchall()]
    filas = [{"texto_crudo": t, **texto.atributos(t)} for t in textos]
    attr_tabla = pa.Table.from_pylist(filas, schema=ESQUEMA_ATRIBUTOS)
    con.register("attr_arrow", attr_tabla)
    con.execute("CREATE OR REPLACE TEMP TABLE attr AS SELECT * FROM attr_arrow")
    con.unregister("attr_arrow")


def correr(lago: Lago) -> dict:
    con = lago.conectar()
    b = {t: lago.leer("bronze", t) for t in ("comentarios", "cuentas", "publicaciones", "fuentes")}
    rechazos = []

    # --- fuentes ---------------------------------------------------------
    cf = columnas(con, b["fuentes"]) if lago.ruta("bronze", "fuentes").exists() else set()
    if cf:
        rechazos.append(deduplicar(con, "fuentes", col(cf, "fuente_id"), b["fuentes"],
                                   f"{col(cf, 'nombre')} AS nombre, {col(cf, 'tipo')} AS tipo"))
    else:
        con.execute("CREATE TEMP TABLE fuentes_ok (id VARCHAR, nombre VARCHAR, tipo VARCHAR)")
    lago.escribir(con, "silver", "fuentes",
                  "SELECT id AS fuente_id, nombre, lower(tipo) AS tipo FROM fuentes_ok ORDER BY 1")

    # --- publicaciones ---------------------------------------------------
    cp = columnas(con, b["publicaciones"])
    rechazos.append(deduplicar(con, "publicaciones", col(cp, "publicacion_id"), b["publicaciones"],
                               f"{col(cp, 'fuente_id')} AS fuente_id, {col(cp, 'fecha')} AS fecha_raw, "
                               f"{col(cp, 'titular', False)} AS titular"))

    # --- comentarios: tipado + referencias -------------------------------
    cc = columnas(con, b["comentarios"])
    rechazos.append(deduplicar(con, "comentarios", col(cc, "comentario_id"), b["comentarios"], ", ".join([
        f"{col(cc, 'publicacion_id')} AS publicacion_id", f"{col(cc, 'cuenta_id')} AS cuenta_id",
        f"{col(cc, 'fecha')} AS fecha_raw", f"{col(cc, 'texto', False)} AS texto",
        f"{col(cc, 'respuesta_a')} AS respuesta_raw", f"{col(cc, 'me_gusta')} AS me_gusta_raw"])))
    atributos_texto(con)

    cu = columnas(con, b["cuentas"])
    rechazos.append(deduplicar(con, "cuentas", col(cu, "cuenta_id"), b["cuentas"], ", ".join([
        f"{col(cu, 'usuario')} AS usuario", f"{col(cu, 'fecha_creacion')} AS creacion_raw",
        f"{col(cu, 'seguidores')} AS seguidores_raw", f"{col(cu, 'siguiendo')} AS siguiendo_raw"])))

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE pubs AS
        SELECT p.id AS publicacion_id, p.fuente_id, {fecha_sql('p.fecha_raw')} AS ts, p.titular,
               {flags_sql({
                   'fecha_invalida': f"{fecha_sql('p.fecha_raw')} IS NULL",
                   'fuente_desconocida': 'f.id IS NULL',
               })} AS flags
        FROM publicaciones_ok p LEFT JOIN fuentes_ok f ON f.id = p.fuente_id
    """)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE com AS
        SELECT c.id AS comentario_id, c.publicacion_id, c.cuenta_id, c._fila,
               {fecha_sql('c.fecha_raw')} AS ts_original,
               CASE WHEN r.id IS NOT NULL AND c.respuesta_raw <> c.id THEN c.respuesta_raw END AS respuesta_a,
               {entero_sql('c.me_gusta_raw')} AS me_gusta,
               coalesce(c.texto, '') AS texto,
               a.* EXCLUDE (texto_crudo),
               p.publicacion_id IS NULL AS pub_desconocida,
               p.ts AS ts_publicacion,
               c.respuesta_raw IS NOT NULL AND (r.id IS NULL OR c.respuesta_raw = c.id) AS resp_invalida,
               c.me_gusta_raw IS NOT NULL AND {entero_sql('c.me_gusta_raw')} IS NULL AS mg_invalido,
               c.fecha_raw
        FROM comentarios_ok c
        LEFT JOIN attr a ON a.texto_crudo = coalesce(c.texto, '')
        LEFT JOIN pubs p ON p.publicacion_id = c.publicacion_id
        LEFT JOIN (SELECT id FROM comentarios_ok) r ON r.id = c.respuesta_raw
    """)
    # Imputar fechas faltantes: primero el comentario padre, si no la publicación.
    con.execute("""
        CREATE OR REPLACE TEMP TABLE com2 AS
        SELECT c.*, coalesce(c.ts_original, padre.ts_original, c.ts_publicacion) AS ts
        FROM com c LEFT JOIN com padre ON padre.comentario_id = c.respuesta_a
    """)
    lago.escribir(con, "silver", "comentarios", f"""
        SELECT c.comentario_id, c.publicacion_id, c.cuenta_id, c.ts,
               hour(c.ts) AS hora_local, c.ts::DATE AS dia_local,
               c.respuesta_a, c.respuesta_a IS NOT NULL AS es_respuesta, c.me_gusta,
               c.texto, c.texto_limpio, c.texto_norm, md5(c.texto_norm) AS texto_id, c.n_tokens,
               c.es_pregunta, c.hashtags, c.emojis, c.n_urls, c.n_menciones, c.prop_mayusculas,
               {flags_sql({
                   'fecha_imputada': 'c.ts_original IS NULL AND c.ts IS NOT NULL',
                   'sin_fecha': 'c.ts IS NULL',
                   'publicacion_desconocida': 'c.pub_desconocida',
                   'sin_cuenta': 'c.cuenta_id IS NULL',
                   'cuenta_desconocida': 'c.cuenta_id IS NOT NULL AND c.cuenta_id NOT IN (SELECT id FROM cuentas_ok)',
                   'respuesta_invalida': 'c.resp_invalida',
                   'me_gusta_invalido': 'c.mg_invalido',
                   'texto_vacio': "c.texto_norm = ''",
               })} AS flags
        FROM com2 c ORDER BY c._fila
    """)
    sc = lago.leer("silver", "comentarios")

    lago.escribir(con, "silver", "publicaciones", f"""
        SELECT p.publicacion_id, p.fuente_id, coalesce(p.ts, m.primer_comentario) AS ts, p.titular,
               CASE WHEN p.ts IS NULL AND m.primer_comentario IS NOT NULL
                    THEN list_append(p.flags, 'fecha_imputada') ELSE p.flags END AS flags
        FROM pubs p LEFT JOIN (SELECT publicacion_id, min(ts) AS primer_comentario FROM {sc} GROUP BY 1) m
             USING (publicacion_id)
        ORDER BY 1
    """)

    # --- cuentas: perfil + cuentas que solo aparecen en comentarios -------
    inicio = con.execute(f"SELECT min(ts)::DATE FROM {sc}").fetchall()[0][0]
    lago.escribir(con, "silver", "cuentas", f"""
        WITH perfil AS (
            SELECT id AS cuenta_id, usuario, {fecha_sql('creacion_raw', True)} AS fecha_creacion,
                   {entero_sql('seguidores_raw')} AS seguidores, {entero_sql('siguiendo_raw')} AS siguiendo,
                   creacion_raw, seguidores_raw, siguiendo_raw
            FROM cuentas_ok
        ), activas AS (SELECT DISTINCT cuenta_id FROM {sc} WHERE cuenta_id IS NOT NULL)
        SELECT coalesce(p.cuenta_id, a.cuenta_id) AS cuenta_id, p.usuario, p.fecha_creacion,
               DATE '{inicio}' - p.fecha_creacion AS antiguedad_dias, p.seguidores, p.siguiendo,
               a.cuenta_id IS NOT NULL AS activa,
               {flags_sql({
                   'sin_perfil': 'p.cuenta_id IS NULL',
                   'fecha_creacion_invalida': 'p.cuenta_id IS NOT NULL AND p.fecha_creacion IS NULL',
                   'seguidores_invalido': 'p.seguidores_raw IS NOT NULL AND p.seguidores IS NULL',
                   'siguiendo_invalido': 'p.siguiendo_raw IS NOT NULL AND p.siguiendo IS NULL',
               })} AS flags
        FROM perfil p FULL OUTER JOIN activas a ON a.cuenta_id = p.cuenta_id
        ORDER BY 1
    """)

    # --- textos únicos: base para embeddings -----------------------------
    # Orden y representante deterministas: el resultado no puede depender de empates.
    lago.escribir(con, "silver", "textos", f"""
        WITH variantes AS (
            SELECT texto_id, texto_limpio, count(*) AS n FROM {sc} GROUP BY 1, 2
        ), representante AS (
            SELECT texto_id, first(texto_limpio ORDER BY n DESC, texto_limpio) AS texto_limpio
            FROM variantes GROUP BY 1
        )
        SELECT c.texto_id, c.texto_norm, r.texto_limpio, any_value(c.n_tokens) AS n_tokens,
               count(*) AS n_comentarios, count(DISTINCT c.cuenta_id) AS n_cuentas,
               count(DISTINCT c.publicacion_id) AS n_publicaciones, min(c.ts) AS primera_vez
        FROM {sc} c JOIN representante r USING (texto_id)
        GROUP BY c.texto_id, c.texto_norm, r.texto_limpio ORDER BY n_comentarios DESC, c.texto_id
    """)

    lago.escribir(con, "silver", "rechazos", " UNION ALL ".join(rechazos))

    # --- reporte de calidad ----------------------------------------------
    calidad = con.execute(f"""
        SELECT 'comentarios' AS tabla, f AS chequeo, count(*) AS filas FROM {sc}, unnest(flags) t(f) GROUP BY 1, 2
        UNION ALL SELECT 'cuentas', f, count(*) FROM {lago.leer('silver', 'cuentas')}, unnest(flags) t(f) GROUP BY 1, 2
        UNION ALL SELECT 'publicaciones', f, count(*) FROM {lago.leer('silver', 'publicaciones')}, unnest(flags) t(f) GROUP BY 1, 2
        UNION ALL SELECT tabla, 'rechazo:' || motivo, count(*) FROM {lago.leer('silver', 'rechazos')} GROUP BY 1, 2
        UNION ALL SELECT tabla, 'csv_ilegible', count(*) FROM {lago.leer('bronze', 'rechazos_csv')} GROUP BY 1
        ORDER BY 1, 3 DESC
    """).df()
    totales = {t: con.execute(f"SELECT count(*) FROM {lago.leer('silver', t)}").fetchall()[0][0]
               for t in ("comentarios", "cuentas", "publicaciones", "fuentes", "textos")}
    con.register("calidad_df", calidad)
    lago.escribir(con, "silver", "calidad", "SELECT * FROM calidad_df")
    reporte = {"filas": totales, "chequeos": calidad.to_dict(orient="records")}
    (lago.raiz / "calidad.json").write_text(json.dumps(reporte, ensure_ascii=False, indent=2, default=str),
                                            encoding="utf-8")
    con.close()
    return reporte
