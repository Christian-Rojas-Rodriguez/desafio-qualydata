import duckdb, time
R='./'
con=duckdb.connect(); con.execute("SET TimeZone='America/Argentina/Buenos_Aires'")
con.execute(f"create view c as select * from read_parquet('{R}lake/practica/silver/comentarios.parquet')")
con.execute(f"create table v as select cuenta_id, campana_id camp from read_csv('{R}datos/practica/verdad/cuentas.csv.gz', all_varchar=true)")
con.execute(f"create table g as select comentario_id, micro_cluster mc, narrativa from read_parquet('{R}lake/practica/gold/comentarios_narrativa.parquet')")
t=time.time()
for W in [600, 1800]:
    con.execute(f"""create or replace table co as select a.cuenta_id a, b.cuenta_id b, count(distinct a.publicacion_id) pubs,
       count(*) filter (where a.texto_id=b.texto_id) mismo_texto
      from c a join c b on a.publicacion_id=b.publicacion_id and a.cuenta_id<b.cuenta_id and abs(epoch(a.ts)-epoch(b.ts))<={W}
      group by 1,2""")
    print('W',W,'pares',con.sql("select count(*) from co").fetchall(), round(time.time()-t,1),'s')
    print(con.sql("""select case when va.camp<>'' and va.camp=vb.camp then 'misma_camp' when va.camp<>'' or vb.camp<>'' then 'mixto' else 'genuino' end tipo,
        count(*) pares, quantile_cont(pubs,[0.5,0.9,0.99,0.999]) q, max(pubs), count(*) filter (where pubs>=3) ge3, count(*) filter (where pubs>=5) ge5
        from co join v va on va.cuenta_id=a join v vb on vb.cuenta_id=b group by 1""").df().to_string())
# reply pairs
con.execute("""create table rp as select least(h.cuenta_id,p.cuenta_id) a, greatest(h.cuenta_id,p.cuenta_id) b, count(*) n from c h join c p on p.comentario_id=h.respuesta_a where h.cuenta_id<>p.cuenta_id group by 1,2""")
print(con.sql("""select case when va.camp<>'' and va.camp=vb.camp then 'misma_camp' when va.camp<>'' or vb.camp<>'' then 'mixto' else 'genuino' end tipo, n, count(*) from rp join v va on va.cuenta_id=a join v vb on vb.cuenta_id=b group by all order by 1,2""").df().to_string())
# activity per account
print(con.sql("""select coalesce(nullif(v.camp,''),'gen') camp, count(distinct c.cuenta_id) cuentas, quantile_cont(n,[0.1,0.5,0.9]) q from (select cuenta_id, count(*) n from c group by 1) c join v using (cuenta_id) group by 1""").df().to_string())
