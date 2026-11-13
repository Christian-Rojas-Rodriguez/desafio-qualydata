import pandas as pd, numpy as np, igraph as ig, duckdb
from collections import Counter, defaultdict
R='./'
df=pd.read_parquet('experimentos/cache/pares.parquet')
v=dict(duckdb.sql(f"select cuenta_id, coalesce(campana_id,'') from read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true)").fetchall())
rp=duckdb.sql(f"""with c as (select * from read_parquet('{R}lake/practica/silver/comentarios.parquet'))
 select least(h.cuenta_id,p.cuenta_id) a, greatest(h.cuenta_id,p.cuenta_id) b, count(*) n from c h join c p on p.comentario_id=h.respuesta_a where h.cuenta_id<>p.cuenta_id group by 1,2""").df()
s=df[df.logp>=5]; g=ig.Graph.TupleList(s[['a','b']].itertuples(index=False), directed=False)
cores=[set(g.vs[i]['name'] for i in c) for c in g.connected_components() if len(c)>=3]
grupo={a:i for i,c in enumerate(cores) for a in c}
ev=defaultdict(lambda: defaultdict(float)); ne=defaultdict(lambda: defaultdict(int)); rr=defaultdict(lambda: defaultdict(int))
for a,b,lp in df[df.logp>=1.5][['a','b','logp']].itertuples(index=False):
    for x,y in ((a,b),(b,a)):
        if y in grupo and x not in grupo: ev[x][grupo[y]]+=lp; ne[x][grupo[y]]+=1
for a,b,n in rp.itertuples(index=False):
    for x,y in ((a,b),(b,a)):
        if y in grupo and x not in grupo: rr[x][grupo[y]]+=n
rows=[]
for x in set(ev)|set(rr):
    for gi in set(ev[x])|set(rr[x]):
        rows.append(dict(cuenta=x, g=gi, ev=ev[x][gi], ne=ne[x][gi], rr=rr[x][gi], camp=v.get(x,''), gcamp=Counter(v[a] for a in cores[gi]).most_common(1)[0][0]))
r=pd.DataFrame(rows); r['es']=r.camp==r.gcamp
print('candidatos', len(r), 'de campaña', r.es.sum())
print(r[r.es].sort_values('ev').to_string())
print(r[~r.es].sort_values('ev', ascending=False).head(15).to_string())
age=dict(duckdb.sql(f"select cuenta_id, antiguedad_dias from read_parquet('{R}lake/practica/silver/cuentas.parquet')").fetchall())
nc=dict(duckdb.sql(f"select cuenta_id, count(*) from read_parquet('{R}lake/practica/silver/comentarios.parquet') group by 1").fetchall())
r['edad']=r.cuenta.map(age); r['n']=r.cuenta.map(nc); r['tam']=r.g.map(lambda i: len(cores[i]))
r['frac']=r['ne']/r['tam']; r['ev_por_com']=r['ev']/r['n']
for gi,c in enumerate(cores):
    print('grupo',gi,'tam',len(c),'edad core', np.percentile([age[a] for a in c],[0,50,100]), 'n core', np.percentile([nc[a] for a in c],[0,50,100]))
    sub=r[r.g==gi]
    print(sub.groupby('es')[['ev','ne','rr','edad','n','frac','ev_por_com']].describe(percentiles=[.5,.9,.99]).T.to_string())
