"""Gold: un vector por texto único (silver/textos), con caché por texto_id.

Se embebe `texto_limpio` (no la versión sin acentos): los modelos se entrenaron
con texto natural. Los vectores quedan normalizados, así producto punto = coseno.
"""
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .lago import Lago

MODELO = "intfloat/multilingual-e5-small"


def dispositivo() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def correr(lago: Lago, modelo: str = MODELO, lote: int = 128) -> dict:
    con = lago.conectar()
    textos = con.execute(f"SELECT texto_id, texto_limpio FROM {lago.leer('silver', 'textos')}").fetchall()
    destino = lago.ruta("gold", "embeddings")
    previos = {}
    if destino.exists():
        t = pq.read_table(destino)
        if t.schema.metadata and t.schema.metadata.get(b"modelo", b"").decode() == modelo:
            previos = dict(zip(t["texto_id"].to_pylist(), t["vector"].to_numpy(zero_copy_only=False)))
    faltan = [(i, x) for i, x in textos if i not in previos]
    if faltan:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(modelo, device=dispositivo())
        prefijo = "query: " if "e5" in modelo else ""
        vec = m.encode([prefijo + (x or "") for _, x in faltan], batch_size=lote,
                       normalize_embeddings=True, show_progress_bar=False)
        previos.update({i: v.astype(np.float32) for (i, _), v in zip(faltan, vec)})
    ids = [i for i, _ in textos]
    matriz = np.stack([previos[i] for i in ids]).astype(np.float32)
    tabla = pa.table({"texto_id": ids,
                      "vector": pa.FixedSizeListArray.from_arrays(matriz.ravel(), matriz.shape[1])})
    pq.write_table(tabla.replace_schema_metadata({"modelo": modelo}), destino, compression="zstd")
    con.close()
    return {"modelo": modelo, "textos": len(ids), "nuevos": len(faltan), "dim": matriz.shape[1]}


def cargar(lago: Lago):
    t = pq.read_table(lago.ruta("gold", "embeddings"))
    ids = t["texto_id"].to_pylist()
    matriz = t["vector"].combine_chunks().flatten().to_numpy().reshape(len(ids), -1)
    return ids, matriz
