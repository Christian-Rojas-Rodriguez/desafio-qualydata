"""Bronze + silver aguantan datos sucios sin perder comentarios con id.

Arma un set chico a partir de práctica e inyecta los problemas típicos de un
export real: duplicados, fechas en otros formatos, números rotos, respuestas
huérfanas, encabezados con mayúsculas, CRLF, archivos sin comprimir y una
línea mal formada.
"""
import csv
import gzip
from pathlib import Path

import duckdb
import pytest

from qd import bronze, silver
from qd.lago import Lago

PRACTICA = Path(__file__).resolve().parent.parent / "datos" / "practica"
N = 3000


def leer(nombre):
    with gzip.open(PRACTICA / f"{nombre}.csv.gz", "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir(path: Path, filas, columnas, encabezado=None, crlf=False):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n" if crlf else "\n")
        w.writerow(encabezado or columnas)
        for fila in filas:
            w.writerow([fila.get(c, "") for c in columnas])


@pytest.fixture(scope="module")
def lago(tmp_path_factory):
    datos = tmp_path_factory.mktemp("sucio")
    com = leer("comentarios")[:N]
    usados = {c["cuenta_id"] for c in com}
    cuentas = [c for c in leer("cuentas") if c["cuenta_id"] in usados]
    pubs = [p for p in leer("publicaciones") if p["publicacion_id"] in {c["publicacion_id"] for c in com}]

    com[0]["fecha"] = "ayer a la tarde"                       # fecha ilegible, se imputa
    com[1]["fecha"] = "01/09/2026 07:40:00"                   # dd/mm/aaaa sin zona
    com[2]["fecha"] = "1788262200"                            # epoch
    com[3]["me_gusta"] = "-3"
    com[4]["me_gusta"] = "muchos"
    com[5]["respuesta_a"] = "c9999999"                        # padre inexistente
    com[6]["respuesta_a"] = com[6]["comentario_id"]           # se responde a sí mismo
    com[7]["texto"] = ""
    com[8]["texto"] = 'dijo "basta"\ny se fue, #ParoYa 🔥'    # comillas, salto de línea, hashtag
    com[9]["cuenta_id"] = "u_fantasma"                        # cuenta sin perfil
    com[10]["comentario_id"] = "  " + com[10]["comentario_id"] + " "  # espacios en el id
    com.append(dict(com[20]))                                 # duplicado exacto
    com.append({**com[21], "texto": "otro texto"})            # mismo id, otro contenido
    com.append({**com[22], "comentario_id": ""})              # sin id
    cuentas[0]["seguidores"] = "1.234"
    cuentas[1]["seguidores"] = "n/a"
    cuentas[2]["fecha_creacion"] = "nunca"
    cuentas.append(dict(cuentas[3]))
    pubs[0]["fuente_id"] = "f99"
    pubs[1]["fecha"] = ""

    cols = ["comentario_id", "publicacion_id", "cuenta_id", "fecha", "texto", "respuesta_a", "me_gusta"]
    escribir(datos / "comentarios.csv", com, cols, encabezado=[c.upper() for c in cols], crlf=True)
    with open(datos / "comentarios.csv", "a", encoding="utf-8") as f:
        f.write('c_roto,p00001,u000001,2026-09-01T10:00:00-03:00,"comilla sin cerrar,,0\r\n')
    escribir(datos / "cuentas.csv", cuentas, ["cuenta_id", "usuario", "fecha_creacion", "seguidores", "siguiendo"])
    escribir(datos / "publicaciones.csv", pubs, ["publicacion_id", "fuente_id", "fecha", "titular"])
    # fuentes.csv no existe: es opcional

    lago = Lago(tmp_path_factory.mktemp("lago"))
    bronze.correr(datos, lago)
    silver.correr(lago)
    lago.ids_esperados = {c["comentario_id"].strip() for c in com if c["comentario_id"].strip()}
    return lago


def q(lago, sql):
    con = lago.conectar()
    for capa in ("bronze", "silver"):
        for p in (lago.raiz / capa).glob("*.parquet"):
            con.execute(f"CREATE VIEW {capa}_{p.stem} AS SELECT * FROM read_parquet('{p}')")
    return con.execute(sql).fetchall()


def test_ningun_comentario_con_id_se_pierde(lago):
    ids = [r[0] for r in q(lago, "SELECT comentario_id FROM silver_comentarios")]
    assert len(ids) == len(set(ids)), "ids repetidos en silver"
    assert lago.ids_esperados <= set(ids)


def test_rechazos_explican_duplicados_y_sin_id(lago):
    motivos = dict(q(lago, "SELECT motivo, count(*) FROM silver_rechazos WHERE tabla = 'comentarios' GROUP BY 1"))
    assert motivos.get("duplicado_exacto") == 1
    assert motivos.get("id_duplicado_con_otro_contenido") == 1
    assert motivos.get("sin_id") == 1


def test_fechas_alternativas_e_imputacion(lago):
    nulas = q(lago, "SELECT count(*) FROM silver_comentarios WHERE ts IS NULL")[0][0]
    assert nulas == 0
    flags = {f for (f,) in q(lago, "SELECT DISTINCT unnest(flags) FROM silver_comentarios")}
    assert {"fecha_imputada", "respuesta_invalida", "me_gusta_invalido", "texto_vacio",
            "cuenta_desconocida"} <= flags


def test_formatos_de_fecha_se_interpretan_en_hora_argentina(lago):
    horas = dict(q(lago, "SELECT texto, strftime(ts, '%Y-%m-%d %H:%M') FROM silver_comentarios "
                         "WHERE comentario_id IN ('c0000002', 'c0000003')"))
    assert "2026-09-01 07:40" in horas.values()   # dd/mm/aaaa sin zona = hora local
    assert "2026-09-01 08:30" in horas.values()   # epoch 1788262200 = 11:30 UTC


def test_valores_corregidos(lago):
    seg = dict(q(lago, "SELECT cuenta_id, seguidores FROM silver_cuentas"))
    assert 1234 in seg.values()
    autoresp = q(lago, "SELECT count(*) FROM silver_comentarios WHERE respuesta_a = comentario_id")[0][0]
    assert autoresp == 0
    assert q(lago, "SELECT count(*) FROM silver_cuentas WHERE cuenta_id = 'u_fantasma' "
                   "AND list_contains(flags, 'sin_perfil')")[0][0] == 1
    assert q(lago, "SELECT count(*) FROM silver_publicaciones WHERE list_contains(flags, 'fuente_desconocida')")[0][0] >= 1


def test_texto_raro_se_normaliza(lago):
    fila = q(lago, "SELECT texto_norm, hashtags, emojis FROM silver_comentarios WHERE texto LIKE '%basta%'")[0]
    assert fila[0] == "dijo basta y se fue paro ya"
    assert fila[1] == ["paroya"] and fila[2] == ["🔥"]


def test_linea_mal_formada_queda_registrada(lago):
    n_bronze = q(lago, "SELECT count(*) FROM bronze_comentarios")[0][0]
    n_ilegibles = q(lago, "SELECT count(*) FROM bronze_rechazos_csv")[0][0]
    assert n_bronze + n_ilegibles >= N + 4
