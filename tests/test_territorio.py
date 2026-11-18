"""Prueba de punta a punta del módulo territorio con datos sintéticos (sin internet).
Crea un zip de barrios con nombres al estilo INE y un zip de reclamos al estilo SUR, y verifica
que los reclamos caigan en el barrio correcto y que el panel arme las señales."""
import sys, tempfile, zipfile
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import box

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "s3"))
import contratos
import territorio as terr

contratos.CONTRATOS["reclamos_sur"]["filas_minimas"] = 1_000  # los datos de prueba son pocos
from features import panel

df = pd.read_parquet(RAIZ / "data/denuncias.parquet")
mi = sorted(df.loc[df.DEPTO == "MONTEVIDEO", "BARRIO_MONTEVIDEO"].dropna().astype(str).unique())
mi = [b for b in mi if b not in ("SIN CLASIFICAR", "NO CORRESPONDE")]
ine = [b.title().replace("Pta.", "Punta").replace("Malvin", "Malvín") for b in mi]  # nombres "estilo INE"

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    terr.SALIDA, terr.MAPEO = tmp / "territorio.parquet", tmp / "mapeo.json"  # no tocar los datos reales
    x0, y0, lado = 560000, 6130000, 1000
    polys = [box(x0 + (i % 8) * lado, y0 + (i // 8) * lado, x0 + (i % 8 + 1) * lado, y0 + (i // 8 + 1) * lado) for i in range(len(ine))]
    g = gpd.GeoDataFrame({"NOMBBARR": ine, "CODBA": range(len(ine))}, geometry=polys, crs="EPSG:32721")
    (tmp / "shp").mkdir()
    g.to_file(tmp / "shp" / "ine_barrios_mvd.shp", encoding="utf-8")
    zine = tmp / "ine.zip"
    with zipfile.ZipFile(zine, "w") as z:
        for f in (tmp / "shp").iterdir():
            z.write(f, f"vectoriales/{f.name}")
    rng = np.random.default_rng(0)
    n = 20000
    idx = rng.integers(0, len(ine), n)
    fechas = pd.to_datetime("2016-11-01") + pd.to_timedelta(rng.integers(0, 3600, n), unit="D")
    areas = rng.choice(["Alumbrado", "Limpieza", "Convivencia Departamental", "Espacios Públicos", "Arbolado"], n)
    sur = pd.DataFrame({"NUMERO_RECLAMO": range(n), "FECHA_INGRESO_RECLAMO": fechas.strftime("%d/%m/%Y"),
                        "DESC_AREA": areas,
                        "COORD_X": [f"{x0 + (i % 8) * lado + 500:.1f}".replace(".", ",") for i in idx],
                        "COORD_Y": [y0 + (i // 8) * lado + 500 for i in idx]})
    zsur = tmp / "sur.zip"
    with zipfile.ZipFile(zsur, "w") as z:
        z.writestr("reclamos.csv", sur.to_csv(sep=";", index=False).encode("latin-1"))

    t = terr.construir(zsur, zine, mi, ["Alumbrado", "Limpieza", "Convivencia Departamental", "Espacios Publicos"])
    esperado = (sur.assign(b=[mi[i] for i in idx])[sur.DESC_AREA != "Arbolado"])
    assert len(t) and t["n"].sum() == len(esperado), (t["n"].sum(), len(esperado))
    real = t.groupby("barrio")["n"].sum()
    esp = esperado.groupby("b").size()
    assert (real.reindex(esp.index).fillna(0) == esp).all(), "reclamos asignados al barrio equivocado"
    pan, conj, _ = panel(df, "QE", territorio=t)
    nuevas = [c for c in conj["territorio"] if c.startswith("sur_")]
    assert len(nuevas) == 12, nuevas  # 4 áreas × (conteo, media, participación)
    assert pan.loc[pan.t >= "2018-01-01", nuevas].notna().all().all()
    print("OK: ", len(t), "filas;", len(nuevas), "señales;", "ejemplo:", nuevas[:2])
