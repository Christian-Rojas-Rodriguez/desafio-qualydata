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
| 12/11 | Coordinación: núcleo solo si su 2-core tiene ≥ 4 cuentas (las cadenas sueltas de genuinas no cuentan) | coord. en train / test | genuinas 7 → 3, 23.59 → 23.65 / genuinas 52 → 7, 14.14 → 14.16 | queda; práctica completa sigue en 53.25 |
| 13/11 | Validación con corte temporal (`--modo dias`) | días 1–12 / 12–14 | train 53.36; test: B-cubed 0.968, postura 0.749, 0 genuinas marcadas | queda; ver validacion.md |
| 13/11 | Desempate de postura por probabilidad del LLM (en vez de marcadores) | 7 partes train | indecisas 8/11 → 3/11; total 83/90 → 78/90 | revertido: quedan los marcadores |
| 13/11 | Título de respaldo: afirmación más repetida, sin preguntas | práctica | solo cambia títulos | queda |

## Pendientes conocidos

- B3 y H3 con postura invertida (< 0,6 puntos en práctica). En el corte temporal también L2:
  sin campaña visible, el LLM no decide y los marcadores eligen mal.
- C2 (cuentas viejas, textos variados) pierde 2–9 de 30 cuentas en train y casi desaparece
  con el 20% de los datos.
