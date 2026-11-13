PY ?= .venv/bin/python
export QD_LLM ?= mlx

.PHONY: practica final verificar tablero puntuar validar eda docs test

practica:  ## pipeline sobre la práctica y puntaje
	$(PY) -m qd --datos datos/practica --entrega salida/practica
	$(PY) evaluacion/puntuar.py --verdad datos/practica/verdad --entrega salida/practica

final:  ## pipeline sobre el set final -> entrega/
	$(PY) -m qd --datos datos/final --entrega entrega

verificar:  ## re-corre el final desde cero en otra carpeta y compara las huellas SHA256 de costo.json
	$(PY) -m qd.huella --datos datos/final --entrega entrega

tablero:  ## página de resultados del final: qué circula, desde cuándo y quién lo empuja
	$(PY) -m qd.tablero --lago lake/final --salida docs/resultados.html

puntuar:
	$(PY) evaluacion/puntuar.py --verdad datos/practica/verdad --entrega salida/practica

validar:  ## validación cruzada (etiquetas es rápido; datos y tema corren el pipeline varias veces)
	$(PY) -m qd.validacion --modo etiquetas
	$(PY) -m qd.validacion --modo tema
	$(PY) -m qd.validacion --modo datos
	$(PY) -m qd.validacion --modo dias

eda:  ## ejecuta el notebook de EDA y guarda las salidas
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda_practica.ipynb

docs:  ## regenera el diccionario de datos
	$(PY) -m qd.diccionario --lago lake/practica

test:
	$(PY) -m pytest -q tests
