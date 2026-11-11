"""Lectura de claves sin que toquen el repo.

Orden: variable de entorno > archivo .env en la raíz > Kaggle Secrets (si corre en Kaggle).
Ninguna clave es obligatoria: si falta, quien llama decide el plan B (p. ej. pipeline sin LLM).
"""
import os
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent


def _leer_env(path: Path) -> dict:
    valores = {}
    if not path.exists():
        return valores
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def secreto(nombre: str) -> Optional[str]:
    if os.environ.get(nombre):
        return os.environ[nombre]
    valor = _leer_env(RAIZ / ".env").get(nombre)
    if valor:
        return valor
    try:  # solo existe dentro de un notebook de Kaggle
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret(nombre) or None
    except Exception:
        return None


def mascara(valor: Optional[str]) -> str:
    """Para logs: nunca imprimir una clave entera."""
    return "(sin definir)" if not valor else f"{valor[:4]}…{valor[-2:]}"
