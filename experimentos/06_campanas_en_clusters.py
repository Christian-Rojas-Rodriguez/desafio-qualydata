import duckdb
R='./'
con=duckdb.connect()
con.execute(f"""create table j as select g.*, v.narrativa_id n, v.postura p, s.es_respuesta, s.texto_norm, s.cuenta_id, coalesce(vc.campana_id,'') camp, gr.grupo
 from read_parquet('{R}lake/practica/gold/comentarios_narrativa.parquet') g
 join read_csv('{R}datos/practica/verdad/comentarios.csv.gz', all_varchar=true) v using (comentario_id)
 join read_parquet('{R}lake/practica/silver/comentarios.parquet') s using (comentario_id)
 join read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true) vc using (cuenta_id)
 left join read_parquet('{R}lake/practica/gold/cuentas_grupo.parquet') gr using (cuenta_id)""")
print(con.sql("""select camp, tipo_cluster, narrativa<>'' asignado, es_respuesta, count(*) from j where camp<>'' group by all order by all""").df().to_string())
print(con.sql("""select micro_cluster, tipo_cluster, count(*) n, count(*) filter (where camp<>'') camp, mode(n||'/'||coalesce(p,'')) verdad, any_value(texto_norm) from j where camp='C1' or micro_cluster in (select micro_cluster from j where camp='C1') group by 1,2 order by camp desc limit 8""").df().to_string())
print('--- H3 nodos')
print(con.sql("""select micro_cluster, postura, count(*) n, count(*) filter (where p='apoya') v_apoya, count(*) filter (where p='rechaza') v_rech, count(*) filter (where grupo is not null and not es_respuesta) coord_raiz, any_value(texto_norm) from j where narrativa=(select mode(narrativa) from j where n='H3') group by 1,2 order by n desc""").df().to_string())
print('--- H3 por campaña/postura')
print(con.sql("""select camp, es_respuesta, p verdad, postura nuestra, count(*) from j where n='H3' group by all order by all""").df().to_string())
print(con.sql(f"""with c as (select * from read_parquet('{R}lake/practica/silver/comentarios.parquet'))
 select coalesce(vc.campana_id,'gen') quien_responde, jh.p postura_resp, count(*) from j jp join c h on h.respuesta_a=jp.comentario_id join j jh on jh.comentario_id=h.comentario_id
 join read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true) vc on vc.cuenta_id=h.cuenta_id
 where jp.camp='C3' group by all""").df().to_string())
