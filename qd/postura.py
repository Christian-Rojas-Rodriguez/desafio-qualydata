"""Qué lado de una narrativa es el que la afirma ("apoya").

El corte del grafo de respuestas separa bien los dos lados, pero no dice cuál es
la afirmación y cuál la refutación. Eso es semántico: se resuelve con un LLM si hay
uno configurado (QD_LLM) y, si no, con marcadores de refutación.
"""
from . import llm

MARCADORES_REFUTACION = [
    "falso", "mentira", "verso", "fake", "no es cierto", "no es verdad", "no hubo", "nada que ver",
    "inventan", "invento", "trucho", "desminti", "sin pruebas", "dejen de", "no es asi", "nadie va a",
    "exageran", "chamuyo", "operacion", "no tiene sentido", "lean bien", "no es para", "mucho antes",
    "buscan la vuelta", "no pasa nada", "es viejo", "cuento", "fantasia", "mienten",
]


def tasa_refutacion(textos_norm) -> float:
    """Fracción de textos (ya normalizados) con algún marcador de refutación."""
    if not textos_norm:
        return 0.0
    return sum(any(m in t for m in MARCADORES_REFUTACION) for t in textos_norm) / len(textos_norm)


def elegir_lado(lado_0: dict, lado_1: dict) -> tuple:
    """Cada lado es {'limpio': [...], 'norm': [...]}. Devuelve (lado que apoya, info)."""
    respuesta = llm.elegir_afirmacion(lado_0["limpio"], lado_1["limpio"])
    if respuesta is not None:
        return respuesta["lado"], {"metodo": "llm", "titulo": respuesta.get("titulo")}
    r0, r1 = tasa_refutacion(lado_0["norm"]), tasa_refutacion(lado_1["norm"])
    return (0 if r0 <= r1 else 1), {"metodo": "marcadores"}
