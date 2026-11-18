"""Entrenamiento, backtest y métricas."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


def nuevo_modelo(feats):
    return HistGradientBoostingRegressor(
        loss="poisson", max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=40,
        l2_regularization=1.0, categorical_features=[feats.index("barrio_cod")], random_state=0)


def backtest(panel, conjuntos, baselines, desde, reentrenar_cada=1):
    """Origen móvil: para cada período >= desde, entrena con el pasado y predice ese período.
    reentrenar_cada > 1 reutiliza el modelo algunos períodos (más rápido, igual de honesto)."""
    periodos = sorted(t for t in panel["t"].unique() if t >= pd.Timestamp(desde))
    salida = []
    modelos = {}
    for i, t in enumerate(periodos):
        test = panel[panel["t"] == t]
        fila = pd.DataFrame({"t": t, "barrio": test["barrio"].values, "real": test["y"].values})
        for nombre, col in baselines.items():
            fila[f"base_{nombre}"] = test[col].values
        if i % reentrenar_cada == 0:
            train = panel[panel["t"] < t]
            modelos = {c: nuevo_modelo(f).fit(train[f], train["y"]) for c, f in conjuntos.items()}
        for c, f in conjuntos.items():
            fila[c] = modelos[c].predict(test[f])
        salida.append(fila)
    return pd.concat(salida, ignore_index=True)


def metricas(res, top_k=10):
    metodos = [c for c in res.columns if c not in ("t", "barrio", "real")]
    out = {}
    for m in metodos:
        acierto = [len(set(g.nlargest(top_k, m)["barrio"]) & set(g.nlargest(top_k, "real")["barrio"])) / top_k
                   for _, g in res.groupby("t")]
        out[m] = {"error_medio": round(float((res[m] - res["real"]).abs().mean()), 4),
                  "acierto_top10": round(float(np.mean(acierto)), 4)}
    return out


def error_por_periodo(res, metodo):
    return res.assign(e=(res[metodo] - res["real"]).abs()).groupby("t")["e"].mean()


def bootstrap_mejora(res, retador, campeon, n=2000, semilla=0):
    """Intervalo del 90% para la mejora relativa del error (remuestreando períodos)."""
    a, b = error_por_periodo(res, retador).values, error_por_periodo(res, campeon).values
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, len(a), (n, len(a)))
    mejoras = 1 - a[idx].mean(1) / b[idx].mean(1)
    return float(np.percentile(mejoras, 5)), float(np.percentile(mejoras, 95))


def piso_azar(res, metodo):
    """Error mínimo esperable si el modelo conociera la tasa real: el azar de Poisson.
    Si el error real está cerca de este piso, ningún modelo puede mejorar mucho a esa escala."""
    from scipy.stats import poisson
    lam = res[metodo].clip(lower=0.01).values
    k = np.arange(0, int(lam.max() * 3 + 30))
    tabla = np.abs(k[None, :] - lam[:, None]) * poisson.pmf(k[None, :], lam[:, None])
    return float(tabla.sum(1).mean())
