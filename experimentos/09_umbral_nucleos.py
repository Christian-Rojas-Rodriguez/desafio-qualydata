import pandas as pd, numpy as np, igraph as ig
from collections import Counter
df=pd.read_parquet('experimentos/cache/pares.parquet')
camp=dict(zip(df.a,df.ca)); camp.update(dict(zip(df.b,df.cb)))
tot=Counter({'C1':60,'C2':30,'C3':25})
for th in [3,4,5,6]:
    s=df[df.logp>=th]
    g=ig.Graph.TupleList(s[['a','b']].itertuples(index=False), directed=False)
    comps=[c for c in g.connected_components() if len(c)>=3]
    res=[]
    tp=fp=0
    for c in comps:
        names=[g.vs[i]['name'] for i in c]; cc=Counter(camp.get(n) or 'gen' for n in names)
        res.append(dict(cc)); tp+=sum(v for k,v in cc.items() if k!='gen'); fp+=cc.get('gen',0)
    print(f'th={th} aristas={len(s)} comps(>=3)={len(comps)} tp={tp} fp={fp} recall={tp/115:.2f}', sorted(res, key=lambda d:-sum(d.values()))[:8])
