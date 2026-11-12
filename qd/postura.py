"""Qué lado de una narrativa es el que la afirma ("apoya").

El corte del grafo de respuestas separa bien los dos lados, pero no dice cuál es
la afirmación y cuál la refutación. En orden de confianza:
1. Campaña: si una operación coordinada empuja claramente un lado, ese lado afirma
   (las operaciones existen para inflar una idea o instalar un rumor).
2. LLM, si hay uno configurado (QD_LLM), leyendo ejemplos de cada lado.
3. Marcadores de refutación ("falso", "mentira", "no hubo"...).
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


MIN_COORDINADOS = 10
PREDOMINIO = 0.8


def elegir_lado(lado_0: dict, lado_1: dict) -> tuple:
    """Cada lado es {'limpio': [...], 'norm': [...], 'coordinados': n}. Devuelve (lado que apoya, info)."""
    c0, c1 = lado_0.get("coordinados", 0), lado_1.get("coordinados", 0)
    if max(c0, c1) >= MIN_COORDINADOS and max(c0, c1) >= PREDOMINIO * (c0 + c1):
        respuesta = llm.elegir_afirmacion(lado_0["limpio"], lado_1["limpio"])
        titulo = respuesta.get("titulo") if respuesta and respuesta["lado"] == (0 if c0 > c1 else 1) else None
        return (0 if c0 > c1 else 1), {"metodo": "campaña", "titulo": titulo}
    respuesta = llm.elegir_afirmacion(lado_0["limpio"], lado_1["limpio"])
    if respuesta is not None:
        return respuesta["lado"], {"metodo": "llm", "titulo": respuesta.get("titulo")}
    r0, r1 = tasa_refutacion(lado_0["norm"]), tasa_refutacion(lado_1["norm"])
    return (0 if r0 <= r1 else 1), {"metodo": "marcadores"}
