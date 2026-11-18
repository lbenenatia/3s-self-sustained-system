"""Prueba del registro prospectivo: no registra períodos con datos, no sobrescribe, y califica bien."""
import sys, tempfile
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "s3"))
import prospectivo as p
from features import serie

df = pd.read_parquet(RAIZ / "data/denuncias.parquet")
hasta = df["FECHA"].max()
reales = serie(df, "RAPIÑA", "QE")
ult = reales.index[-1]

with tempfile.TemporaryDirectory() as tmp:
    p.CARPETA, p.CALIF = Path(tmp), Path(tmp) / "calificaciones.csv"
    pred = pd.DataFrame({"barrio": reales.columns, "esperado": reales.iloc[-2].values,
                         "promedio_reciente": reales.iloc[-2].values})
    # 1) un período que ya tiene datos NO se registra
    assert p.registrar("trimestral", ult, pred, hasta, "x") is None
    # 2) un período futuro se registra una sola vez
    fut = ult + pd.offsets.QuarterEnd()
    assert p.registrar("trimestral", fut, pred, hasta, "x") is not None
    assert p.registrar("trimestral", fut, pred.assign(esperado=0), hasta, "x") is None
    assert pd.read_csv(Path(tmp) / "trimestral" / f"{fut.date()}.csv")["esperado"].sum() > 0
    # 3) calificación: simulamos una predicción vieja (la del trimestre anterior) del último trimestre con datos
    pred.to_csv(Path(tmp) / "trimestral" / f"{ult.date()}.csv", index=False)
    nuevas = p.calificar(df, {"trimestral": "QE"})
    assert len(nuevas) == 1 and nuevas[0]["periodo"] == str(ult.date()), nuevas
    esperado = (reales.iloc[-2] - reales.iloc[-1]).abs().mean()
    assert abs(nuevas[0]["error_3s"] - esperado) < 1e-2, (nuevas[0], esperado)
    assert p.calificar(df, {"trimestral": "QE"}) == []  # no se califica dos veces
    print("OK:", nuevas[0])
