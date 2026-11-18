"""Señales del territorio a partir de los reclamos ciudadanos a la Intendencia (SUR).

Cada reclamo tiene fecha, área (Alumbrado, Limpieza, Convivencia, ...) y coordenadas. 3S ubica cada
reclamo en su barrio con un cruce espacial contra los límites de barrios del INE y cuenta reclamos por
barrio, área y día. Solo se usa la FECHA DE INGRESO: el estado actual del reclamo no se usa porque
"miraría al futuro" (el SUR se sobrescribe cada mes con el estado de hoy).

Ojo con el sesgo: más reclamos también puede significar más vecinos que reclaman, no solo más problemas.
"""
import csv
import difflib
import io
import json
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

import contratos

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "territorio_sur.parquet"
MAPEO = RAIZ / "state" / "mapeo_barrios.json"
CRS_SUR = "EPSG:31981"  # SIRGAS2000 / UTM 21S (según los metadatos del SUR)


def norm(txt) -> str:
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().upper()
    t = t.replace("PTA.", "PUNTA").replace("STA.", "SANTA").replace("GRAL.", "GENERAL")
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


# ---------- barrios ----------
def cargar_barrios(zip_ine: Path):
    """Busca dentro del zip del INE la capa de barrios de Montevideo (unos 62 polígonos con nombre)."""
    import geopandas as gpd
    with zipfile.ZipFile(zip_ine) as z:
        shps = [n for n in z.namelist() if n.lower().endswith(".shp")]
    candidatos = sorted(shps, key=lambda n: ("barr" not in n.lower(), len(n)))
    for shp in candidatos:
        try:
            g = gpd.read_file(f"zip://{zip_ine}!{shp}")
        except Exception:
            continue
        if g.empty or not g.geom_type.isin(["Polygon", "MultiPolygon"]).all():
            continue
        for col in g.columns:
            if col == "geometry" or not (g[col].dtype == object or pd.api.types.is_string_dtype(g[col])):
                continue
            nombres = g[col].dropna().astype(str)
            if 50 <= nombres.nunique() <= 70 and nombres.map(norm).str.contains("CIUDAD VIEJA").any():
                g = g[[col, "geometry"]].rename(columns={col: "barrio_ine"})
                if g.crs is None:
                    g = g.set_crs("EPSG:32721")
                g = g.dissolve(by="barrio_ine").reset_index().to_crs(CRS_SUR)
                return g, shp
    raise ValueError(f"no encontré una capa de barrios de Montevideo en {zip_ine.name} (capas: {shps[:15]})")


def mapear_nombres(barrios_ine, barrios_mi):
    """Empareja los nombres de barrio del INE con los del Ministerio del Interior."""
    mi_norm = {norm(b): b for b in barrios_mi}
    mapeo, sin_par = {}, []
    for b in barrios_ine:
        n = norm(b)
        if n in mi_norm:
            mapeo[b] = mi_norm[n]
            continue
        cerca = difflib.get_close_matches(n, list(mi_norm), n=1, cutoff=0.75)
        if cerca:
            mapeo[b] = mi_norm[cerca[0]]
        else:
            sin_par.append(b)
    MAPEO.parent.mkdir(exist_ok=True)
    MAPEO.write_text(json.dumps({"mapeo": mapeo, "sin_par": sin_par}, ensure_ascii=False, indent=1))
    return mapeo, sin_par


# ---------- reclamos ----------
def leer_sur(zip_sur: Path):
    """Lee los reclamos. Acepta coordenadas UTM (COORD_X/COORD_Y, como dicen los metadatos)
    o geográficas (LATITUD/LONGITUD, como viene el archivo desde 2026). Devuelve (tabla, crs)."""
    with zipfile.ZipFile(zip_sur) as z:
        nombre = next(n for n in z.namelist() if n.lower().endswith((".csv", ".txt")))
        muestra = z.open(nombre).read(200_000)
        enc = "utf-8-sig"
        try:
            muestra.decode(enc)
        except UnicodeDecodeError:
            enc = "latin-1"
        texto = muestra.decode(enc, errors="ignore")
        sep = csv.Sniffer().sniff(texto[:5000], delimiters=",;|\t").delimiter
        cabecera = [c.strip().strip('"') for c in texto.splitlines()[0].split(sep)]
        mapa, adapt = contratos.resolver("reclamos_sur", cabecera)
        cx, cy, crs = contratos.resolver_coordenadas(cabecera)
        reales = {mapa["FECHA_INGRESO_RECLAMO"]: "FECHA_INGRESO_RECLAMO", mapa["DESC_AREA"]: "DESC_AREA", cx: cx, cy: cy}
        df = pd.read_csv(z.open(nombre), sep=sep, encoding=enc, dtype=str, usecols=list(reales))
        df = df.rename(columns=reales)
    contratos.verificar_volumen("reclamos_sur", len(df))
    crudo = df["FECHA_INGRESO_RECLAMO"].str.strip()
    fecha = pd.to_datetime(crudo, errors="coerce", format="ISO8601")
    resto = fecha.isna() & crudo.notna()
    if resto.any():  # por si alguna vez viene como dd/mm/aaaa
        fecha[resto] = pd.to_datetime(crudo[resto], errors="coerce", dayfirst=True, format="mixed")
    out = pd.DataFrame({
        "FECHA": fecha.dt.normalize(),
        "DESC_AREA": df["DESC_AREA"],
        "X": pd.to_numeric(df[cx].str.replace(",", ".", regex=False), errors="coerce"),
        "Y": pd.to_numeric(df[cy].str.replace(",", ".", regex=False), errors="coerce"),
    }).dropna(subset=["FECHA", "X", "Y"])
    return out, crs


def construir(zip_sur: Path, zip_ine: Path, barrios_mi, areas, log=lambda etapa, **datos: print(etapa, datos)) -> pd.DataFrame:
    """Devuelve conteos diarios: FECHA, barrio (nombre del MI), area, n. Usa caché si nada cambió."""
    import geopandas as gpd
    firma = f"{zip_sur.stat().st_mtime}-{zip_ine.stat().st_mtime}-{sorted(areas)}"
    marca = SALIDA.with_suffix(".firma")
    if SALIDA.exists() and marca.exists() and marca.read_text() == firma:
        return pd.read_parquet(SALIDA)

    barrios, capa = cargar_barrios(zip_ine)
    mapeo, sin_par = mapear_nombres(barrios["barrio_ine"].tolist(), barrios_mi)
    log("territorio_barrios", capa=capa, poligonos=len(barrios), emparejados=len(mapeo), sin_par=sin_par)

    sur, crs_sur = leer_sur(zip_sur)
    areas_n = {norm(a): a for a in areas}
    sur["area"] = sur["DESC_AREA"].map(lambda a: next((v for k, v in areas_n.items() if norm(a).startswith(k)), None))
    sur = sur.dropna(subset=["area"])
    pts = gpd.GeoDataFrame(sur, geometry=gpd.points_from_xy(sur["X"], sur["Y"]), crs=crs_sur).to_crs(CRS_SUR)
    unido = gpd.sjoin(pts, barrios, how="inner", predicate="within")
    unido["barrio"] = unido["barrio_ine"].map(mapeo)
    unido = unido.dropna(subset=["barrio"])
    log("territorio_reclamos", leidos=len(sur), ubicados=len(unido), coordenadas=crs_sur,
        desde=str(unido["FECHA"].min().date()) if len(unido) else None)

    out = unido.groupby(["FECHA", "barrio", "area"]).size().rename("n").reset_index()
    SALIDA.parent.mkdir(exist_ok=True)
    out.to_parquet(SALIDA, index=False)
    marca.write_text(firma)
    return out
