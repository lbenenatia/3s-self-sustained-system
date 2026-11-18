"""Registro de modelos: campeón actual, historial y regla de promoción (campeón/retador).

Así se autocorrige 3S: cada corrida evalúa variantes nuevas, pero solo reemplaza al campeón
si la mejora es real (intervalo de confianza por encima de cero) y no empeora el top 10.
Si ninguna gana, se queda con lo que ya funcionaba. Nunca se engaña a sí mismo.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ARCHIVO = RAIZ / "state" / "registro.json"


def cargar(escenario, campeon_inicial):
    reg = json.loads(ARCHIVO.read_text()) if ARCHIVO.exists() else {}
    if escenario not in reg:
        reg[escenario] = {"campeon": campeon_inicial, "historial": []}
    return reg


def guardar(reg):
    ARCHIVO.parent.mkdir(exist_ok=True)
    ARCHIVO.write_text(json.dumps(reg, ensure_ascii=False, indent=1))


def decidir(metr, intervalos, campeon, umbral_top10_pts):
    """Devuelve (nuevo_campeon, motivo). intervalos[m] = (lo, hi) de la mejora del error contra el campeón."""
    candidatos = []
    for m, (lo, hi) in intervalos.items():
        dif_top = (metr[m]["acierto_top10"] - metr[campeon]["acierto_top10"]) * 100
        if lo > 0 and dif_top >= -umbral_top10_pts:
            candidatos.append((metr[m]["error_medio"], m, lo, hi, dif_top))
    if not candidatos:
        return campeon, "ningún retador mostró una mejora segura: se mantiene el campeón"
    _, m, lo, hi, dif = min(candidatos)
    return m, f"'{m}' mejora el error entre {lo:.1%} y {hi:.1%} (IC 90%) y el top 10 en {dif:+.1f} pts"


def anotar(reg, escenario, campeon, motivo, metr):
    reg[escenario]["campeon"] = campeon
    reg[escenario]["historial"].append({
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campeon": campeon, "motivo": motivo, "metricas": metr})
