"""LLM opcional, usado solo una vez por narrativa (no por comentario).

Backends (variable QD_LLM en el entorno o en .env):
- auto  (por defecto): mlx si está instalado y el modelo ya está descargado, si no none
- mlx   : modelo local en Apple Silicon, costo cero
- none  : sin LLM; quien llama usa su plan B
"""
import json
import re
from collections import Counter

from .secretos import secreto

MODELO_MLX = "mlx-community/Qwen2.5-7B-Instruct-4bit"
USO = {"llamadas": 0, "tokens_entrada": 0, "tokens_salida": 0, "backend": "none", "modelo": None}
_modelo = None

PROMPT = """Estos son comentarios de una discusión pública en redes, separados en dos grupos que se contradicen entre sí.

Grupo A:
{a}

Grupo B:
{b}

Un grupo sostiene una AFIRMACIÓN que circula (una denuncia, un reclamo, un rumor, una propuesta o una promesa). El otro grupo la RESPONDE: la desmiente, la relativiza o la contradice.
¿Qué grupo sostiene la afirmación? Respondé solo con JSON: {{"afirmacion": "A" o "B", "titulo": "la afirmación en una frase corta"}}"""


def backend() -> str:
    elegido = (secreto("QD_LLM") or "auto").lower()
    if elegido != "auto":
        return elegido
    try:
        import mlx_lm  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
        return "mlx" if try_to_load_from_cache(MODELO_MLX, "config.json") else "none"
    except Exception:
        return "none"


def _generar(prompt: str) -> str:
    global _modelo
    from mlx_lm import generate, load
    if _modelo is None:
        _modelo = load(MODELO_MLX)
        USO.update(backend="mlx", modelo=MODELO_MLX)
    modelo, tok = _modelo
    entrada = tok.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True,
                                      tokenize=False)
    salida = generate(modelo, tok, prompt=entrada, max_tokens=80, verbose=False)
    USO["llamadas"] += 1
    USO["tokens_entrada"] += len(tok.encode(entrada))
    USO["tokens_salida"] += len(tok.encode(salida))
    return salida


def _muestra(textos, n=10):
    return "\n".join(f"- {t}" for t, _ in Counter(textos).most_common(n))


def _preguntar(a, b):
    salida = _generar(PROMPT.format(a=_muestra(a), b=_muestra(b)))
    m = re.search(r"\{.*\}", salida, re.S)
    try:
        datos = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        datos = {}
    eleccion = str(datos.get("afirmacion", "")).strip().upper()[:1]
    return (eleccion if eleccion in ("A", "B") else None), datos.get("titulo")


def elegir_afirmacion(textos_0, textos_1):
    """{'lado': 0|1, 'titulo': str} o None si no hay LLM o las dos lecturas no coinciden."""
    if backend() != "mlx" or not textos_0 or not textos_1:
        return None
    e1, titulo1 = _preguntar(textos_0, textos_1)       # lado 0 como A
    e2, titulo2 = _preguntar(textos_1, textos_0)       # lado 0 como B
    lado1 = {"A": 0, "B": 1}.get(e1)
    lado2 = {"A": 1, "B": 0}.get(e2)
    if lado1 is None or lado1 != lado2:
        return None
    return {"lado": lado1, "titulo": titulo1 if lado1 == 0 else titulo2 or titulo1}
