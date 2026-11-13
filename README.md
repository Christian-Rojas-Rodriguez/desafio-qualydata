# QualyData: narrativas y coordinación

Solución al [Desafío QualyData](docs/consigna.md) del Hackathon Argentina Space 2026.
A partir de comentarios en redes, descubre qué **narrativas** circulan, quién las apoya o las
rechaza y desde cuándo, y detecta las **cuentas coordinadas** que las empujan.

- **Un comando**, de punta a punta, sin servidor y sin claves.
- **US$0 de IA**: embeddings y LLM corren locales; ~2 minutos para 200k comentarios en una Mac.
- **53.25 / 55** en la parte automática del set de práctica; **51.9 ± 0.6** en validación
  cruzada corriendo desde cero sobre el 80% de los datos, y **53.36** entrenando con los
  primeros 12 días ([docs/validacion.md](docs/validacion.md)).
- **Set final** (`entrega/`): 150.000 comentarios en ~100 s desde cero (se reproduce byte a byte con `make verificar`), 12 narrativas,
  17,8% de ruido, 3 operaciones coordinadas con 94 cuentas, 10/10 supuestos del EDA verificados.

## Cómo correr

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
make practica    # pipeline sobre datos/practica y puntaje
make final       # pipeline sobre datos/final → entrega/
make verificar   # re-corre el final desde cero y compara con las huellas SHA256 de costo.json
make tablero     # docs/resultados.html: qué circula, desde cuándo y quién lo empuja
```

Sin `make`:

```bash
.venv/bin/python -m qd --datos datos/final --entrega entrega
```

El LLM es opcional (`QD_LLM=mlx` en Mac con Apple Silicon; `QD_LLM=none` para correr sin él).
Las claves, si alguna vez hacen falta, van en `.env` (ignorado); ver `.env.example`.

## Cómo está organizado

```
qd/            el pipeline (un módulo por etapa; mapa en docs/arquitectura.md)
docs/          consigna, arquitectura, método, diccionario de datos, validación, bitácora
notebooks/     análisis exploratorio (EDA)
experimentos/  scripts de exploración que guiaron cada decisión
tests/         datos sucios: el pipeline no pierde filas ni se rompe
evaluacion/    puntuador oficial (de la organización, sin cambios)
ejemplos/      línea base oficial (de la organización, sin cambios)
datos/         sets de entrada (datos/final no se versiona)
lake/          capas bronze/silver/gold en Parquet (se regeneran; no se versionan)
entrega/       resultado sobre el set final
```

| Para entender... | Leé |
|---|---|
| **Qué encontramos en el set final** (abrir en el navegador) | [docs/resultados.html](docs/resultados.html) |
| Qué piden y cómo puntúa | [docs/consigna.md](docs/consigna.md) |
| Cómo fluyen los datos y qué hace cada módulo | [docs/arquitectura.md](docs/arquitectura.md) |
| Qué tabla y columna hay en cada capa | [docs/datos.md](docs/datos.md) |
| Cómo se detectan narrativas, postura y coordinación | [docs/metodo.md](docs/metodo.md) |
| Qué se valida en los datos y cómo se reproduce la entrega | [docs/contrato.md](docs/contrato.md) |
| Cuánto generaliza y cómo lo medimos | [docs/validacion.md](docs/validacion.md) |
| Por qué cada decisión | [docs/bitacora.md](docs/bitacora.md) |

## Dónde guardamos los datos y por qué

DuckDB sobre Parquet, en capas **bronze** (copia fiel), **silver** (limpio y tipado) y
**gold** (resultados). Embebido y columnar: no hay servidor, el jurado clona y corre, y las
consultas pesadas (millones de pares de cuentas) tardan segundos. El Parquet lo lee cualquier
herramienta, y el mismo SQL escala a Parquet particionado por día en un bucket. Detalle y plan
de escala en [docs/arquitectura.md](docs/arquitectura.md).

## Qué existía antes del evento

Todo el código de `qd/`, `tests/`, `notebooks/` y `experimentos/` se escribió durante el
hackathon. `evaluacion/puntuar.py` y `ejemplos/linea_base.py` son de la organización.
Librerías públicas: DuckDB, PyArrow, pandas, NumPy, SciPy, scikit-learn, PyTorch,
sentence-transformers (modelo `intfloat/multilingual-e5-small`), python-igraph, leidenalg y
mlx-lm (modelo `mlx-community/Qwen2.5-7B-Instruct-4bit`).
