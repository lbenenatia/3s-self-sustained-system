"""Contratos de datos: qué espera 3S de cada fuente y cómo se adapta a cambios menores.

Cada contrato dice, para cada columna lógica, qué nombres reales acepta (sinónimos), y qué volumen
mínimo espera. Si una fuente cambia un nombre por uno conocido, 3S se adapta solo y lo anota.
Si cambia a algo desconocido, 3S se detiene con esa fuente, avisa y sigue con la última copia buena.
Así se mantiene durante años sin que alguien tenga que vigilarlo a diario.
"""
import unicodedata

CONTRATOS = {
    "denuncias_mi": {
        "columnas": {
            "DELITO": ["DELITO", "TIPO_DELITO"],
            "FECHA": ["FECHA", "FECHA_HECHO", "FECHA_DENUNCIA"],
            "HORA": ["HORA", "HORA_HECHO"],
            "DIA_SEMANA": ["DIA_SEMANA", "DIA"],
            "DEPTO": ["DEPTO", "DEPARTAMENTO"],
            "JURISDICCION": ["JURISDICCION", "SECCIONAL"],
            "BARRIO_MONTEVIDEO": ["BARRIO_MONTEVIDEO", "BARRIO"],
            "VICT_RAP": ["VICT_RAP", "VICTIMA_RAPINA"],
            "VICT_HUR": ["VICT_HUR", "VICTIMA_HURTO"],
            "TENTATIVA": ["TENTATIVA"],
        },
        "opcionales": {"VICT_RAP", "VICT_HUR", "TENTATIVA", "DIA_SEMANA", "HORA"},
        "filas_minimas": 1_000_000,
    },
    "reclamos_sur": {
        "columnas": {
            "FECHA_INGRESO_RECLAMO": ["FECHA_INGRESO_RECLAMO", "FECHA_INGRESO", "FECHA"],
            "DESC_AREA": ["DESC_AREA", "AREA"],
            # dos formas de coordenadas: se resuelven aparte (ver resolver_coordenadas)
        },
        "opcionales": set(),
        "filas_minimas": 500_000,
    },
}

COORDENADAS = [  # (columna X, columna Y, sistema de referencia)
    (["COORD_X", "X"], ["COORD_Y", "Y"], "EPSG:31981"),
    (["LONGITUD", "LON", "LONG"], ["LATITUD", "LAT"], "EPSG:4326"),
]


class Incumplido(Exception):
    """La fuente cambió de una forma que 3S no sabe resolver solo."""


def _n(c):
    return unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode().strip().upper()


def resolver(fuente, cabecera):
    """Devuelve ({nombre_logico: nombre_real}, [adaptaciones]) o lanza Incumplido."""
    contrato = CONTRATOS[fuente]
    reales = {_n(c): c for c in cabecera}
    mapa, adaptaciones, faltan = {}, [], []
    for logico, sinonimos in contrato["columnas"].items():
        hallado = next((reales[_n(s)] for s in sinonimos if _n(s) in reales), None)
        if hallado is None:
            if logico not in contrato["opcionales"]:
                faltan.append(logico)
            continue
        mapa[logico] = hallado
        if _n(hallado) != _n(logico):
            adaptaciones.append(f"{logico} ← {hallado}")
    if faltan:
        raise Incumplido(f"{fuente}: faltan columnas {faltan}. Columnas recibidas: {list(cabecera)[:30]}")
    return mapa, adaptaciones


def resolver_coordenadas(cabecera):
    reales = {_n(c): c for c in cabecera}
    for xs, ys, crs in COORDENADAS:
        x = next((reales[_n(s)] for s in xs if _n(s) in reales), None)
        y = next((reales[_n(s)] for s in ys if _n(s) in reales), None)
        if x and y:
            return x, y, crs
    raise Incumplido(f"reclamos_sur: no hay coordenadas reconocibles. Columnas: {list(cabecera)[:30]}")


def verificar_volumen(fuente, filas):
    minimo = CONTRATOS[fuente]["filas_minimas"]
    if filas < minimo:
        raise Incumplido(f"{fuente}: llegaron {filas:,} filas, se esperaban al menos {minimo:,}")
