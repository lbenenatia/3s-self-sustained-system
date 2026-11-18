"""Registro prospectivo: la prueba de fuego de 3S.

1. REGISTRAR: cuando 3S predice un período del que todavía NO hay datos publicados, guarda la
   predicción en registro_predicciones/<escenario>/<período>.csv. Ese archivo nunca se sobrescribe.
   Al estar en un repositorio público de GitHub, la fecha del commit prueba que la predicción
   existía antes de que se conocieran los resultados.
2. CALIFICAR: cuando el Ministerio publica ese período, 3S compara lo predicho con lo real y lo
   anota en registro_predicciones/calificaciones.csv, junto con la referencia "promedio reciente".

Así se acumula un historial que cualquiera puede verificar, sin confiar en 3S.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from features import serie, EXCLUIR

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "registro_predicciones"
CALIF = CARPETA / "calificaciones.csv"


def registrar(escenario, periodo, prediccion: pd.DataFrame, datos_hasta, campeon):
    """Guarda la predicción si el período todavía no tiene datos. Devuelve la ruta o None."""
    periodo = pd.Timestamp(periodo)
    if periodo <= pd.Timestamp(datos_hasta):
        return None  # ya hay datos de ese período: no sería una predicción a ciegas
    destino = CARPETA / escenario / f"{periodo.date()}.csv"
    if destino.exists():
        return None  # inmutable: la primera predicción registrada es la que cuenta
    destino.parent.mkdir(parents=True, exist_ok=True)
    (prediccion[["barrio", "esperado", "promedio_reciente"]].round(2)
     .to_csv(destino, index=False, lineterminator="\n"))
    meta = {"periodo": str(periodo.date()), "escenario": escenario, "campeon": campeon,
            "datos_hasta": str(pd.Timestamp(datos_hasta).date()),
            "registrado_en": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    destino.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    return destino


def calificar(df, freq_por_escenario, top_k=10):
    """Califica todas las predicciones registradas cuyo período ya tiene datos. Devuelve las nuevas."""
    previas = pd.read_csv(CALIF) if CALIF.exists() else pd.DataFrame(columns=["escenario", "periodo"])
    hechas = set(zip(previas["escenario"], previas["periodo"].astype(str)))
    datos_hasta = df["FECHA"].max()
    nuevas = []
    for escenario, freq in freq_por_escenario.items():
        reales = serie(df, "RAPIÑA", freq)
        for f in sorted((CARPETA / escenario).glob("*.csv")) if (CARPETA / escenario).exists() else []:
            periodo = pd.Timestamp(f.stem)
            if (escenario, f.stem) in hechas or periodo > datos_hasta or periodo not in reales.index:
                continue
            pred = pd.read_csv(f)
            real = reales.loc[periodo].rename("real")
            t = pred.set_index("barrio").join(real, how="inner").reset_index()
            t = t[~t["barrio"].isin(EXCLUIR)]
            fila = {"escenario": escenario, "periodo": f.stem, "barrios": len(t),
                    "calificado_en": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            for col, nombre in [("esperado", "3s"), ("promedio_reciente", "promedio")]:
                fila[f"error_{nombre}"] = round(float((t[col] - t["real"]).abs().mean()), 3)
                top_p, top_r = set(t.nlargest(top_k, col)["barrio"]), set(t.nlargest(top_k, "real")["barrio"])
                fila[f"top10_{nombre}"] = round(len(top_p & top_r) / top_k, 2)
            nuevas.append(fila)
    if nuevas:
        CARPETA.mkdir(exist_ok=True)
        pd.concat([previas, pd.DataFrame(nuevas)], ignore_index=True).to_csv(CALIF, index=False, lineterminator="\n")
    return nuevas


def resumen():
    """Historial acumulado: cuántas predicciones calificadas y cómo le fue a 3S contra la referencia."""
    if not CALIF.exists():
        return None
    c = pd.read_csv(CALIF)
    return {"calificadas": len(c), "error_3s": round(c["error_3s"].mean(), 2),
            "error_promedio": round(c["error_promedio"].mean(), 2),
            "veces_3s_mejor": int((c["error_3s"] < c["error_promedio"]).sum())}
