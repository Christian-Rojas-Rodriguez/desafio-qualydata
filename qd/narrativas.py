"""Gold: narrativas, postura y origen.

1. Micro-clusters: Leiden sobre el grafo de k vecinos de los embeddings. Cada uno
   agrupa variantes de una misma frase (muletillas, typos, sinónimos).
2. Tipos de micro-cluster: `generico` (textos cortos tipo "tal cual" que acompañan
   cualquier cosa), `ruido` (casi no participa de conversaciones) o de narrativa.
3. Grafo de respuestas entre micro-clusters: una respuesta siempre pertenece a la
   narrativa del comentario al que responde, así que esas aristas unen los dos
   lados (apoya / rechaza) de cada narrativa. Leiden decide cuántas hay.
4. Reasignación por texto: una plantilla como "lo de X es falso" puede mezclar
   narrativas en un micro-cluster. Cada texto toma la narrativa que votan sus
   respuestas, propagada a los textos vecinos que no tienen respuestas.
5. Postura: dentro de cada narrativa la mayoría de las respuestas contradice al
   padre, así que los lados salen de un corte máximo del grafo de respuestas.
   Las respuestas entre cuentas de una misma operación coordinada no cuentan: se
   dan la razón. Qué lado "apoya" lo decide `postura.elegir_lado`.
6. Comentarios: las respuestas heredan la narrativa del padre; las genéricas
   heredan también la postura.
7. Origen: primer comentario que inicia una racha sostenida de la narrativa.
"""
from collections import Counter, defaultdict

import igraph as ig
import leidenalg as la
import numpy as np
import pyarrow as pa
import scipy.sparse as sp

from . import embeddings, postura
from .lago import Lago

PARAMS = {
    "k_vecinos": 10,
    "resolucion_micro": 1.0,
    "tokens_generico": 4,         # micro-clusters con mediana de tokens <= esto son genéricos
    "participacion_minima": 0.05, # fracción de comentarios en conversaciones para ser narrativa
    "resolucion_narrativas": 1.0,
    "peso_voto": 2.0,             # cuánto pesa un voto de respuesta frente a un vecino de texto
    "rondas_propagacion": 3,
    "rondas_postura": 3,
    "umbral_postura": 1.0,        # evidencia mínima para que un texto cambie de lado
    "origen_ventana_h": 6,        # racha: al menos `origen_min` comentarios en esta ventana
    "origen_min": 5,
    "semilla": 0,
}


def vecinos(X: np.ndarray, k: int):
    import torch
    T = torch.tensor(X, device=embeddings.dispositivo())
    idx = np.zeros((len(X), k), dtype=np.int64)
    sim = np.zeros((len(X), k), dtype=np.float32)
    for s in range(0, len(X), 4096):
        v, i = torch.topk(T[s:s + 4096] @ T.T, k + 1, dim=1)
        idx[s:s + 4096], sim[s:s + 4096] = i[:, 1:].cpu().numpy(), v[:, 1:].cpu().numpy()
    return idx, sim


def leiden(n: int, aristas, pesos, resolucion: float, semilla: int) -> np.ndarray:
    g = ig.Graph(n=n, edges=aristas, directed=False)
    g.es["weight"] = pesos
    g = g.simplify(combine_edges="sum")
    part = la.find_partition(g, la.RBConfigurationVertexPartition, weights="weight",
                             resolution_parameter=resolucion, seed=semilla)
    return np.array(part.membership)


def corte_maximo(nodos, pesos: dict, semilla: int = 0) -> dict:
    """Divide nodos en dos lados maximizando el peso de las aristas que cruzan.

    Búsqueda local desde varios arranques; con pocas decenas de nodos alcanza el óptimo.
    """
    nodos = sorted(nodos)
    vecinos_de = defaultdict(list)
    for (a, b), w in pesos.items():
        vecinos_de[a].append((b, w))
        vecinos_de[b].append((a, w))
    rng = np.random.default_rng(semilla)
    mejor, mejor_v = None, -1.0
    for _ in range(20):
        lado = {n: int(rng.integers(2)) for n in nodos}
        mejoro = True
        while mejoro:
            mejoro = False
            for n in nodos:
                ganancia = sum(w if lado[v] == lado[n] else -w for v, w in vecinos_de[n])
                if ganancia > 0:
                    lado[n] ^= 1
                    mejoro = True
        v = sum(w for (a, b), w in pesos.items() if lado[a] != lado[b])
        if v > mejor_v:
            mejor, mejor_v = dict(lado), v
    return mejor


def terminos_clave(textos_narr, textos_todos, n=6):
    """Bigramas y palabras más distintivos de la narrativa (c-TF-IDF simple)."""
    def tokens(t):
        w = [x for x in t.split() if len(x) > 3]
        return w + [f"{a} {b}" for a, b in zip(w, w[1:])]
    df = Counter(x for t in textos_todos for x in set(tokens(t)))
    tf = Counter(x for t in textos_narr for x in tokens(t))
    N = len(textos_todos)
    puntaje = {x: c * np.log(N / (1 + df[x])) for x, c in tf.items() if c >= 5}
    elegidos = []
    for x, _ in sorted(puntaje.items(), key=lambda kv: -kv[1]):
        if not any(x in e or e in x for e in elegidos):
            elegidos.append(x)
        if len(elegidos) == n:
            break
    return elegidos


def origen(ts_horas: np.ndarray, ventana: float, minimo: int) -> int:
    """Índice del primer comentario seguido por una racha de `minimo` en `ventana` horas."""
    fin = np.searchsorted(ts_horas, ts_horas + ventana, side="right")
    rachas = np.nonzero(fin - np.arange(len(ts_horas)) >= minimo)[0]
    return int(rachas[0]) if len(rachas) else 0


def correr(lago: Lago, p: dict = None) -> dict:
    p = {**PARAMS, **(p or {})}
    con = lago.conectar()
    ids, X = embeddings.cargar(lago)
    n_txt = len(ids)
    k = p["k_vecinos"]
    vidx, vsim = vecinos(X, k)
    src = np.repeat(np.arange(n_txt), k)
    mc = leiden(n_txt, list(zip(src.tolist(), vidx.ravel().tolist())), vsim.ravel().tolist(),
                p["resolucion_micro"], p["semilla"])
    n_mc = int(mc.max()) + 1
    txt_de = {t: i for i, t in enumerate(ids)}

    com = con.execute(f"""
        SELECT comentario_id, texto_id, respuesta_a, epoch(ts) AS ts, n_tokens, texto_norm, texto_limpio,
               cuenta_id
        FROM {lago.leer('silver', 'comentarios')} ORDER BY ts, comentario_id
    """).fetchall()
    # Operaciones coordinadas detectadas (si ya corrió esa etapa): sus cuentas se dan
    # la razón entre sí y empujan el lado que afirma la narrativa.
    grupo_de = {}
    if lago.ruta("gold", "cuentas_grupo").exists():
        grupo_de = dict(con.execute(f"SELECT cuenta_id, grupo FROM {lago.leer('gold', 'cuentas_grupo')}").fetchall())
    grupo_com = [grupo_de.get(r[7]) for r in com]
    n_com = len(com)
    cid = [r[0] for r in com]
    pos = {c: i for i, c in enumerate(cid)}
    txt = np.array([txt_de[r[1]] for r in com])
    cm = mc[txt]
    padre = np.array([pos.get(r[2], -1) if r[2] else -1 for r in com])
    hijos = np.nonzero(padre >= 0)[0]
    tiene_hijos = np.zeros(n_com, bool)
    tiene_hijos[padre[hijos]] = True

    # --- 2. tipo de cada micro-cluster ------------------------------------
    tokens = defaultdict(list)
    for i, r in enumerate(com):
        tokens[cm[i]].append(r[4])
    particip = np.bincount(cm, weights=((padre >= 0) | tiene_hijos).astype(float), minlength=n_mc) \
        / np.maximum(np.bincount(cm, minlength=n_mc), 1)
    tipo = {}
    for m in range(n_mc):
        if np.median(tokens[m] or [0]) <= p["tokens_generico"]:
            tipo[m] = "generico"
        elif particip[m] < p["participacion_minima"]:
            tipo[m] = "ruido"
        else:
            tipo[m] = "narrativa"
    es_narr_mc = np.array([tipo[m] == "narrativa" for m in range(n_mc)])

    # --- 3. narrativas a nivel micro-cluster -------------------------------
    pares = [(h, padre[h]) for h in hijos if es_narr_mc[cm[h]] and es_narr_mc[cm[padre[h]]]]
    pesos_mc = Counter((min(cm[a], cm[b]), max(cm[a], cm[b])) for a, b in pares if cm[a] != cm[b])
    narr_mc = [m for m in range(n_mc) if es_narr_mc[m]]
    loc = {m: i for i, m in enumerate(narr_mc)}
    comunidad = leiden(len(narr_mc), [(loc[a], loc[b]) for a, b in pesos_mc],
                       [float(w) for w in pesos_mc.values()], p["resolucion_narrativas"], p["semilla"])
    n_narr = int(comunidad.max()) + 1
    narr_de_mc = np.full(n_mc, -1)
    for m in narr_mc:
        narr_de_mc[m] = comunidad[loc[m]]

    # --- 4. reasignación por texto -----------------------------------------
    # Un texto largo que cayó en un micro-cluster genérico no es "tal cual": su
    # narrativa la decide la evidencia, igual que un texto de un cluster mezclado.
    tok_txt = np.zeros(n_txt, int)
    tok_txt[txt] = [r[4] for r in com]
    es_gen_mc = np.array([tipo[m] == "generico" for m in range(n_mc)])
    generico_txt = es_gen_mc[mc] & (tok_txt <= p["tokens_generico"])
    activo = es_narr_mc[mc] | (es_gen_mc[mc] & ~generico_txt)
    capaz = activo[txt]
    pares_texto = [(h, padre[h]) for h in hijos if capaz[h] and capaz[padre[h]]]
    votos = np.zeros((n_txt, n_narr))
    for a, b in pares_texto:
        if narr_de_mc[cm[b]] >= 0:
            votos[txt[a], narr_de_mc[cm[b]]] += 1
        if narr_de_mc[cm[a]] >= 0:
            votos[txt[b], narr_de_mc[cm[a]]] += 1
    # La evidencia (votos de respuestas) se difunde por el grafo de textos parecidos;
    # la etiqueta del micro-cluster solo decide donde no llega evidencia.
    S = sp.csr_matrix((vsim.ravel(), (src, vidx.ravel())), shape=(n_txt, n_txt))
    D = sp.diags(activo.astype(np.float32))
    S = (D @ S.maximum(S.T) @ D).tocsr()
    S = sp.diags(1 / np.maximum(np.asarray(S.sum(1)).ravel(), 1e-9)) @ S
    evidencia = votos.copy()
    for _ in range(p["rondas_propagacion"]):
        evidencia = votos + 0.5 * (S @ evidencia)
    con_evidencia = evidencia.sum(1) > 0
    narr_txt = np.where(activo, np.where(con_evidencia, evidencia.argmax(1), narr_de_mc[mc]), -1)

    # --- 5. postura: nodos = (micro-cluster, narrativa) ---------------------
    nodo_de_txt = {t: (int(mc[t]), int(narr_txt[t])) for t in range(n_txt) if narr_txt[t] >= 0}
    pesos_nodo = Counter()
    for a, b in pares_texto:
        na, nb = nodo_de_txt.get(txt[a]), nodo_de_txt.get(txt[b])
        misma_operacion = grupo_com[a] is not None and grupo_com[a] == grupo_com[b]
        if na and nb and na != nb and na[1] == nb[1] and not misma_operacion:
            pesos_nodo[tuple(sorted((na, nb)))] += 1
    nodos_por_narr = defaultdict(set)
    for nodo in nodo_de_txt.values():
        nodos_por_narr[nodo[1]].add(nodo)
    centroide = {}
    for t, nodo in nodo_de_txt.items():
        centroide.setdefault(nodo, []).append(t)
    centroide = {nodo: X[ts].mean(0) for nodo, ts in centroide.items()}
    lado_nodo = {}
    for n, nodos in nodos_por_narr.items():
        pn = {e: w for e, w in pesos_nodo.items() if e[0][1] == n}
        conectados = {x for e in pn for x in e}
        lado = corte_maximo(conectados, pn, p["semilla"]) if conectados else {}
        for nodo in nodos - conectados:  # sin respuestas: el lado del nodo conectado más parecido
            if conectados:
                cerca = max(conectados, key=lambda c: float(centroide[c] @ centroide[nodo]))
                lado[nodo] = lado[cerca]
            else:
                lado[nodo] = 0
        lado_nodo.update(lado)

    # --- 5b. refinamiento por texto: un micro-cluster puede mezclar posturas
    # ("todo para la foto" y "no tiene sentido lo de la foto"). Cada texto vota en
    # contra del lado de quien le responde o a quien responde, y el voto se suaviza
    # entre textos parecidos de la misma narrativa.
    signo = np.zeros(n_txt)
    for t, nodo in nodo_de_txt.items():
        signo[t] = 1.0 if lado_nodo[nodo] == 0 else -1.0
    contra = [(txt[a], txt[b]) for a, b in pares_texto
              if txt[a] != txt[b] and narr_txt[txt[a]] >= 0 and narr_txt[txt[a]] == narr_txt[txt[b]]
              and not (grupo_com[a] is not None and grupo_com[a] == grupo_com[b])]
    ca = np.array([x for x, _ in contra], dtype=np.int64)
    cb = np.array([y for _, y in contra], dtype=np.int64)
    Sc = S.tocoo()
    misma = narr_txt[Sc.row] == narr_txt[Sc.col]
    Sn = sp.csr_matrix((Sc.data[misma], (Sc.row[misma], Sc.col[misma])), shape=S.shape)
    Sn = sp.diags(1 / np.maximum(np.asarray(Sn.sum(1)).ravel(), 1e-9)) @ Sn
    for _ in range(p["rondas_postura"]):
        voto = np.zeros(n_txt)
        np.add.at(voto, ca, -signo[cb])
        np.add.at(voto, cb, -signo[ca])
        suave = voto + 0.5 * (Sn @ voto)
        signo = np.where(np.abs(suave) >= p["umbral_postura"], np.sign(suave), signo)

    raiz_de_txt = defaultdict(list)
    for i in range(n_com):
        if padre[i] < 0 and narr_txt[txt[i]] >= 0:
            raiz_de_txt[txt[i]].append(i)
    lado_txt, info_lados = {}, {}
    textos_por_narr = defaultdict(list)
    for t in nodo_de_txt:
        textos_por_narr[int(narr_txt[t])].append(t)
    for n, ts_n in textos_por_narr.items():
        lados = []
        for s_ in (1.0, -1.0):
            idx = [i for t in ts_n if signo[t] == s_ for i in raiz_de_txt[t]]
            lados.append({"limpio": [com[i][6] for i in idx], "norm": [com[i][5] for i in idx],
                          "coordinados": sum(grupo_com[i] is not None for i in idx)})
        apoya, info = postura.elegir_lado(lados[0], lados[1])
        info_lados[n] = info
        signo_apoya = 1.0 if apoya == 0 else -1.0
        for t in ts_n:
            lado_txt[t] = "apoya" if signo[t] == signo_apoya else "rechaza"

    # --- 6. asignación por comentario (orden temporal: el padre ya está) ---
    narr = [""] * n_com
    post = [""] * n_com
    for i in range(n_com):
        t = txt[i]
        q = padre[i]
        if q >= 0 and narr[q]:
            narr[i] = narr[q]
            if t in lado_txt and f"n{narr_txt[t]:02d}" == narr[i]:
                post[i] = lado_txt[t]
            elif generico_txt[t]:
                post[i] = post[q]
            else:
                post[i] = "rechaza" if post[q] == "apoya" else "apoya"
        elif t in lado_txt:
            narr[i] = f"n{narr_txt[t]:02d}"
            post[i] = lado_txt[t]

    # --- 7. tabla de narrativas --------------------------------------------
    ts = np.array([r[3] for r in com])
    todos = [r[5] for r in com if r[5]]
    por_narr = defaultdict(list)
    for i, n in enumerate(narr):
        if n:
            por_narr[n].append(i)
    filas_narr = []
    for n, idx in sorted(por_narr.items()):
        o = idx[origen(ts[idx] / 3600, p["origen_ventana_h"], p["origen_min"])]
        apoyan = [com[i][6] for i in idx if post[i] == "apoya" and padre[i] < 0]
        info = info_lados.get(int(n[1:]), {})
        filas_narr.append({
            "narrativa": n,
            "titulo": info.get("titulo") or (Counter(apoyan).most_common(1)[0][0] if apoyan else com[idx[0]][6]),
            "frases_clave": "|".join(terminos_clave([com[i][5] for i in idx], todos)),
            "fecha_origen_s": float(ts[o]), "comentarios": len(idx),
            "apoya": sum(post[i] == "apoya" for i in idx), "rechaza": sum(post[i] == "rechaza" for i in idx),
            "metodo_postura": info.get("metodo", ""),
        })

    tabla_com = pa.table({"comentario_id": cid, "narrativa": narr, "postura": post,
                          "micro_cluster": cm.tolist(), "tipo_cluster": [tipo[m] for m in cm]})
    con.register("t_com", tabla_com)
    lago.escribir(con, "gold", "comentarios_narrativa", "SELECT * FROM t_com")
    con.register("t_narr", pa.Table.from_pylist(filas_narr))
    lago.escribir(con, "gold", "narrativas", "SELECT * EXCLUDE (fecha_origen_s), "
                  "to_timestamp(fecha_origen_s) AS fecha_origen FROM t_narr ORDER BY comentarios DESC")
    con.register("t_mc", pa.table({
        "micro_cluster": list(range(n_mc)), "tipo": [tipo[m] for m in range(n_mc)],
        "narrativa_inicial": [f"n{narr_de_mc[m]:02d}" if narr_de_mc[m] >= 0 else "" for m in range(n_mc)],
        "participacion": particip.tolist()}))
    lago.escribir(con, "gold", "micro_clusters", "SELECT * FROM t_mc")
    con.close()
    return {"micro_clusters": n_mc, "tipos": dict(Counter(tipo.values())), "narrativas": len(filas_narr),
            "textos_reasignados": int(((narr_txt != narr_de_mc[mc]) & activo).sum()),
            "textos_largos_rescatados": int((es_gen_mc[mc] & ~generico_txt & (narr_txt >= 0)).sum()),
            "ruido": sum(1 for x in narr if not x)}
