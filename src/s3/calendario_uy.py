"""Señales de calendario y de luz para Montevideo. No necesitan internet: todo se calcula."""
from datetime import date, timedelta
import math
import pandas as pd

LAT_MVD = -34.9


def pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo de Gauss/Meeus, calendario gregoriano)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def feriados_uy(anio: int) -> set[date]:
    """Feriados y días no laborables habituales de Uruguay, más Carnaval y Semana de Turismo."""
    fijos = [(1, 1), (1, 6), (4, 19), (5, 1), (5, 18), (6, 19), (7, 18), (8, 25), (10, 12), (11, 2), (12, 25)]
    dias = {date(anio, m, d) for m, d in fijos}
    p = pascua(anio)
    dias |= {p - timedelta(days=48), p - timedelta(days=47)}           # Carnaval (lunes y martes)
    dias |= {p - timedelta(days=6 - i) for i in range(7)}               # Semana de Turismo (lunes a domingo)
    return dias


def horas_de_luz(dia: date, lat: float = LAT_MVD) -> float:
    """Duración del día (horas) con la fórmula de la declinación solar."""
    n = dia.timetuple().tm_yday
    decl = math.radians(23.44) * math.sin(math.radians(360 / 365 * (n - 81)))
    x = -math.tan(math.radians(lat)) * math.tan(decl)
    x = max(-1.0, min(1.0, x))
    return 2 * math.degrees(math.acos(x)) / 15


def senales_semana(fin_semana: pd.Timestamp) -> dict:
    """Señales para la semana que termina el domingo `fin_semana`."""
    dias = [(fin_semana - pd.Timedelta(days=i)).date() for i in range(7)]
    fer = set().union(*(feriados_uy(a) for a in {d.year for d in dias}))
    return {
        "feriados_semana": sum(d in fer for d in dias),
        "semana_de_cobro": int(any(d.day <= 5 for d in dias)),      # salarios y pasividades a inicio de mes
        "horas_oscuridad": round(24 - sum(horas_de_luz(d) for d in dias) / 7, 2),
        "vacaciones_verano": int(any(d.month in (1, 2) for d in dias)),
    }


def senales_trimestre(fin_trim: pd.Timestamp) -> dict:
    ini = (fin_trim - pd.offsets.QuarterBegin(startingMonth=1)).date()
    dias = pd.date_range(ini, fin_trim.date()).date
    fer = set().union(*(feriados_uy(a) for a in {d.year for d in dias}))
    return {
        "feriados_semana": sum(d in fer for d in dias),
        "semana_de_cobro": 0,
        "horas_oscuridad": round(24 - sum(horas_de_luz(d) for d in dias) / len(dias), 2),
        "vacaciones_verano": int(fin_trim.month == 3),
    }
