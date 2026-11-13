import sys, time, duckdb
sys.path.insert(0,'.')
from pathlib import Path; from qd.lago import Lago; from qd import coordinacion
R='./'
L=Lago(Path(R+'lake/practica'))
params = eval(sys.argv[1]) if len(sys.argv)>1 else {}
t=time.time(); print(coordinacion.correr(L, params), round(time.time()-t,1),'s')
print(duckdb.sql(f"""select g.grupo, coalesce(v.campana_id,'GENUINA') camp, count(*) n, count(*) filter (where nucleo) nucleo
 from read_parquet('{R}lake/practica/gold/cuentas_grupo.parquet') g join read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true) v using (cuenta_id) group by all order by 1,2""").df().to_string())
