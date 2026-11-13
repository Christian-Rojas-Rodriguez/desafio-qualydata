# Validación

El pipeline no aprende de etiquetas: lo que se "entrena" son nuestras decisiones (parámetros,
reglas). Hay fuga si elegimos una decisión mirando las mismas etiquetas con las que después
reportamos. **Regla: las decisiones se toman con métricas de train; test solo se reporta.**

## Cómo se separa (`python -m qd.validacion --modo ...`)

- **Unidad de corte: la publicación.** Las respuestas nunca salen de su publicación
  (verificado: 0 casos), así que cada conversación queda entera de un lado.
- **5 folds 80/20 estratificados por tema**: cada parte tiene los tres temas.
- **Verdad de cada parte**: el origen se recalcula dentro de la parte; las cuentas de campaña
  que en esa parte solo comentan como "cobertura" (fuera de la narrativa de su operación) no se
  evalúan.

| Modo | Qué hace | Qué prueba |
|---|---|---|
| `etiquetas` | Una corrida sobre todo el set; las métricas se calculan aparte con etiquetas de train y de test. | Variabilidad entre folds. |
| `datos` | El pipeline corre desde cero sobre el 80% y sobre el 20%, en lagos separados. | Que los umbrales se adapten al tamaño. El 80% (~160k) tiene el tamaño del set final (~150k). |
| `tema` | El pipeline corre sobre un solo tema. | Lo más parecido a "temas y campañas nuevos". Colectivo no tiene campaña: prueba falsos positivos. |

## ¿Las cuentas cruzan de lado?

Sí: el 99% de los comentarios de test son de cuentas que también comentan en train, y C1 y C2
tienen cuentas en ambos lados. No es fuga (cada parte corre desde cero y sin etiquetas), pero
el test es optimista para campañas nuevas. No se puede cortar por cuenta sin partir hilos y
campañas; el modo `tema` es la aproximación a "cuentas y campañas nuevas".

## Resultados (12 nov, antes de corregir el origen)

| Prueba | Total /55 | B-cubed | Postura | Origen | F1 cuentas | Genuinas marcadas |
|---|---|---|---|---|---|---|
| Etiquetas, test | 53.3 ± 1.0 | 0.994 | 0.90 | 1.00 | 0.97 | 0 |
| Datos, 80% (tamaño final) | 51.9 ± 0.6 | 0.991 | 0.97 | 0.87 | 0.94 | 1.2 |
| Datos, 20% | 39.0 ± 5.3 | 0.981 | 0.88 | 0.52 | 0.55 | 7.4 |
| Tema oculto | 42.7 ± 11 | 0.995 | 0.996 | 0.33 | 0.64 | 5 |

Lectura:
- **El agrupamiento generaliza**: 0.98–1.0 en todo, y encuentra la cantidad exacta de
  narrativas en temas ocultos.
- **Origen de emergentes**: fallaba con menos datos; corregido (ver bitácora).
- **Coordinación con pocos datos o sin campaña**: aparecían cuentas genuinas marcadas (6 en
  colectivo, 9 en litio, 35 en un fold de 20%), todas en núcleos falsos: cadenas de 4–6
  cuentas unidas por pares que coinciden solo 2 veces. Corregido exigiendo núcleos densos
  (2-core), elegido con train: genuinas 7 → 3, puntos 23.59 → 23.65; en test genuinas
  52 → 7 y ningún grupo falso (`experimentos/13_coordinacion_cv.py`).
- **El recall de test sigue bajo (0.3–0.6)** y es falta de datos, no del método: en el 20%
  muchas cuentas de campaña tienen un solo comentario, y C2 (cuentas viejas repartidas en
  muchas publicaciones) casi no coincide. En train (160k comentarios, tamaño parecido al
  final) C1 y C3 salen casi completas; a C2 le faltan 2–9 cuentas de 30.
