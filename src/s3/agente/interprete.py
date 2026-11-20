"""Intérprete: convierte el resultado de una corrida en un aviso en lenguaje humano.

Sin modelo de lenguaje devuelve el texto de siempre. Con modelo, le pasa el resumen y las alertas
y usa lo que redacte; si el modelo falla o no contesta, vuelve al texto de siempre. El intérprete
nunca decide nada: solo cambia cómo se cuenta lo que 3S ya calculó.
"""
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]


def redactar(resumen: str, alertas_texto: str | None = None) -> str:
    try:
        from .proveedor import cargar
        cfg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8"))
        proveedor = cargar(cfg)
        texto = proveedor.redactar({"resumen": resumen, "alertas": alertas_texto})
        return texto or resumen
    except Exception as e:  # el aviso tiene que salir siempre
        print(f"[intérprete] se usa el texto de siempre: {type(e).__name__}")
        return resumen
