import duckdb, time, numpy as np
from scipy.stats import poisson
R='./'
con=duckdb.connect(); con.execute("SET TimeZone='America/Argentina/Buenos_Aires'")
con.execute(f"create view c0 as select *, epoch(ts) t from read_parquet('{R}lake/practica/silver/comentarios.parquet')")
con.execute(f"create table v as select cuenta_id, campana_id camp from read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true)")
W=1800
con.execute(f"create table c as select *, count(*) over (partition by publicacion_id order by t range between {W} preceding and {W} following) m from c0")
N=con.sql("select count(*) from c").fetchall()[0][0]
con.execute("create table acc as select cuenta_id, count(*) n, sum(m) M from c group by 1")
con.execute(f"""create table co as select a.cuenta_id a, b.cuenta_id b, count(distinct a.publicacion_id) k
      from c a join c b on a.publicacion_id=b.publicacion_id and a.cuenta_id<b.cuenta_id and abs(a.t-b.t)<={W} group by 1,2""")
df=con.sql(f"""select co.*, (xb.n*xa.M + xa.n*xb.M)/(2.0*{N}) E, va.camp ca, vb.camp cb from co join acc xa on xa.cuenta_id=a join acc xb on xb.cuenta_id=b
   join v va on va.cuenta_id=a join v vb on vb.cuenta_id=b where k>=2""").df()
df['logp']=-poisson.logsf(df.k-1, df.E)/np.log(10)
df['tipo']=np.where((df.ca!='')&(df.ca==df.cb),'misma', np.where((df.ca!='')|(df.cb!=''),'mixto','gen'))
print(df.groupby('tipo').logp.describe(percentiles=[.5,.9,.99,.999]).to_string())
for th in [6,8,10,12]:
    s=df[df.logp>=th]; print(th, s.tipo.value_counts().to_dict())
df.to_parquet('experimentos/cache/pares.parquet')
