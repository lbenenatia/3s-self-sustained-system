"""Alertas de desvío por barrio (Fase 5).

Cuando el Ministerio publica un trimestre nuevo, 3S lo recorre semana por semana y busca barrios que
se salieron de lo esperable para ellos mismos:

  - PICO: una semana puntual muy por encima de lo esperable.
  - SUBA SOSTENIDA: varias semanas seguidas por encima, aunque ninguna sola llame la atención (CUSUM).
  - BAJA SOSTENIDA: lo mismo hacia abajo. Sirve para preguntar qué se hizo bien.

Lo "esperable" para un barrio en una semana es su participación habitual en los delitos de la ciudad
(medida en las 52 semanas previas al trimestre) multiplicada por el total de la ciudad esa semana.
Así no salta una alerta en todos los barrios por una suba o baja general, ni por estacionalidad:
se alerta solo lo que es propio del barrio. El cambio de la ciudad entera se informa aparte.

Los umbrales se calibran por simulación con una binomial negativa (que admite la variabilidad extra
que tienen los datos reales) para que, si nada cambiara, hubiera en promedio como máximo el número de
falsas alarmas por trimestre que fija la configuración.

Nunca se habla de personas: solo de barrios y semanas.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from features import serie

TIPOS = ("pico", "suba", "baja")


@dataclass
class Parametros:
    delitos: tuple = ("RAPIÑA", "HURTO", "LESIONES")
    subas: bool = True
    bajas: bool = True
    falsas_alarmas_por_trimestre: float = 1.0   # en toda la ciudad, sumando delitos y tipos
    delta_suba: float = 0.4                     # cambio que la CUSUM busca detectar (+40%)
    delta_baja: float = 0.3                     # (-30%)
    min_esperado_trimestre: float = 5.0         # barrios con menos eventos esperados no se evalúan
    simulaciones: int = 20000
    semilla: int = 0

    @classmethod
    def desde_config(cls, cfg: dict):
        a = cfg.get("alertas", {})
        p = cls()
        for k, v in a.items():
            if hasattr(p, k):
                setattr(p, k, tuple(v) if isinstance(v, list) else v)
        return p


# ---------------------------------------------------------------- utilidades estadísticas
def _dispersion(obs: np.ndarray, esp: np.ndarray) -> float:
    """k de la binomial negativa (var = mu + mu²/k) por momentos. Grande = casi Poisson."""
    exceso = ((obs - esp) ** 2 - esp).sum()
    return float(np.clip((esp ** 2).sum() / exceso, 2.0, 1e4)) if exceso > 0 else 1e4


def _simular_nb(mu: np.ndarray, k: float, n: int, rng) -> np.ndarray:
    """Simula conteos NB(mu, k). mu: (barrios, semanas) -> (n, barrios, semanas)."""
    lam = rng.gamma(shape=k, scale=mu[None] / k, size=(n,) + mu.shape)
    return rng.poisson(lam)


def _cusum(y: np.ndarray, mu: np.ndarray, factor: float) -> np.ndarray:
    """CUSUM de Poisson (razón de verosimilitud) para detectar un cambio mu -> mu*factor.
    y, mu: (..., semanas). Devuelve el estadístico acumulado en cada semana."""
    paso = y * np.log(factor) - mu * (factor - 1)
    s = np.zeros_like(paso, dtype=float)
    acc = np.zeros(paso.shape[:-1])
    for t in range(paso.shape[-1]):
        acc = np.maximum(0.0, acc + paso[..., t])
        s[..., t] = acc
    return s


def _cola_superior_nb(y, mu, k):
    """P(Y >= y) para Y ~ NB(mu, k)."""
    from scipy.stats import nbinom
    p = k / (k + mu)
    return nbinom.sf(np.asarray(y) - 1, k, p)


# ---------------------------------------------------------------- núcleo
def _ventana(tabla: pd.DataFrame, inicio: pd.Timestamp, fin: pd.Timestamp):
    """Semanas completas (lunes a domingo) que caen enteras dentro de [inicio, fin]."""
    return tabla[(tabla.index - pd.Timedelta(days=6) >= inicio) & (tabla.index <= fin)]


def esperado(tabla: pd.DataFrame, inicio: pd.Timestamp, semanas: pd.DataFrame):
    """Participación de cada barrio en las 52 semanas previas × total de la ciudad en cada semana."""
    previo = tabla[tabla.index < inicio].tail(52)
    if len(previo) < 52:
        return None, None
    part = previo.sum() / previo.values.sum()
    mu = pd.DataFrame(np.outer(semanas.sum(axis=1), part), index=semanas.index, columns=semanas.columns)
    # dispersión estimada con el mismo modelo dentro del año previo (sin mirar el trimestre evaluado)
    mu_prev = pd.DataFrame(np.outer(previo.sum(axis=1), part), index=previo.index, columns=previo.columns)
    k = _dispersion(previo.values.ravel(), mu_prev.values.ravel())
    return mu, k


def evaluar_trimestre(df, delito, inicio, fin, p: Parametros, rng=None):
    """Alertas de un delito en un trimestre. Devuelve (lista de alertas, resumen de la ciudad)."""
    rng = rng or np.random.default_rng(p.semilla)
    tabla = serie(df, delito, "W-SUN")
    semanas = _ventana(tabla, pd.Timestamp(inicio), pd.Timestamp(fin))
    if len(semanas) < 8:
        return [], None
    mu, k = esperado(tabla, pd.Timestamp(inicio), semanas)
    if mu is None:
        return [], None
    evaluables = mu.sum() >= p.min_esperado_trimestre
    y = semanas.loc[:, evaluables].values.T.astype(float)          # (barrios, semanas)
    m = mu.loc[:, evaluables].values.T
    barrios = list(semanas.columns[evaluables])
    nb, ns = y.shape

    tipos_activos = [t for t in TIPOS if (t != "suba" or p.subas) and (t != "baja" or p.bajas)]
    cupo = p.falsas_alarmas_por_trimestre / (len(p.delitos) * len(tipos_activos))   # falsas alarmas por tipo
    alertas = []

    # --- picos: una semana con probabilidad muy baja bajo lo esperable
    if "pico" in tipos_activos:
        alfa = cupo / (nb * ns)
        pv = _cola_superior_nb(y, m, k)
        for i, j in zip(*np.where(pv < alfa)):
            alertas.append(_alerta(delito, barrios[i], "pico", semanas.index[j], semanas.index[j],
                                   y[i, j], m[i, j], float(pv[i, j])))

    # --- subas y bajas sostenidas: CUSUM con umbral calibrado por simulación para cada barrio
    sim = None
    for tipo, factor in (("suba", 1 + p.delta_suba), ("baja", 1 - p.delta_baja)):
        if tipo not in tipos_activos:
            continue
        if sim is None:
            sim = _simular_nb(m, k, p.simulaciones, rng)
        maximos_nulos = _cusum(sim, m[None], factor).max(axis=-1)       # (n, barrios)
        h = np.quantile(maximos_nulos, 1 - cupo / nb, axis=0)           # umbral por barrio
        s = _cusum(y, m, factor)
        for i in range(nb):
            cruces = np.where(s[i] > h[i])[0]
            if not len(cruces):
                continue
            fin_j = ns - 1
            ini_j = cruces[0]
            while ini_j > 0 and s[i, ini_j - 1] > 0:   # el desvío empezó cuando la CUSUM dejó de estar en 0
                ini_j -= 1
            obs, exp = y[i, ini_j:fin_j + 1].sum(), m[i, ini_j:fin_j + 1].sum()
            alertas.append(_alerta(delito, barrios[i], tipo, semanas.index[ini_j], semanas.index[fin_j],
                                   obs, exp, None, cusum=float(s[i].max()), umbral=float(h[i])))

    ciudad = {"delito": delito, "semanas": ns, "barrios_evaluados": nb, "dispersion_k": round(k, 1),
              "total": int(semanas.values.sum())}
    return alertas, ciudad


def _alerta(delito, barrio, tipo, desde, hasta, obs, esp, pvalor, cusum=None, umbral=None):
    return {"delito": delito, "barrio": barrio, "tipo": tipo,
            "desde": str((pd.Timestamp(desde) - pd.Timedelta(days=6)).date()), "hasta": str(pd.Timestamp(hasta).date()),
            "observado": int(round(obs)), "esperado": round(float(esp), 1),
            "variacion_pct": float(round((obs / esp - 1) * 100, 1)) if esp > 0 else None,
            "p_valor": None if pvalor is None else float(f"{pvalor:.2e}"),
            "cusum": None if cusum is None else round(cusum, 2), "umbral": None if umbral is None else round(umbral, 2)}


def ultimo_trimestre_completo(df):
    fin = df["FECHA"].max().normalize()
    q = pd.Timestamp(fin).to_period("Q")
    if fin < q.end_time.normalize():
        q = q - 1
    return q.start_time, q.end_time.normalize(), str(q)


def evaluar(df, p: Parametros, trimestre=None):
    """Evalúa todos los delitos en un trimestre (por defecto, el último completo)."""
    if trimestre is None:
        inicio, fin, nombre = ultimo_trimestre_completo(df)
    else:
        q = pd.Period(trimestre, "Q")
        inicio, fin, nombre = q.start_time, q.end_time.normalize(), str(q)
    todas, ciudad = [], []
    for d in p.delitos:
        a, c = evaluar_trimestre(df, d, inicio, fin, p)
        todas += a
        if c:
            ciudad.append(c)
    return nombre, todas, ciudad


# ---------------------------------------------------------------- validación con la historia
def _razon_siguiente(df, delito, inicio_q, fin_q):
    """Para cada barrio: observado / esperado en el trimestre SIGUIENTE, con la línea base de antes de Q.
    Si una alerta era real, el barrio debería seguir del mismo lado (arriba para subas, abajo para bajas)."""
    tabla = serie(df, delito, "W-SUN")
    q1 = pd.Period(pd.Timestamp(inicio_q), "Q") + 1
    sig = _ventana(tabla, q1.start_time, q1.end_time.normalize())
    mu, _ = esperado(tabla, pd.Timestamp(inicio_q), sig)
    if mu is None or len(sig) < 8:
        return None
    return (sig.sum() / mu.sum()).rename("razon")


def validar_historia(df, p: Parametros, desde="2016Q1"):
    """Corre las alertas en cada trimestre pasado y mide si los barrios alertados siguieron desviados
    el trimestre siguiente, comparado con todos los barrios. Devuelve (resumen, detalle)."""
    ultimo = pd.Period(ultimo_trimestre_completo(df)[2], "Q")
    filas = []
    for q in pd.period_range(desde, ultimo - 1, freq="Q"):
        _, alertas, _ = evaluar(df, p, str(q))
        for d in p.delitos:
            r = _razon_siguiente(df, d, q.start_time, q.end_time)
            if r is None:
                continue
            marcados = {(a["barrio"], a["tipo"]) for a in alertas if a["delito"] == d}
            for barrio, razon in r.items():
                tipos = [t for (b, t) in marcados if b == barrio] or ["ninguna"]
                for t in tipos:
                    filas.append({"trimestre": str(q), "delito": d, "barrio": barrio, "alerta": t,
                                  "razon_siguiente": float(razon)})
    det = pd.DataFrame(filas)
    base = det[det["alerta"] == "ninguna"]
    resumen = {"trimestres": int(det["trimestre"].nunique()),
               "sin_alerta_arriba_pct": round(float((base["razon_siguiente"] > 1).mean() * 100), 1)}
    for t in TIPOS:
        g = det[det["alerta"] == t]
        if not len(g):
            continue
        lado = (g["razon_siguiente"] < 1) if t == "baja" else (g["razon_siguiente"] > 1)
        resumen[t] = {"alertas": int(len(g)), "por_trimestre": round(len(g) / resumen["trimestres"], 1),
                      "siguio_desviado_pct": round(float(lado.mean() * 100), 1),
                      "razon_media_siguiente": round(float(g["razon_siguiente"].mean()), 2)}
    return resumen, det
