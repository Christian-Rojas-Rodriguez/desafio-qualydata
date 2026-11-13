import sys, numpy as np, duckdb, igraph as ig, leidenalg as la, time
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, '.')
from qd.lago import Lago; from qd import embeddings
S='experimentos/cache/'
L = Lago(Path('./lake/practica'))
con = L.conectar()
V = './datos/practica/verdad/comentarios.csv.gz'
con.execute(f"create table c as select s.*, v.narrativa_id n, v.postura p from {L.leer('silver','comentarios')} s join read_csv('{V}', all_varchar=true) v using (comentario_id)")
ids, X = embeddings.cargar(L); nb=np.load(S+'nb.npy'); sm=np.load(S+'sm.npy')
lab = dict(con.execute("select texto_id, mode(n||'/'||coalesce(p,'')) from c where not es_respuesta group by 1").fetchall())
w = dict(con.execute("select texto_id, count(*) from c where not es_respuesta group by 1").fetchall())
N=len(ids)
for K in [10]:
    src=np.repeat(np.arange(N),K); dst=nb[:,:K].ravel(); ww=sm[:,:K].ravel()
    g=ig.Graph(n=N, edges=list(zip(src.tolist(),dst.tolist())), directed=False); g.es['weight']=ww.tolist(); g=g.simplify(combine_edges='max')
    for res in [0.5, 1.0, 3.0]:
        t=time.time(); part=la.find_partition(g, la.RBConfigurationVertexPartition, weights='weight', resolution_parameter=res, seed=0)
        memb=np.array(part.membership)
        cnt=defaultdict(Counter)
        for i,tid in enumerate(ids):
            if tid in lab: cnt[memb[i]][lab[tid]]+=w[tid]
        tot=sum(sum(c.values()) for c in cnt.values()); pur=sum(c.most_common(1)[0][1] for c in cnt.values())/tot
        # narrative-only purity (ignoring stance)
        cn=defaultdict(Counter)
        for i,tid in enumerate(ids):
            if tid in lab: cn[memb[i]][lab[tid].split('/')[0]]+=w[tid]
        purn=sum(c.most_common(1)[0][1] for c in cn.values())/tot
        print(f'K={K} res={res} clusters={len(set(memb))} pureza narr+postura={pur:.4f} pureza narr={purn:.4f} {time.time()-t:.1f}s', flush=True)
        np.save(S+f'memb_{K}_{res}.npy', memb)
