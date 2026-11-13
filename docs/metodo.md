# Método

Explicado sin código. Los parámetros están en `PARAMS` al principio de cada módulo.

## Narrativas (`qd/narrativas.py`)

1. **Textos únicos.** 200k comentarios son 58k textos distintos: la gente repite fórmulas.
   Se trabaja por texto, no por comentario.
2. **Embeddings** con `multilingual-e5-small` (local, ~1 minuto en una Mac): textos que dicen
   lo mismo con otras palabras quedan cerca.
3. **Micro-clusters**: Leiden sobre el grafo de 10 vecinos más cercanos. Salen ~170 grupos de
   textos casi iguales, con ~96% de pureza.
4. **Tipo de micro-cluster**:
   - *genérico* si sus textos son muy cortos ("totalmente de acuerdo", "jaja"): pueden ir en
     cualquier narrativa;
   - *ruido* si casi no participa de conversaciones (el ruido nunca responde ni recibe
     respuestas);
   - *narrativa* en otro caso.
5. **Narrativas**: Leiden sobre el grafo de **respuestas** entre micro-clusters. Quien
   responde discute la misma narrativa que su padre (del lado opuesto en ~80% de los casos),
   así que las respuestas unen micro-clusters de una misma narrativa. Cuántas narrativas hay lo
   decide el algoritmo (en práctica encuentra 13 de 13).
6. **Rescate de textos dudosos**: los textos largos que cayeron en un grupo genérico se
   reasignan por evidencia de sus respuestas, propagada a sus vecinos de texto.
7. **Origen**: primer comentario de una racha sostenida, contando solo textos propios de la
   narrativa (los genéricos que caen temprano no la inician).

## Postura (`qd/narrativas.py` paso 5, `qd/postura.py`)

1. **Separar los dos lados**: dentro de cada narrativa, un corte máximo del grafo de
   respuestas (los que se responden suelen estar en lados opuestos).
2. **Refinamiento por texto**: cada texto vota según el lado de quienes le responden.
3. **Qué lado afirma** (el corte no lo dice), en orden de confianza:
   - *campaña*: si una operación coordinada empuja claramente un lado, ese afirma;
   - *LLM local* (Qwen2.5-7B, dos consultas con el orden invertido; si no coinciden, se descarta);
   - *marcadores de refutación* ("falso", "mentira", "no hubo"...).

## Coordinación (`qd/coordinacion.py`)

1. **Densidad**: para cada comentario, cuántos hay en la misma publicación a ±30 minutos.
   Coincidir en un posteo viral es normal; en uno tranquilo, no.
2. **Pares**: para cada par de cuentas, en cuántas publicaciones coincidieron frente a cuántas
   se esperaría por azar dada su actividad. Sorpresa = -log10 P(Poisson ≥ observado).
3. **Núcleos**: componentes de pares muy sorprendentes (umbral tipo Bonferroni: se ajusta solo
   a la cantidad de pares probados). Un componente cuenta como núcleo solo si al menos 4 de
   sus cuentas tienen 2 o más pares fuertes dentro de él: con miles de pares, el azar arma
   cadenas sueltas de cuentas genuinas (A-B, B-C, C-D); una campaña es densa.
4. **Expansión**: una cuenta se suma a un grupo si comenta junto al grupo, o le responde, mucho
   más de lo esperable. Rescata campañas de cuentas viejas con textos variados.

## LLM: dónde y por qué

Solo para decidir qué lado afirma y titular cada narrativa: ~26 llamadas en total, local,
US$0. Todo lo demás (agrupar, asignar, coordinación) es estadística y grafos, por costo y
reproducibilidad.
