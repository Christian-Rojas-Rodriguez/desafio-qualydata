"""Huella de una corrida: SHA256 de lo que entró y de lo que salió, y el commit del código.

`costo.json` la guarda, así cualquiera puede comprobar que la entrega sale de estos datos
y de este código. Para verificarla, se vuelve a correr todo desde cero en una carpeta
aparte y se comparan las huellas:

    python -m qd.huella --datos datos/final --entrega entrega
"""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SALIDAS = ("comentarios.csv", "narrativas.csv", "cuentas.csv")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def entradas(datos: Path) -> dict:
    return {r.name: sha256(r) for r in sorted(Path(datos).iterdir()) if r.is_file() and not r.name.startswith(".")}


def salidas(entrega: Path) -> dict:
    return {n: sha256(Path(entrega) / n) for n in SALIDAS if (Path(entrega) / n).exists()}


def codigo() -> str:
    """Commit del código; avisa si había cambios sin commitear en qd/."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
        sucio = subprocess.run(["git", "status", "--porcelain", "qd", "requirements.txt"], capture_output=True,
                               text=True).stdout.strip()
        return commit + (" con cambios sin commitear" if sucio else "")
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def filas_iguales(a: Path, b: Path) -> float:
    with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
        ra, rb = list(csv.reader(fa)), list(csv.reader(fb))
    return sum(x == y for x, y in zip(ra, rb)) / max(len(ra), len(rb), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True)
    ap.add_argument("--entrega", type=Path, default=Path("entrega"))
    args = ap.parse_args()
    costo = json.loads((args.entrega / "costo.json").read_text(encoding="utf-8"))
    ok = True
    for nombre, h in entradas(args.datos).items():
        igual = costo.get("entradas_sha256", {}).get(nombre) == h
        ok &= igual
        print(f"entrada  {nombre:<22} {'igual' if igual else 'DISTINTA'}")
    with tempfile.TemporaryDirectory() as tmp:
        nueva = Path(tmp) / "entrega"
        subprocess.run([sys.executable, "-m", "qd", "--datos", str(args.datos), "--entrega", str(nueva),
                        "--lago", str(Path(tmp) / "lago")], check=True, stdout=subprocess.DEVNULL)
        for nombre, h in salidas(nueva).items():
            igual = costo.get("salidas_sha256", {}).get(nombre) == h
            ok &= igual
            detalle = "" if igual else f" ({100 * filas_iguales(args.entrega / nombre, nueva / nombre):.2f}% de filas iguales)"
            print(f"salida   {nombre:<22} {'igual' if igual else 'DISTINTA'}{detalle}")
    print("la entrega se reproduce exacta" if ok else "hay diferencias (con LLM se aceptan diferencias menores)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
