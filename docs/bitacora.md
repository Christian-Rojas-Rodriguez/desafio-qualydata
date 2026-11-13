# Bitácora de decisiones

Cada cambio con su efecto. Hasta el 12/11 a la tarde se midió sobre toda la práctica (sin
separar train y test); desde entonces, ver [validacion.md](validacion.md).

| Fecha | Cambio | Medido en | Antes → después | Decisión |
|---|---|---|---|---|
| 11/11 | Línea base del repo (`ejemplos/linea_base.py`) | práctica | 16.95 | punto de partida |
| 11/11 | Bronze + silver con DuckDB/Parquet, 7 tests de datos sucios | tests | — | queda |
| 11/11 | Narrativas v1: embeddings + Leiden en dos niveles | práctica | 16.95 → 24.12 | queda |
| 12/11 | Postura con LLM local (Qwen 7B, dos consultas invertidas) | práctica | 24.12 → 28.47 | queda |
| 12/11 | Determinismo (orden y representantes estables) | dos corridas | 161–169 → 169 micro-clusters fijos | queda |
| 12/11 | Coordinación: sorpresa Poisson + núcleos + expansión | práctica | 28.5 → 52.59 | queda |
| 12/11 | Umbral de expansión adaptativo por grupo | práctica | metía una cuenta genuina en C3 | revertido: umbral global |
| 12/11 | Rescate de textos largos en grupos genéricos | práctica | 52.59 → 53.23 | queda |
| 12/11 | Refinamiento de postura por texto | práctica | 53.23 → 53.25 | queda |
| 12/11 | Lado de campaña por vecinos genuinos (H3) | práctica | sin mejora | revertido |
| 12/11 | Validación cruzada sin fugas (`qd/validacion.py`) | folds | ver validacion.md | queda |
| 12/11 | Origen: sin textos genéricos y racha ∝ tamaño (5 → max(5, 0,5%·n)) | origen en train / test | 0.81 → 0.95 / 0.49 → 0.82 | queda; práctica completa sigue en 53.25 |
| 12/11 | EDA documentado (`notebooks/01_eda_practica.ipynb`) y etapa `supuestos` que verifica en cada corrida lo que el EDA dio por cierto | práctica | 10/10 chequeos ok | queda; el viernes avisa si el final rompe alguno |

## Pendientes conocidos

- B3 y H3 con postura invertida (< 0,6 puntos en práctica).
- Coordinación marca cuentas genuinas cuando hay pocos datos o ninguna campaña.
