# Experimentos

Scripts de exploración que guiaron el diseño del pipeline. **No son parte del pipeline**: se
conservan para poder reproducir cada hallazgo. Se corren desde la raíz del repo, después de
`make practica` (leen `lake/practica` y la verdad de `datos/practica/verdad`). Los
intermedios pesados van a `experimentos/cache/` (ignorado por git).

| Script | Pregunta | Hallazgo | Dónde se usa |
|---|---|---|---|
| `01_ruido_y_respuestas.py` | ¿El ruido participa de las conversaciones? ¿Hay respuestas a respuestas? | El ruido nunca responde ni recibe respuestas; las respuestas heredan la narrativa del padre. Guarda los vecinos de cada texto. | tipo *ruido* de micro-cluster; asignación de respuestas |
| `02_umbral_microclusters.py` | ¿Umbral de similitud o Leiden para agrupar textos? | Umbrales fijos mezclan narrativas; Leiden con 10 vecinos da ~96% de pureza. | micro-clusters |
| `03_hilos_por_microcluster.py` | ¿Cómo se responden los micro-clusters entre sí? | ~80% de las respuestas cruzan de postura dentro de la misma narrativa. | narrativas por grafo de respuestas; corte máximo |
| `04_senales_de_postura.py` | ¿Qué distingue al lado que afirma? | La dirección de las respuestas es simétrica: no sirve. Los marcadores de refutación ayudan poco. | `qd/postura.py` |
| `05_postura_por_narrativa.py` | Precisión de postura y origen por narrativa | B3 y H3 invertidas. | diagnóstico |
| `06_campanas_en_clusters.py` | ¿Dónde caen los textos de campaña? | Los textos de C3 casi no reciben respuestas genuinas. | regla de campaña en postura |
| `07_coincidencias_por_ventana.py` | ¿Ventana de 10 o 30 minutos? ¿Mismo texto? | Contar coincidencias crudas confunde campañas con posteos virales. | ventana de 1800 s |
| `08_sorpresa_poisson_pares.py` | Coincidencias observadas frente a esperadas | La sorpresa Poisson separa campañas de pares genuinos muy activos. | `coordinacion.pares` |
| `09_umbral_nucleos.py` | ¿Qué umbral de sorpresa para los núcleos? | Componentes con ≥4 cuentas sobre un umbral tipo Bonferroni. | núcleos |
| `10_expansion_por_respuestas.py` | ¿Cómo rescatar C2 (cuentas viejas, textos variados)? | Sincronía con el grupo + respuestas entre sí. | expansión |
| `11_evaluar_coordinacion.py` | Barrido de parámetros de coordinación | Umbral global log10(cuentas·grupos) sin falsos positivos. | `PARAMS` de coordinación |
| `12_reglas_de_origen_cv.py` | ¿Qué regla de origen generaliza? (elige con train, mira test) | Sin textos genéricos y racha ∝ tamaño: train 0.81 → 0.95, test 0.49 → 0.82. | `narrativas.origen` |

Los scripts 01–11 se escribieron antes de separar train y test: miran toda la práctica.
