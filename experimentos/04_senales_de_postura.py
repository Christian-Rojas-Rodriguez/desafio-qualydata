import duckdb, sys
sys.path.insert(0,'.')
from qd.postura import MARCADORES_REFUTACION
R='./'
con=duckdb.connect()
con.execute(f"""create table j as select v.narrativa_id n, v.postura p, s.*, (select count(*) from read_parquet('{R}lake/practica/silver/comentarios.parquet') h where h.respuesta_a=s.comentario_id) hijos
 from read_parquet('{R}lake/practica/silver/comentarios.parquet') s join read_csv('{R}datos/practica/verdad/comentarios.csv.gz', all_varchar=true) v using (comentario_id) where v.narrativa_id<>'ninguna'""")
lex = " or ".join(f"contains(texto_norm, '{m}')" for m in MARCADORES_REFUTACION)
print(con.sql(f"""select n, p, count(*) c, round(avg(es_respuesta::int),3) frac_resp, round(avg((hijos>0)::int),3) frac_hijos,
 round(avg(me_gusta),2) likes, round(avg(({lex})::int),3) lex, round(avg(n_tokens),1) tok, min(ts) primero,
 round(avg(contains(texto_norm,'pero')::int),3) pero
 from j group by all order by n,p""").df().to_string())
