"""Registro público de alertas: una vez por trimestre, inmutable, con su validación histórica.

registro_alertas/<trimestre>.csv   alertas del trimestre (se escribe una sola vez)
registro_alertas/<trimestre>.json  cuándo y con qué datos y parámetros se generaron, y el total de la ciudad
registro_alertas/validacion.json   cómo les fue a las alertas en la historia (se recalcula con cada trimestre nuevo)
"""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import alertas as A

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "registro_alertas"
COLUMNAS = ["delito", "barrio", "tipo", "desde", "hasta", "observado", "esperado", "variacion_pct",
            "p_valor", "cusum", "umbral"]
NOMBRE_TIPO = {"pico": "🔺 Pico", "suba": "🔺 Suba sostenida", "baja": "🔻 Baja sostenida"}


def _fuerza(a):
    """Para ordenar: cuánto superó el umbral (CUSUM) o qué tan improbable fue (pico)."""
    if a["tipo"] == "pico":
        return 50.0
    return a["cusum"] / a["umbral"] if a["umbral"] else 0.0


def procesar(df, cfg, log):
    """Evalúa el último trimestre completo. Si es nuevo, lo registra y valida. Devuelve un resumen o None."""
    p = A.Parametros.desde_config(cfg)
    nombre, alertas, ciudad = A.evaluar(df, p)
    destino = CARPETA / f"{nombre}.csv"
    nuevo = not destino.exists()
    if nuevo:
        CARPETA.mkdir(exist_ok=True)
        pd.DataFrame(alertas, columns=COLUMNAS).to_csv(destino, index=False, lineterminator="\n")
        meta = {"trimestre": nombre, "datos_hasta": str(df["FECHA"].max().date()),
                "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "parametros": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(p).items()},
                "ciudad": ciudad}
        destino.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
        log("alertas_registradas", trimestre=nombre, alertas=len(alertas))
        vp = A.Parametros.desde_config(cfg)
        vp.simulaciones = min(vp.simulaciones, 10000)   # la validación recorre 40+ trimestres
        resumen, _ = A.validar_historia(df, vp)
        resumen["calculado_en"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (CARPETA / "validacion.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n")
        log("alertas_validadas", **{k: v for k, v in resumen.items() if k != "calculado_en"})
    else:
        alertas = pd.read_csv(destino).to_dict("records")   # lo registrado manda: no se reescribe
    return {"trimestre": nombre, "nuevo": nuevo, "alertas": alertas, "ciudad": ciudad}


def validacion():
    f = CARPETA / "validacion.json"
    return json.loads(f.read_text()) if f.exists() else None


def _linea(a):
    var = f"{a['variacion_pct']:+.0f}%" if a.get("variacion_pct") is not None else ""
    desde = pd.Timestamp(a["desde"]).strftime("%d/%m")
    cuando = f"semana del {desde}" if a["tipo"] == "pico" else f"desde el {desde}"
    return (f"{NOMBRE_TIPO[a['tipo']]} · {a['delito'].title()} · {a['barrio'].title()}: {var} "
            f"({a['observado']} vs {a['esperado']:.0f} esperadas) {cuando}")


def mensaje(res, maximo=8):
    """Texto para Telegram. Solo se manda si el trimestre es nuevo y hubo alertas."""
    if not res or not res["nuevo"] or not res["alertas"]:
        return None
    orden = sorted(res["alertas"], key=_fuerza, reverse=True)
    lineas = [f"🚨 3S · alertas de desvío {res['trimestre']} ({len(orden)} en total)"]
    lineas += [f"• {_linea(a)}" for a in orden[:maximo]]
    if len(orden) > maximo:
        lineas.append(f"… y {len(orden) - maximo} más en registro_alertas/{res['trimestre']}.csv")
    v = validacion()
    if v and "suba" in v:
        lineas.append(f"Historia: {v['suba']['siguio_desviado_pct']:.0f}% de las subas y "
                      f"{v.get('baja', {}).get('siguio_desviado_pct', 0):.0f}% de las bajas siguieron igual "
                      f"el trimestre siguiente (sin alerta: {v['sin_alerta_arriba_pct']:.0f}% quedó arriba).")
    lineas.append("Son denuncias. El desvío es respecto de la participación habitual del barrio en la ciudad.")
    return "\n".join(lineas)


def seccion_informe(res):
    if not res:
        return []
    l = [f"## Alertas de desvío · {res['trimestre']}", ""]
    if not res["alertas"]:
        l += ["Ningún barrio se desvió de lo esperable en este trimestre.", ""]
    else:
        l += ["| Tipo | Delito | Barrio | Período | Observado | Esperado | Variación |", "|---|---|---|---|---|---|---|"]
        for a in sorted(res["alertas"], key=_fuerza, reverse=True):
            l.append(f"| {NOMBRE_TIPO[a['tipo']]} | {a['delito'].title()} | {a['barrio'].title()} | "
                     f"{a['desde']} a {a['hasta']} | {a['observado']} | {a['esperado']:.1f} | {a['variacion_pct']:+.1f}% |")
        l.append("")
    v = validacion()
    if v:
        partes = [f"{t}: {v[t]['siguio_desviado_pct']:.0f}% siguió desviado ({v[t]['por_trimestre']} por trimestre)"
                  for t in A.TIPOS if t in v]
        l += [f"**Validación histórica ({v['trimestres']} trimestres):** " + " · ".join(partes) +
              f". Sin alerta, {v['sin_alerta_arriba_pct']:.0f}% de los barrios quedó arriba de lo esperable.", ""]
    return l
