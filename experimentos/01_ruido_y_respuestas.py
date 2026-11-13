import sys, numpy as np, duckdb, torch
from pathlib import Path
sys.path.insert(0, '.')
from qd.lago import Lago; from qd import embeddings
L = Lago(Path('./lake/practica'))
con = L.conectar()
V = './datos/practica/verdad/comentarios.csv.gz'
con.execute(f"create table c as select s.*, v.narrativa_id n, v.postura p from {L.leer('silver','comentarios')} s join read_csv('{V}', all_varchar=true) v using (comentario_id)")
print(con.sql("""select pa.n='ninguna' padre_ruido, h.n='ninguna' hijo_ruido, count(*) from c h join c pa on pa.comentario_id=h.respuesta_a group by all order by all"""))
print(con.sql("""select c.n='ninguna' ruido, c.es_respuesta, avg((select count(*) from c h where h.respuesta_a=c.comentario_id)) hijos_prom, count(*) from c group by all"""))
# texts of noise parents' replies
print(con.sql("""select h.texto_norm, count(*) from c h join c pa on pa.comentario_id=h.respuesta_a where pa.n='ninguna' group by 1 order by 2 desc limit 10"""))
# depth: replies to replies?
print(con.sql("""select count(*) from c h join c pa on pa.comentario_id=h.respuesta_a where pa.es_respuesta"""))
# micro clusters by threshold
ids, X = embeddings.cargar(L)
idx = {t:i for i,t in enumerate(ids)}
T = torch.tensor(X, device='mps')
K=15; nb=np.zeros((len(ids),K),dtype=np.int64); sm=np.zeros((len(ids),K),dtype=np.float32)
for s in range(0,len(ids),4096):
    S = T[s:s+4096] @ T.T
    v,i = torch.topk(S, K+1, dim=1)
    nb[s:s+4096]=i[:,1:].cpu().numpy(); sm[s:s+4096]=v[:,1:].cpu().numpy()
np.save('experimentos/cache/nb.npy', nb); np.save('experimentos/cache/sm.npy', sm)
# per text majority label
lab = dict(con.execute("select texto_id, mode(n||'/'||coalesce(p,'')) from c where not es_respuesta group by 1").fetchall())
w = dict(con.execute("select texto_id, count(*) from c where not es_respuesta group by 1").fetchall())
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
for th in [0.88,0.9,0.92,0.94]:
    r,cidx = np.nonzero(sm>=th); cols = nb[r,cidx]
    A = sp.coo_matrix((np.ones(len(r)),(r,cols)),shape=(len(ids),len(ids)))
    k, comp = connected_components(A, directed=False)
    # purity weighted by root comments
    from collections import Counter, defaultdict
    cnt=defaultdict(Counter)
    for t,i in idx.items():
        if t in lab: cnt[comp[i]][lab[t]]+=w[t]
    tot=sum(sum(c.values()) for c in cnt.values()); pur=sum(c.most_common(1)[0][1] for c in cnt.values())/tot
    big=sorted(cnt.values(), key=lambda c:-sum(c.values()))[:3]
    print(th, 'clusters',k, 'purity narr/postura', round(pur,4), 'biggest', [ (sum(c.values()), c.most_common(3)) for c in big])
