# Diccionario de datos

Generado con `python -m qd.diccionario --lago lake/practica`. Filas del set de práctica.

Todas las capas son Parquet (zstd) en `lake/<set>/<capa>/<tabla>.parquet`; `lake/<set>/catalogo.duckdb` las expone como vistas `bronze.*`, `silver.*` y `gold.*`.

## bronze

Copia fiel de los CSV: todo como texto, más de dónde vino cada fila. Nunca se pierde nada.

### `bronze/comentarios` (200.000 filas)

Comentarios tal cual llegan. `_archivo`, `_fila`, `_hash` e `_ingesta` permiten rastrear cada fila.

| Columna | Tipo | Descripción |
|---|---|---|
| `comentario_id` | VARCHAR |  |
| `publicacion_id` | VARCHAR |  |
| `cuenta_id` | VARCHAR |  |
| `fecha` | VARCHAR |  |
| `texto` | VARCHAR |  |
| `respuesta_a` | VARCHAR |  |
| `me_gusta` | VARCHAR |  |
| `_archivo` | VARCHAR |  |
| `_fila` | BIGINT |  |
| `_hash` | VARCHAR |  |
| `_ingesta` | TIMESTAMP WITH TIME ZONE |  |

### `bronze/cuentas` (15.991 filas)

Cuentas tal cual llegan.

| Columna | Tipo | Descripción |
|---|---|---|
| `cuenta_id` | VARCHAR |  |
| `usuario` | VARCHAR |  |
| `fecha_creacion` | VARCHAR |  |
| `seguidores` | VARCHAR |  |
| `siguiendo` | VARCHAR |  |
| `_archivo` | VARCHAR |  |
| `_fila` | BIGINT |  |
| `_hash` | VARCHAR |  |
| `_ingesta` | TIMESTAMP WITH TIME ZONE |  |

### `bronze/fuentes` (8 filas)

Medios, radios, comunidades e instituciones.

| Columna | Tipo | Descripción |
|---|---|---|
| `fuente_id` | VARCHAR |  |
| `nombre` | VARCHAR |  |
| `tipo` | VARCHAR |  |
| `_archivo` | VARCHAR |  |
| `_fila` | BIGINT |  |
| `_hash` | VARCHAR |  |
| `_ingesta` | TIMESTAMP WITH TIME ZONE |  |

### `bronze/publicaciones` (506 filas)

Publicaciones tal cual llegan.

| Columna | Tipo | Descripción |
|---|---|---|
| `publicacion_id` | VARCHAR |  |
| `fuente_id` | VARCHAR |  |
| `fecha` | VARCHAR |  |
| `titular` | VARCHAR |  |
| `_archivo` | VARCHAR |  |
| `_fila` | BIGINT |  |
| `_hash` | VARCHAR |  |
| `_ingesta` | TIMESTAMP WITH TIME ZONE |  |

### `bronze/rechazos_csv` (0 filas)

Líneas que el lector de CSV no pudo interpretar (comillas rotas, columnas de más).

| Columna | Tipo | Descripción |
|---|---|---|
| `tabla` | VARCHAR |  |
| `linea` | BIGINT |  |
| `tipo` | VARCHAR |  |
| `mensaje` | VARCHAR |  |
| `contenido` | VARCHAR |  |

## silver

Datos limpios y tipados: fechas en hora argentina, números validados, texto normalizado, duplicados resueltos y cada problema anotado en `flags`.

### `silver/calidad` (1 filas)

Cuántas filas tienen cada problema de calidad.

| Columna | Tipo | Descripción |
|---|---|---|
| `tabla` | VARCHAR |  |
| `chequeo` | VARCHAR |  |
| `filas` | BIGINT |  |

### `silver/comentarios` (200.000 filas)

Un comentario por fila, limpio. Base de todo el análisis.

| Columna | Tipo | Descripción |
|---|---|---|
| `comentario_id` | VARCHAR |  |
| `publicacion_id` | VARCHAR |  |
| `cuenta_id` | VARCHAR |  |
| `ts` | TIMESTAMP WITH TIME ZONE | Fecha y hora con zona horaria (America/Argentina/Buenos_Aires). |
| `hora_local` | BIGINT |  |
| `dia_local` | DATE |  |
| `respuesta_a` | VARCHAR |  |
| `es_respuesta` | BOOLEAN | Si `respuesta_a` apunta a otro comentario. |
| `me_gusta` | BIGINT |  |
| `texto` | VARCHAR |  |
| `texto_limpio` | VARCHAR | Texto sin URLs, menciones ni emojis; hashtags separados en palabras. |
| `texto_norm` | VARCHAR | Minúsculas, sin acentos (salvo ñ), sin signos, abreviaturas expandidas. Se usa para comparar. |
| `texto_id` | VARCHAR | md5 de `texto_norm`: mismo texto normalizado, mismo id. |
| `n_tokens` | INTEGER |  |
| `es_pregunta` | BOOLEAN |  |
| `hashtags` | VARCHAR[] |  |
| `emojis` | VARCHAR[] |  |
| `n_urls` | INTEGER |  |
| `n_menciones` | INTEGER |  |
| `prop_mayusculas` | FLOAT |  |
| `flags` | VARCHAR[] | Problemas de calidad de la fila (fecha imputada, cuenta desconocida, texto vacío...). |

### `silver/cuentas` (15.991 filas)

Cuentas con antigüedad calculada; incluye las que solo aparecen en comentarios (flag `sin_perfil`).

| Columna | Tipo | Descripción |
|---|---|---|
| `cuenta_id` | VARCHAR |  |
| `usuario` | VARCHAR |  |
| `fecha_creacion` | DATE |  |
| `antiguedad_dias` | BIGINT |  |
| `seguidores` | BIGINT |  |
| `siguiendo` | BIGINT |  |
| `activa` | BOOLEAN |  |
| `flags` | VARCHAR[] | Problemas de calidad de la fila (fecha imputada, cuenta desconocida, texto vacío...). |

### `silver/fuentes` (8 filas)

Fuentes limpias.

| Columna | Tipo | Descripción |
|---|---|---|
| `fuente_id` | VARCHAR |  |
| `nombre` | VARCHAR |  |
| `tipo` | VARCHAR |  |

### `silver/publicaciones` (506 filas)

Publicaciones con fecha tipada.

| Columna | Tipo | Descripción |
|---|---|---|
| `publicacion_id` | VARCHAR |  |
| `fuente_id` | VARCHAR |  |
| `ts` | TIMESTAMP WITH TIME ZONE | Fecha y hora con zona horaria (America/Argentina/Buenos_Aires). |
| `titular` | VARCHAR |  |
| `flags` | VARCHAR[] | Problemas de calidad de la fila (fecha imputada, cuenta desconocida, texto vacío...). |

### `silver/rechazos` (0 filas)

Filas descartadas en la deduplicación y por qué.

| Columna | Tipo | Descripción |
|---|---|---|
| `tabla` | VARCHAR |  |
| `_fila` | BIGINT |  |
| `_hash` | VARCHAR |  |
| `id` | VARCHAR |  |
| `motivo` | VARCHAR |  |

### `silver/textos` (58.344 filas)

Un texto normalizado único por fila (58k textos para 200k comentarios: hay mucha repetición).

| Columna | Tipo | Descripción |
|---|---|---|
| `texto_id` | VARCHAR | md5 de `texto_norm`: mismo texto normalizado, mismo id. |
| `texto_norm` | VARCHAR | Minúsculas, sin acentos (salvo ñ), sin signos, abreviaturas expandidas. Se usa para comparar. |
| `texto_limpio` | VARCHAR | Texto sin URLs, menciones ni emojis; hashtags separados en palabras. |
| `n_tokens` | INTEGER |  |
| `n_comentarios` | BIGINT |  |
| `n_cuentas` | BIGINT |  |
| `n_publicaciones` | BIGINT |  |
| `primera_vez` | TIMESTAMP WITH TIME ZONE |  |

## gold

Resultados del análisis: narrativas, postura, coordinación. De acá sale la entrega.

### `gold/comentarios_narrativa` (200.000 filas)

Narrativa y postura asignadas a cada comentario.

| Columna | Tipo | Descripción |
|---|---|---|
| `comentario_id` | VARCHAR |  |
| `narrativa` | VARCHAR |  |
| `postura` | VARCHAR |  |
| `micro_cluster` | BIGINT |  |
| `tipo_cluster` | VARCHAR | narrativa, generico ("totalmente de acuerdo") o ruido. |

### `gold/cuentas_grupo` (109 filas)

Cuentas coordinadas y su operación; `nucleo` indica si entró por pares fuertes o por expansión.

| Columna | Tipo | Descripción |
|---|---|---|
| `cuenta_id` | VARCHAR |  |
| `grupo` | VARCHAR |  |
| `nucleo` | BOOLEAN | true si la cuenta entró por pares fuertes; false si se sumó por sincronía con el grupo. |

### `gold/embeddings` (58.344 filas)

Vector semántico (multilingual-e5-small, 384 dims) de cada texto único.

| Columna | Tipo | Descripción |
|---|---|---|
| `texto_id` | VARCHAR | md5 de `texto_norm`: mismo texto normalizado, mismo id. |
| `vector` | FLOAT[] |  |

### `gold/micro_clusters` (169 filas)

Grupos de textos casi iguales (Leiden sobre vecinos) y su tipo: narrativa, genérico o ruido.

| Columna | Tipo | Descripción |
|---|---|---|
| `micro_cluster` | BIGINT |  |
| `tipo` | VARCHAR |  |
| `narrativa_inicial` | VARCHAR |  |
| `participacion` | DOUBLE |  |

### `gold/narrativas` (13 filas)

Una fila por narrativa: título, frases clave, origen, tamaño y cómo se decidió la postura.

| Columna | Tipo | Descripción |
|---|---|---|
| `narrativa` | VARCHAR |  |
| `titulo` | VARCHAR |  |
| `frases_clave` | VARCHAR |  |
| `comentarios` | BIGINT |  |
| `apoya` | BIGINT |  |
| `rechaza` | BIGINT |  |
| `metodo_postura` | VARCHAR | Cómo se decidió qué lado afirma: campaña, llm o marcadores. |
| `fecha_origen` | TIMESTAMP WITH TIME ZONE |  |

### `gold/pares_coordinados` (797 filas)

Pares de cuentas que coinciden más de lo esperable (k observado, esperado, sorpresa = -log10 p).

| Columna | Tipo | Descripción |
|---|---|---|
| `a` | VARCHAR |  |
| `b` | VARCHAR |  |
| `k` | BIGINT | Publicaciones donde las dos cuentas comentaron a menos de 30 minutos. |
| `esperado` | DOUBLE | Coincidencias esperables por azar según la actividad de las dos cuentas. |
| `sorpresa` | DOUBLE | -log10 de la probabilidad de coincidir tantas veces por azar (Poisson). |

### `gold/supuestos` (10 filas)

Chequeos de lo que el pipeline da por cierto (salen del EDA); se recalculan en cada corrida, también sobre el set final.

| Columna | Tipo | Descripción |
|---|---|---|
| `chequeo` | VARCHAR |  |
| `valor` | DOUBLE |  |
| `esperado` | VARCHAR | Coincidencias esperables por azar según la actividad de las dos cuentas. |
| `ok` | BOOLEAN |  |
| `depende` | VARCHAR |  |
