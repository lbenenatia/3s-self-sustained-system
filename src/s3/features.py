"""Construcción de series por barrio y de conjuntos de señales (feature sets).

Cada conjunto agrega señales nuevas sobre el anterior, para medir cuánto aporta cada una:
  base        -> historia de rapiñas del barrio (lo mismo que en la Fase 1)
  calendario  -> + feriados, semana de cobro, horas de oscuridad, vacaciones
  otros       -> + hurtos, lesiones y violencia doméstica recientes del mismo barrio
  escalada    -> + aceleración reciente (últimas semanas contra el promedio largo)
  territorio  -> + reclamos a la Intendencia en el barrio (alumbrado, limpieza, convivencia, ...)
  clima       -> + lluvia y temperatura
"""
import json
from pathlib import Path
import pandas as pd
from calendario_uy import senales_semana, senales_trimestre

EXCLUIR = {"SIN CLASIFICAR", "NO CORRESPONDE"}
OTROS = {"HURTO": "hurto", "LESIONES": "lesiones", "VIOLENCIA DOMÉSTICA": "vd"}
CONJUNTOS = ["base", "calendario", "otros", "escalada", "territorio", "clima"]
RAIZ = Path(__file__).resolve().parents[2]
CLIMA = RAIZ / "data" / "externos" / "clima_montevideo.csv"
CLIMA_JSON = RAIZ / "data" / "fuentes" / "clima_open_meteo.json"


def cargar_clima():
    """Clima diario opcional (por ejemplo, exportado de Open-Meteo o INUMET).
    Columnas esperadas: fecha (AAAA-MM-DD), lluvia_mm, temp_max. Si no está, el conjunto 'clima' se omite."""
    if CLIMA_JSON.exists():
        d = json.loads(CLIMA_JSON.read_text())["daily"]
        c = pd.DataFrame({"fecha": pd.to_datetime(d["time"]), "lluvia_mm": d["precipitation_sum"],
                          "temp_max": d["temperature_2m_max"]})
        return c.set_index("fecha").sort_index()
    if not CLIMA.exists():
        return None
    c = pd.read_csv(CLIMA, parse_dates=["fecha"]).set_index("fecha").sort_index()
    return c[["lluvia_mm", "temp_max"]]


def serie(df, delito, freq):
    m = df[(df["DEPTO"] == "MONTEVIDEO") & (df["DELITO"] == delito) & ~df["BARRIO_MONTEVIDEO"].isin(EXCLUIR)]
    t = (m.groupby([pd.Grouper(key="FECHA", freq=freq), "BARRIO_MONTEVIDEO"], observed=True)
           .size().unstack(fill_value=0))
    if t.index[-1] > df["FECHA"].max():
        t = t.iloc[:-1]
    return t


def _apilar(tabla_feat, idx):
    return tabla_feat.stack().reindex(idx).values


def panel(df, freq="W-SUN", extender=False, territorio=None):
    """Devuelve (panel, columnas por conjunto). Si extender, agrega un período futuro vacío para predecir."""
    semanal = freq.startswith("W")
    L, W_CORTA, W_LARGA, EST = (1, 8, 26, 52) if semanal else (1, 4, 4, 4)
    y = serie(df, "RAPIÑA", freq)
    otros = {k: serie(df, d, freq).reindex(index=y.index, columns=y.columns, fill_value=0) for d, k in OTROS.items()}
    if extender:
        nuevo = y.index[-1] + (pd.Timedelta(weeks=1) if semanal else pd.offsets.QuarterEnd())
        y = pd.concat([y, pd.DataFrame(0, index=[nuevo], columns=y.columns)])
        otros = {k: pd.concat([v, pd.DataFrame(0, index=[nuevo], columns=v.columns)]) for k, v in otros.items()}

    largo = y.stack().rename("y").reset_index()
    largo.columns = ["t", "barrio", "y"]
    idx = pd.MultiIndex.from_frame(largo[["t", "barrio"]])
    cols = {c: [] for c in CONJUNTOS}

    def add(grupo, nombre, tabla):
        largo[nombre] = _apilar(tabla, idx)
        cols[grupo].append(nombre)

    for lag in (1, 2, 3, 4):
        add("base", f"lag{lag}", y.shift(lag))
    add("base", "media_corta", y.shift(1).rolling(W_CORTA).mean())
    add("base", "media_larga", y.shift(1).rolling(W_LARGA).mean())
    add("base", "estacional", y.shift(EST))
    total = y.sum(axis=1)
    add("base", "peso_barrio", y.shift(1).rolling(W_LARGA).sum().div(total.shift(1).rolling(W_LARGA).sum(), axis=0))
    largo["barrio_cod"] = largo["barrio"].astype("category").cat.codes
    cols["base"].append("barrio_cod")

    cal = pd.DataFrame([(senales_semana if semanal else senales_trimestre)(t) for t in y.index], index=y.index)
    for c in cal.columns:
        largo[c] = largo["t"].map(cal[c])
        cols["calendario"].append(c)

    for k, tab in otros.items():
        add("otros", f"{k}_lag1", tab.shift(1))
        add("otros", f"{k}_media", tab.shift(1).rolling(W_CORTA).mean())

    corta = y.shift(1).rolling(4 if semanal else 2).mean()
    larga = y.shift(1).rolling(W_LARGA).mean()
    add("escalada", "aceleracion", (corta - larga))
    add("escalada", "ratio_escalada", corta / (larga + 1))
    add("escalada", "max_reciente", y.shift(1).rolling(4 if semanal else 2).max())

    if territorio is not None and len(territorio):
        # El SUR cubre oficialmente desde nov. 2016; antes hay pocos registros y no son comparables.
        inicio = max(territorio["FECHA"].min(), pd.Timestamp("2016-11-01"))
        for area, g in territorio.groupby("area"):
            tab = (g.groupby([pd.Grouper(key="FECHA", freq=freq), "barrio"])["n"].sum().unstack(fill_value=0)
                     .reindex(index=y.index, columns=y.columns).fillna(0))
            tab[tab.index < inicio + (pd.Timedelta(weeks=1) if semanal else pd.offsets.QuarterEnd())] = float("nan")
            # participación del barrio en los reclamos de esa área: quita el efecto de que el uso del SUR
            # creció con los años y deja solo cuánto reclama el barrio en comparación con el resto
            part = tab.div(tab.sum(axis=1), axis=0)
            clave = "sur_" + "".join(ch for ch in area.lower() if ch.isalnum())[:12]
            add("territorio", f"{clave}_lag1", tab.shift(1))
            add("territorio", f"{clave}_media", tab.shift(1).rolling(W_CORTA, min_periods=1).mean())
            add("territorio", f"{clave}_part", part.shift(1).rolling(W_CORTA, min_periods=1).mean())

    clima = cargar_clima()
    if clima is not None:
        agg = clima.resample(freq).agg({"lluvia_mm": "sum", "temp_max": "mean"}).reindex(y.index)
        for c in agg.columns:
            largo[c] = largo["t"].map(agg[c])
            cols["clima"].append(c)

    acum, feats = [], {}
    for c in CONJUNTOS:
        if not cols[c] and c != "base":
            continue
        acum = acum + cols[c]
        feats[c] = list(acum)
    largo = largo.dropna(subset=feats["base"])
    return largo, feats, {"corta": "media_corta", "estacional": "estacional"}
