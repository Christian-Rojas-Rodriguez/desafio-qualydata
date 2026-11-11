"""Normalización de texto en castellano rioplatense de redes.

Dos versiones por comentario:
- texto_limpio: legible, para modelos de embeddings (conserva acentos y mayúsculas).
- texto_norm: canónica, para deduplicar y comparar (minúsculas, sin acentos ni signos).
Nada de esto depende de los temas del set: solo reglas del idioma y del medio.
"""
import re
import unicodedata

URL = re.compile(r"https?://\S+|www\.\S+", re.I)
MENCION = re.compile(r"@\w+")
HASHTAG = re.compile(r"#(\w+)")
CAMEL = re.compile(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])")
REPETIDAS = re.compile(r"([a-zñ])\1{2,}")
NO_PALABRA = re.compile(r"[^a-zñ0-9\s]")
ESPACIOS = re.compile(r"\s+")
INTERROGATIVAS = ("que ", "como ", "cuando ", "donde ", "quien ", "cual ", "cuanto ", "cuanta ",
                  "por que ", "alguien sabe", "alguien ")
ABREVIATURAS = {"q": "que", "xq": "porque", "pq": "porque", "x": "por", "tmb": "tambien",
                "tb": "tambien", "pa": "para", "tdo": "todo", "tdos": "todos", "d": "de",
                "k": "que", "bn": "bien", "mñn": "mañana", "xfa": "por favor", "porfa": "por favor"}


def es_emoji(c: str) -> bool:
    return unicodedata.category(c) == "So" or 0x1F000 <= ord(c) <= 0x1FAFF


def sin_acentos(t: str) -> str:
    t = t.replace("ñ", "\x00")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t.replace("\x00", "ñ")


def separar_hashtag(tag: str) -> str:
    return CAMEL.sub(" ", tag)


def limpiar(texto: str) -> str:
    t = unicodedata.normalize("NFC", texto or "")
    t = URL.sub(" ", t)
    t = MENCION.sub(" ", t)
    t = HASHTAG.sub(lambda m: separar_hashtag(m.group(1)), t)
    t = "".join(c for c in t if not es_emoji(c) and unicodedata.category(c)[0] != "C")
    return ESPACIOS.sub(" ", t).strip()


def normalizar(texto: str) -> str:
    t = sin_acentos(limpiar(texto).lower())
    t = NO_PALABRA.sub(" ", t)
    t = REPETIDAS.sub(r"\1", t)
    return " ".join(ABREVIATURAS.get(w, w) for w in t.split())


def atributos(texto: str) -> dict:
    """Atributos de superficie que se pierden al normalizar."""
    crudo = unicodedata.normalize("NFC", texto or "")
    letras = [c for c in crudo if c.isalpha()]
    norm = normalizar(crudo)
    return {
        "texto_limpio": limpiar(crudo),
        "texto_norm": norm,
        "n_tokens": len(norm.split()),
        "es_pregunta": "?" in crudo or "¿" in crudo or norm.startswith(INTERROGATIVAS),
        "hashtags": [h.lower() for h in HASHTAG.findall(crudo)],
        "emojis": [c for c in crudo if es_emoji(c)],
        "n_urls": len(URL.findall(crudo)),
        "n_menciones": len(MENCION.findall(crudo)),
        "prop_mayusculas": round(sum(c.isupper() for c in letras) / len(letras), 3) if letras else 0.0,
    }
