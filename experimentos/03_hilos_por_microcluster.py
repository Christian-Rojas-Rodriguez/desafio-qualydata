import sys, numpy as np, duckdb, pandas as pd
from pathlib import Path
sys.path.insert(0, '.')
from qd.lago import Lago; from qd import embeddings
S='experimentos/cache/'
L = Lago(Path('./lake/practica'))
con = L.conectar()
V = './datos/practica/verdad/comentarios.csv.gz'
ids,_ = embeddings.cargar(L); memb=np.load(S+'memb_10_1.0.npy')
con.register('mc', pd.DataFrame({'texto_id':ids,'mc':memb}))
con.execute(f"create table c as select s.*, v.narrativa_id n, v.postura p, mc.mc from {L.leer('silver','comentarios')} s join read_csv('{V}', all_varchar=true) v using (comentario_id) join mc using (texto_id)")
con.execute("create table hijos as select respuesta_a id, count(*) k from c where respuesta_a is not null group by 1")
# cluster stats
print(con.sql("""select round(frr,1) fr, count(*) clusters, sum(n) com from (select mc, count(*) n, avg(es_respuesta::int) frr from c group by mc) group by round(frr,1) order by 1""").df().to_string())
# reply direction: for opposite-stance replies, parent stance
print(con.sql("""select pa.p padre, h.p hijo, count(*) from c h join c pa on pa.comentario_id=h.respuesta_a group by all order by all"""))
print(con.sql("""select p, es_respuesta, count(*) from c where n<>'ninguna' group by all order by all"""))
# noise clusters: involvement
print(con.sql("""select mc, count(*) n, avg(es_respuesta::int) fr, avg((h.k is not null)::int) fh, mode(n) maj from c left join hijos h on h.id=c.comentario_id group by mc having maj='ninguna' order by n desc""").df().describe().to_string())
