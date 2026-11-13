"""Compara reglas de origen sobre las corridas de validación (elige con train, mira test)."""
import csv, sys, glob, collections, datetime as dt
import numpy as np, duckdb
R = "."

def cargar(modo, fold, parte):
    lago = f"{R}/lake/validacion/{modo}/{fold}/{parte}"
    sal = f"{R}/salida/validacion/{modo}/{fold}/{parte}"
    df = duckdb.sql(f"""select g.comentario_id, g.narrativa, g.tipo_cluster, epoch(s.ts) t, s.respuesta_a is not null es_resp
        from read_parquet('{lago}/gold/comentarios_narrativa.parquet') g join read_parquet('{lago}/silver/comentarios.parquet') s using(comentario_id)
        where g.narrativa <> ''""").df()
    v = {r['comentario_id']: r['narrativa_id'] for r in csv.DictReader(open(f"{sal}/verdad/comentarios.csv"))}
    emerg = {r['narrativa_id']: dt.datetime.fromisoformat(r['fecha_origen']).timestamp()
             for r in csv.DictReader(open(f"{sal}/verdad/narrativas.csv")) if r['emergente'] == 'si'}
    df['verdad'] = df.comentario_id.map(v)
    return df, emerg

def puntaje(err_h): return 1.0 if err_h <= 3 else max(0.0, 1 - (err_h - 3) / 45)

REGLAS = {}
def regla(nombre):
    def deco(f): REGLAS[nombre] = f; return f
    return deco

def racha(t, ventana, minimo):
    fin = np.searchsorted(t, t + ventana, side="right")
    r = np.nonzero(fin - np.arange(len(t)) >= minimo)[0]
    return t[r[0]] if len(r) else t[0]

@regla("actual 5/6h")
def _(g): return racha(np.sort(g.t.values) / 3600, 6, 5)
for frac in (0.002, 0.005, 0.01, 0.02):
    REGLAS[f"max(5,{frac}n)/6h"] = (lambda frac: lambda g: racha(np.sort(g.t.values) / 3600, 6, max(5, int(frac * len(g)))))(frac)
@regla("solo raíces 5/6h")
def _(g): return racha(np.sort(g[~g.es_resp].t.values) / 3600, 6, 5)
@regla("sin genericos 5/6h")
def _(g):
    x = g[g.tipo_cluster == 'narrativa']; x = x if len(x) else g
    return racha(np.sort(x.t.values) / 3600, 6, 5)
for frac in (0.005, 0.01):
    REGLAS[f"sin genericos max(5,{frac}n)/6h"] = (lambda frac: lambda g: (lambda x: racha(np.sort(x.t.values) / 3600, 6, max(5, int(frac * len(x)))))(g[g.tipo_cluster == 'narrativa'] if (g.tipo_cluster == 'narrativa').any() else g))(frac)

corridas = []
for path in sorted(glob.glob(f"{R}/salida/validacion/*/*/*/verdad")):
    modo, fold, parte = path.split("/")[-4:-1]
    if modo == "etiquetas": continue
    corridas.append((modo, fold, parte))
res = collections.defaultdict(lambda: collections.defaultdict(list))
for modo, fold, parte in corridas:
    df, emerg = cargar(modo, fold, parte)
    for n, t0 in emerg.items():
        sub = df[df.verdad == n]
        if not len(sub): continue
        cl = sub.narrativa.value_counts().index[0]
        g = df[df.narrativa == cl]
        for nombre, f in REGLAS.items():
            err = abs(f(g) * 3600 - t0) / 3600 if nombre else 0
            res[nombre][parte].append(puntaje(err))
            if nombre == "actual 5/6h" and err > 3:
                print(f"  {modo}/{fold}/{parte} {n}: err {err:.1f} h (n={len(g)})")
for nombre in REGLAS:
    print(f"{nombre:<34} train={np.mean(res[nombre]['train']):.3f} (n={len(res[nombre]['train'])})  test={np.mean(res[nombre]['test']):.3f} (n={len(res[nombre]['test'])})")
