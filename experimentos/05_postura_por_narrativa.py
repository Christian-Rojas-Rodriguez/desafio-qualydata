import duckdb
R='./'
con=duckdb.connect(); con.execute("SET TimeZone='America/Argentina/Buenos_Aires'")
con.execute(f"""create table j as select g.*, v.narrativa_id n, v.postura p, s.es_respuesta, s.ts, s.texto_norm
 from read_parquet('{R}lake/practica/gold/comentarios_narrativa.parquet') g
 join read_csv('{R}datos/practica/verdad/comentarios.csv.gz', all_varchar=true) v using (comentario_id)
 join read_parquet('{R}lake/practica/silver/comentarios.parquet') s using (comentario_id)""")
con.execute("create table m as select narrativa, mode(n) n from j where narrativa<>'' group by 1")
print(con.sql("""select j.narrativa, m.n, count(*) filter (where postura=p) ok, count(*) filter (where postura<>p and p<>'') mal,
  round(count(*) filter (where postura=p)*1.0/count(*) filter (where p<>''),3) acc,
  round(count(*) filter (where postura=p and not es_respuesta)*1.0/count(*) filter (where p<>'' and not es_respuesta),3) acc_raiz,
  round(count(*) filter (where postura=p and es_respuesta)*1.0/count(*) filter (where p<>'' and es_respuesta),3) acc_resp
  from j join m using (narrativa) group by all order by 1""").df().to_string())
print(con.sql(f"""select n.narrativa, m.n, n.fecha_origen, v.fecha_origen verdad, n.titulo
  from read_parquet('{R}lake/practica/gold/narrativas.parquet') n join m using (narrativa)
  join read_csv('{R}datos/practica/verdad/narrativas.csv', all_varchar=true) v on v.narrativa_id=m.n order by 1""").df().to_string())
for nar, n, t in [('n06','L5','2026-09-07 08:17:26-03'),('n10','B4','2026-09-10 21:32:05-03'),('n12','H3','2026-09-06 01:12:04-03')]:
    print(nar, n)
    print(con.sql(f"""select date_trunc('day', ts) dia, count(*) total, count(*) filter (where n='{n}') bien, any_value(texto_norm) filter (where n<>'{n}') ej_mal, mode(n) filter (where n<>'{n}') verdad_mal, mode(micro_cluster) filter (where n<>'{n}') mc_mal
      from j where narrativa='{nar}' and ts < timestamptz '{t}' + interval 1 day group by 1 order by 1""").df().to_string())
