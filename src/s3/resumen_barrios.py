"""Resumen liviano por barrio para el agente (Fase 6).

Cada corrida escribe state/resumen_barrios.json: conteos de denuncias por barrio, delito y trimestre
(los últimos 5 trimestres completos). Son datos públicos y agregados. Así el agente puede contestar
"¿cómo viene tal barrio?" en segundos, sin bajar ni procesar los 400 MB de datos.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import alertas as A

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "state" / "resumen_barrios.json"
NO_BARRIO = {"NO CORRESPONDE", "SIN DATO", "SIN CLASIFICAR", ""}
TRIMESTRES = 5


def construir(df, delitos):
    _, fin, nombre = A.ultimo_trimestre_completo(df)
    d = df[(df["FECHA"] <= fin) & df["DELITO"].isin(delitos)].copy()
    d["BARRIO"] = d["BARRIO_MONTEVIDEO"].astype("string").fillna("").str.strip()
    d = d[~d["BARRIO"].isin(NO_BARRIO)]
    d["Q"] = d["FECHA"].dt.to_period("Q")
    ultimos = [d["Q"].max() - i for i in range(TRIMESTRES - 1, -1, -1)]
    d = d[d["Q"].isin(ultimos)]
    conteo = d.groupby(["BARRIO", d["DELITO"].astype(str), "Q"], observed=True).size()
    barrios = {}
    for b in sorted(d["BARRIO"].unique()):
        barrios[b] = {de: [int(conteo.get((b, de, q), 0)) for q in ultimos] for de in delitos}
    ciudad = {de: [sum(barrios[b][de][i] for b in barrios) for i in range(len(ultimos))] for de in delitos}
    return {"generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datos_hasta": str(df["FECHA"].max().date()), "ultimo_trimestre": nombre,
            "trimestres": [str(q) for q in ultimos], "delitos": list(delitos),
            "ciudad": ciudad, "barrios": barrios}


def escribir(df, cfg, log):
    delitos = cfg.get("alertas", {}).get("delitos", ["RAPIÑA", "HURTO", "LESIONES"])
    res = construir(df, delitos)
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log("resumen_barrios", barrios=len(res["barrios"]), trimestre=res["ultimo_trimestre"])
    return res
