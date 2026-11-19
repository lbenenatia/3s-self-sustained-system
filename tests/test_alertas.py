"""Prueba de las alertas de desvío con datos simulados (no necesita internet ni datos reales).

1. Una suba (+80%) y una baja (-50%) inyectadas en el último trimestre se detectan.
2. En datos sin ningún cambio, la cantidad de alertas por trimestre queda cerca de lo configurado.
3. El registro de un trimestre no se reescribe en una segunda corrida.
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "s3"))
import alertas as A
import registro_alertas as R

rng = np.random.default_rng(42)
BARRIOS = [f"BARRIO {i:02d}" for i in range(40)]
TASAS = rng.uniform(0.2, 1.5, len(BARRIOS))      # eventos por día de cada barrio
DIAS = pd.date_range("2022-01-01", "2026-09-30", freq="D")


def simular(cambios=None):
    """Eventos diarios Poisson con algo de variabilidad extra; `cambios` = {barrio: (desde, factor)}."""
    filas = []
    for b, tasa in zip(BARRIOS, TASAS):
        lam = np.full(len(DIAS), tasa) * rng.gamma(30, 1 / 30, len(DIAS))
        if cambios and b in cambios:
            desde, factor = cambios[b]
            lam[DIAS >= pd.Timestamp(desde)] *= factor
        n = rng.poisson(lam)
        filas.append(pd.DataFrame({"FECHA": np.repeat(DIAS, n), "BARRIO_MONTEVIDEO": b}))
    df = pd.concat(filas, ignore_index=True)
    df["DELITO"], df["DEPTO"] = "RAPIÑA", "MONTEVIDEO"
    return df


p = A.Parametros(delitos=("RAPIÑA",), simulaciones=5000)

# 1) detección
df = simular({"BARRIO 03": ("2026-07-01", 1.8), "BARRIO 07": ("2026-07-01", 0.5)})
nombre, alertas, _ = A.evaluar(df, p)
assert nombre == "2026Q3", nombre
tipos = {(a["barrio"], a["tipo"]) for a in alertas}
assert ("BARRIO 03", "suba") in tipos, alertas
assert ("BARRIO 07", "baja") in tipos, alertas
otras = [a for a in alertas if a["barrio"] not in ("BARRIO 03", "BARRIO 07")]
print(f"OK detección: suba y baja inyectadas encontradas; {len(otras)} alertas en barrios sin cambios")

# 2) falsas alarmas en datos sin cambios
nulo = simular()
cuentas = [len(A.evaluar(nulo, p, q)[1]) for q in ["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"]]
media = float(np.mean(cuentas))
assert media <= 2.5, (cuentas, "demasiadas falsas alarmas")
print(f"OK falsas alarmas: {media:.2f} por trimestre en datos sin cambios (configurado: {p.falsas_alarmas_por_trimestre})")

# 3) registro inmutable
with tempfile.TemporaryDirectory() as tmp:
    R.CARPETA = Path(tmp)
    A.validar_historia = lambda df, p: ({"trimestres": 0, "sin_alerta_arriba_pct": 0}, None)  # rápido en la prueba
    cfg = {"alertas": {"delitos": ["RAPIÑA"], "simulaciones": 2000}}
    r1 = R.procesar(df, cfg, lambda *a, **k: None)
    r2 = R.procesar(df, cfg, lambda *a, **k: None)
    assert r1["nuevo"] and not r2["nuevo"]
    assert len(r1["alertas"]) == len(r2["alertas"])
    assert R.mensaje(r2) is None            # un trimestre ya avisado no se vuelve a avisar
    assert R.mensaje(r1).startswith("🚨")
    print("OK registro: se escribe una sola vez y se avisa una sola vez")
