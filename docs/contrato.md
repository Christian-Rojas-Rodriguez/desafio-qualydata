# Contrato de datos y calidad

Qué espera el pipeline de cada archivo, qué hace cuando no se cumple y cómo se comprueba
que una entrega sale de estos datos y este código.

## Dos severidades

| Severidad | Qué pasa con la fila | Dónde queda |
|---|---|---|
| **Error**: la fila no se puede usar | Se aparta (cuarentena), nunca se borra en silencio | `bronze/rechazos_csv`, `silver/rechazos` |
| **Advertencia**: la fila se puede usar | Se corrige o se imputa, y queda anotada | columna `flags` de cada tabla silver |

Principio: **no se pierde ningún comentario con id**, porque la entrega tiene que
cubrirlos a todos. Bronze guarda cada fila tal cual, con `_archivo`, `_fila` y `_hash`, así
que cualquier resultado se puede rastrear hasta la línea del CSV de la que salió.

## Reglas

| Tabla | Regla | Severidad | Qué se hace |
|---|---|---|---|
| todas | La línea del CSV se puede leer | error | `bronze/rechazos_csv` con número de línea y motivo |
| todas | Tiene id | error | `silver/rechazos`, motivo `sin_id` |
| todas | El id es único | error | Se queda la primera; las demás van a `silver/rechazos` como `duplicado_exacto` o `id_duplicado_con_otro_contenido` |
| todas | Encabezados en cualquier caso, CRLF, `.csv` o `.csv.gz` | — | Se aceptan |
| comentarios | Fecha legible (ISO, dd/mm/aaaa, epoch) | advertencia | Se imputa con la del comentario padre o la de la publicación: `fecha_imputada`; si no hay ninguna, `sin_fecha` |
| comentarios | `respuesta_a` apunta a un comentario que existe y no es él mismo | advertencia | Se trata como comentario raíz: `respuesta_invalida` |
| comentarios | La publicación existe (integridad referencial) | advertencia | `publicacion_desconocida` |
| comentarios | La cuenta existe en `cuentas` (integridad referencial) | advertencia | Se crea la cuenta en silver con `sin_perfil`; el comentario lleva `cuenta_desconocida` |
| comentarios | Tiene cuenta | advertencia | `sin_cuenta` |
| comentarios | `me_gusta` es un entero ≥ 0 | advertencia | Queda nulo: `me_gusta_invalido` |
| comentarios | Tiene texto | advertencia | `texto_vacio`; va a ruido pero sigue en la entrega |
| cuentas | `fecha_creacion`, `seguidores`, `siguiendo` legibles (acepta `1.234`) | advertencia | Quedan nulos con su flag |
| publicaciones | Fecha legible y fuente conocida | advertencia | Fecha del primer comentario: `fecha_imputada`; `fuente_desconocida` |

`tests/test_datos_sucios.py` inyecta cada uno de estos problemas en un set chico y comprueba
que ningún comentario con id se pierde.

## Supuestos de cada corrida

Además de las reglas por fila, la etapa `supuestos` (`gold/supuestos`) verifica en cada corrida
lo que el análisis exploratorio dio por cierto. Si el set final rompe alguno, avisa. Como se
vio en la materia de infraestructura, **la señal es el cambio**, no el número suelto:

| Chequeo | Esperado | Práctica | Final |
|---|---|---|---|
| Respuestas que cruzan de publicación | 0 | 0 | 0 |
| Respuestas anteriores a su padre | 0 | 0 | 0 |
| % respuestas | ≥ 5 | 14,0 | 13,8 |
| % respuestas con padre desconocido | < 5 | 0 | 0 |
| Textos únicos / comentarios | < 0,6 | 0,29 | 0,27 |
| % sin fecha | < 1 | 0 | 0 |
| % sin cuenta | < 1 | 0 | 0 |
| Narrativas encontradas | 3 a 40 | 13 | 12 |
| % comentarios como ruido | 5 a 40 | 17,9 | 17,8 |
| % cuentas marcadas como coordinadas | < 3 | 0,68 | 0,78 |

Calidad por fila (`silver/calidad`): en los dos sets el único problema es el texto vacío,
1,08% en práctica (2.159) y 1,21% en el final (1.809). Ningún rechazo, ningún duplicado,
ninguna referencia rota. El final tiene el mismo perfil que la práctica, así que los
umbrales elegidos con la práctica aplican.

## Huella de reproducibilidad

`entrega/costo.json` guarda:

- `entradas_sha256`: el SHA256 de cada archivo de `datos/final`. Coincide con los checksums
  publicados en el release.
- `salidas_sha256`: el SHA256 de `comentarios.csv`, `narrativas.csv` y `cuentas.csv`.
- `codigo`: el commit con el que se corrió; avisa si había cambios sin commitear.

`make verificar` vuelve a correr todo desde cero en una carpeta temporal y compara las
huellas. Es lo mismo que hace el jurado con los equipos del podio. Las semillas están fijas
(Leiden, corte máximo) y el LLM decodifica sin muestreo, así que en la misma máquina la
entrega se reproduce byte a byte. En otro hardware el LLM puede variar algún título; si una
huella no coincide, el comando informa qué porcentaje de filas es igual.
