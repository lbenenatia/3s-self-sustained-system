"""Fase 7 · prueba de viabilidad · paso 2: ¿las noticias agregan algo al esperado de la Fase 5?

Simula la situación real: al cierre de cada trimestre se conoce el dato oficial hasta ahí, y hay que
estimar cada semana del trimestre siguiente. Compara, con origen móvil (se ajusta solo con trimestres
anteriores al evaluado):

  esperado       participación del barrio (52 semanas previas) × promedio de la ciudad (13 semanas previas)
  recalibrado    esperado × un factor fijo aprendido de la historia (sin noticias)
  + ciudad       además, cuánto se apartan las noticias de toda la ciudad de su nivel previo
  + barrio       además, cuánto se apartan las noticias del barrio de su nivel previo

El aporte de las noticias es la diferencia contra "recalibrado", no contra "esperado".

Uso:  python analisis/fase7_viabilidad/02_analizar.py [--muestra N]
"""
import gzip
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "s3"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from features import serie  # noqa: E402
from extraccion import extraer, SENALES  # noqa: E402

DATOS = RAIZ / "data" / "noticias_viabilidad"
PARES = [("RAPIÑA", "robo"), ("RAPIÑA", "rap"), ("HURTO", "robo"), ("LESIONES", "viol")]
PRIMER_TRIMESTRE = "2019Q1"
SUAVIZADO = 2.0
warnings.filterwarnings("ignore")


# ------------------------------------------------------------------ noticias
def leer_notas(medios):
    filas, raros = [], 0
    for medio in medios:
        for f in sorted((DATOS / medio).glob("*.xml.gz")):
            crudo = f.read_bytes()
            try:
                crudo = gzip.decompress(crudo)
            except OSError:
                pass
            for loc, mod in re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", crudo.decode("utf-8", "ignore")):
                senales, barrio, concreto = extraer(loc)
                if not senales:
                    continue
                fecha = pd.Timestamp(mod)
                fecha = (fecha.tz_convert("America/Montevideo") if fecha.tzinfo else fecha).tz_localize(None).normalize()
                if fecha.strftime("%Y%m") != f.name[:6]:
                    raros += 1   # la fecha de modificación no cae en el mes del índice
                    fecha = pd.Timestamp(f.name[:4] + "-" + f.name[4:6] + "-15")
                filas.append({"medio": medio, "fecha": fecha, "barrio": barrio, "concreto": concreto,
                              **{s: s in senales for s in SENALES}, "_url": loc})
    return pd.DataFrame(filas), raros


def semanal_ciudad(notas, senal, indice):
    n = notas[notas[senal] & notas["concreto"]]
    return n.groupby(pd.Grouper(key="fecha", freq="W-SUN")).size().reindex(indice, fill_value=0).astype(float)


def semanal_barrio(notas, senal, indice, barrios):
    """Hechos por barrio y semana. Notas del mismo barrio y señal a 2 días o menos cuentan como un hecho."""
    n = notas[notas[senal] & notas["concreto"] & notas["barrio"].notna()].sort_values("fecha")
    salto = n.groupby("barrio")["fecha"].diff().dt.days
    n = n[salto.isna() | (salto > 2)]
    t = n.groupby([pd.Grouper(key="fecha", freq="W-SUN"), "barrio"]).size().unstack(fill_value=0)
    return t.reindex(index=indice, columns=barrios, fill_value=0).astype(float), len(n)


# ------------------------------------------------------------------ panel de evaluación
def armar(oficial, not_ciudad, not_barrio):
    filas = []
    ultimo = pd.Period(oficial.index[-1], "Q")
    for q in pd.period_range("2018Q1", ultimo, freq="Q"):
        inicio, fin = q.start_time, q.end_time.normalize()
        sem = oficial[(oficial.index - pd.Timedelta(days=6) >= inicio) & (oficial.index <= fin)]
        previo = oficial[oficial.index < inicio]
        if len(sem) < 8 or len(previo) < 52:
            continue
        part = previo.tail(52).sum() / previo.tail(52).values.sum()
        ciudad13 = previo.tail(13).sum(axis=1).mean()
        prom13 = previo.tail(13).mean()
        nc_prev = not_ciudad[not_ciudad.index < inicio].tail(13).mean()
        nb_prev = not_barrio[not_barrio.index < inicio].tail(52).mean()
        nb_acum = not_barrio.loc[sem.index].cumsum()
        for k, t in enumerate(sem.index, 1):
            nc4 = not_ciudad[not_ciudad.index <= t].tail(4).sum()
            f_ciudad = np.log((nc4 + SUAVIZADO) / (4 * nc_prev + SUAVIZADO))
            f_barrio = np.log((nb_acum.loc[t] + SUAVIZADO) / (nb_prev * k + SUAVIZADO))
            filas.append(pd.DataFrame({"q": str(q), "t": t, "barrio": sem.columns, "y": sem.loc[t].values,
                                       "esperado": (part * ciudad13).values, "promedio": prom13.values,
                                       "f_ciudad": f_ciudad, "f_barrio": f_barrio.values,
                                       "n_barrio": not_barrio.loc[t].values}))
    return pd.concat(filas, ignore_index=True)


def _ajustar(tr, te, cols):
    tr = tr[tr["esperado"] > 0]
    if not cols:
        return te["esperado"] * (tr["y"].sum() / tr["esperado"].sum())
    m = PoissonRegressor(alpha=0.0, max_iter=500).fit(tr[cols], tr["y"] / tr["esperado"], sample_weight=tr["esperado"])
    return te["esperado"] * m.predict(te[cols]), m.coef_


def origen_movil(p):
    """Predicciones de cada modelo para cada trimestre, ajustando solo con trimestres anteriores."""
    partes, coefs = [], []
    for q in sorted(x for x in p["q"].unique() if x >= PRIMER_TRIMESTRE):
        tr, te = p[p["q"] < q], p[p["q"] == q].copy()
        if tr["q"].nunique() < 4:   # hace falta al menos un año de historia para ajustar
            continue
        te["recalibrado"] = _ajustar(tr, te, [])
        te["ciudad"], _ = _ajustar(tr, te, ["f_ciudad"])
        te["barrio_m"], c = _ajustar(tr, te, ["f_ciudad", "f_barrio"])
        coefs.append(c)
        partes.append(te)
    return pd.concat(partes, ignore_index=True), np.array(coefs)


def comparar(r, col, ref, n=2000, semilla=0):
    """Mejora del error medio de `col` respecto de `ref` (positivo = mejor), con IC 90% por trimestres."""
    e = r.assign(a=(r[col] - r["y"]).abs(), b=(r[ref] - r["y"]).abs()).groupby("q")[["a", "b"]].sum()
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(e), size=(n, len(e)))
    a, b = e["a"].values[idx].sum(axis=1), e["b"].values[idx].sum(axis=1)
    lo, hi = np.quantile(1 - a / b, [0.05, 0.95])
    return {"mejora": round(float(1 - e["a"].sum() / e["b"].sum()), 4), "ic90": [round(float(lo), 4), round(float(hi), 4)]}


def top10(r, col):
    aciertos = []
    for _, g in r.groupby("q"):
        s = g.groupby("barrio")[[col, "y"]].sum()
        aciertos.append(len(set(s.nlargest(10, col).index) & set(s.nlargest(10, "y").index)) / 10)
    return round(float(np.mean(aciertos)), 3)


def evaluar(oficial, notas, senal, sintetico=None):
    if sintetico is None:
        nc = semanal_ciudad(notas, senal, oficial.index)
        nb, hechos = semanal_barrio(notas, senal, oficial.index, oficial.columns)
    else:   # control: "noticias" perfectas que cubren al azar una fracción fija de las denuncias reales
        nb = pd.DataFrame(np.random.default_rng(1).binomial(oficial.values.astype(int), sintetico),
                          index=oficial.index, columns=oficial.columns).astype(float)
        nc, hechos = nb.sum(axis=1), nb.values.sum()
    r, coefs = origen_movil(armar(oficial, nc, nb))
    modelos = ["esperado", "promedio", "recalibrado", "ciudad", "barrio_m"]
    sal = {"trimestres": int(r["q"].nunique()), "hechos_con_barrio": int(hechos),
           "celdas_con_noticia_pct": round(float((r["n_barrio"] > 0).mean() * 100), 2),
           "coef_ciudad_barrio": [round(float(x), 3) for x in coefs.mean(axis=0)],
           "error_barrio": {m: round(float((r[m] - r["y"]).abs().mean()), 3) for m in modelos},
           "top10": {m: top10(r, m) for m in modelos},
           "piso_poisson": round(float(np.mean(np.abs(np.random.default_rng(0).poisson(r["y"].clip(lower=0.05))
                                                         - r["y"]))), 3),
           "ciudad_vs_recalibrado": comparar(r, "ciudad", "recalibrado"),
           "barrio_vs_ciudad": comparar(r, "barrio_m", "ciudad"),
           "barrio_vs_recalibrado": comparar(r, "barrio_m", "recalibrado"),
           "barrio_vs_esperado": comparar(r, "barrio_m", "esperado")}
    sin2020 = r[~r["q"].str.startswith("2020")]
    sal["barrio_vs_recalibrado_sin_2020"] = comparar(sin2020, "barrio_m", "recalibrado")
    # la ciudad entera, semana a semana
    c = r.groupby(["q", "t"])[["y", "esperado", "recalibrado", "ciudad"]].sum().reset_index()
    sal["error_ciudad"] = {m: round(float((c[m] - c["y"]).abs().mean()), 1) for m in ["esperado", "recalibrado", "ciudad"]}
    sal["total_ciudad_vs_recalibrado"] = comparar(c, "ciudad", "recalibrado")
    # por trimestre y barrio: ¿donde las noticias subieron, el oficial quedó por encima de lo esperado?
    ult = r.sort_values("t").groupby(["q", "barrio"]).agg(y=("y", "sum"), esp=("recalibrado", "sum"),
                                                          f=("f_barrio", "last"), n=("n_barrio", "sum")).reset_index()
    ult = ult[ult["esp"] >= 5]
    sal["correlacion_trimestral"] = round(float(ult["f"].corr(np.log((ult["y"] + 1) / (ult["esp"] + 1)), method="spearman")), 3)
    razon = ult["y"] / ult["esp"]
    sal["subas_oficiales"] = {"casos": int((razon >= 1.4).sum()),
                              "con_noticias_arriba_pct": round(float((ult.loc[razon >= 1.4, "f"] > 0).mean() * 100), 1),
                              "resto_con_noticias_arriba_pct": round(float((ult.loc[razon < 1.4, "f"] > 0).mean() * 100), 1)}
    return sal


def main():
    df = pd.read_parquet(RAIZ / "data" / "denuncias.parquet", columns=["FECHA", "DELITO", "DEPTO", "BARRIO_MONTEVIDEO"])
    todas, raros = leer_notas(["subrayado", "observador"])
    if "--muestra" in sys.argv:   # para revisar a ojo la extracción; se muestra y no se guarda
        n = int(sys.argv[sys.argv.index("--muestra") + 1])
        m = todas[todas["barrio"].notna() & todas["concreto"]].sample(n, random_state=1)
        for _, x in m.iterrows():
            print(f"{x['barrio'][:22]:22} {'+'.join(s for s in SENALES if x[s]):14} {x['_url'].rsplit('/', 1)[-1][:110]}")
        return
    todas = todas.drop(columns="_url")
    res = {"datos_oficiales_hasta": str(df["FECHA"].max().date()), "fechas_fuera_de_mes": int(raros), "notas": {}}
    for medio, g in todas.groupby("medio"):
        res["notas"][medio] = {"desde": str(g["fecha"].min().date()), "con_delito": len(g),
                               "hecho_concreto": int(g["concreto"].sum()),
                               "con_barrio": int((g["concreto"] & g["barrio"].notna()).sum())}
    oficiales = {d: serie(df, d, "W-SUN") for d in {p[0] for p in PARES}}
    # cobertura: hechos con barrio en la prensa respecto de las denuncias, por año
    cob = {}
    for delito, senal in PARES:
        of = oficiales[delito]
        nb, _ = semanal_barrio(todas[todas["medio"] == "subrayado"], senal, of.index, of.columns)
        a = pd.DataFrame({"prensa": nb.sum(axis=1), "oficial": of.sum(axis=1)}).groupby(of.index.year).sum()
        cob[f"{delito}~{senal}"] = {int(y): [int(v["prensa"]), int(v["oficial"]), round(v["prensa"] / v["oficial"] * 100, 2)]
                                    for y, v in a.iterrows() if y >= 2018}
    res["cobertura_subrayado_por_anio"] = cob
    res["resultados"] = {}
    for nombre, medios, desde in [("subrayado", ["subrayado"], None), ("ambos_desde_2022", ["subrayado", "observador"], "2021-01-01")]:
        notas = todas[todas["medio"].isin(medios)]
        for delito, senal in PARES:
            of = oficiales[delito]
            if desde:   # El Observador tiene archivo completo recién desde 2021
                of = of[of.index >= desde]
            try:
                res["resultados"][f"{nombre} · {delito}~{senal}"] = evaluar(of, notas, senal)
            except Exception as e:
                res["resultados"][f"{nombre} · {delito}~{senal}"] = {"error": f"{type(e).__name__}: {e}"}
    # control positivo: ¿con qué cobertura el método SÍ detectaría señal, si la extracción fuera perfecta?
    res["control_cobertura_perfecta"] = {}
    for delito in ("RAPIÑA", "HURTO", "LESIONES"):
        for cobertura in (0.005, 0.02, 0.05, 0.2, 0.5):
            e = evaluar(oficiales[delito], None, None, sintetico=cobertura)
            res["control_cobertura_perfecta"][f"{delito} · {cobertura:.1%}"] = {
                k: e[k] for k in ("celdas_con_noticia_pct", "barrio_vs_recalibrado", "total_ciudad_vs_recalibrado")}
    salida = Path(__file__).resolve().parent / "resultados.json"
    salida.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
