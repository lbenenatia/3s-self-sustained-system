"""3S – Módulo Seguridad · Ingesta y limpieza.

Lee el CSV oficial "Denuncias de otros delitos" del Ministerio del Interior
(catalogodatos.gub.uy) y lo deja en un formato limpio y liviano (parquet).
"""
from pathlib import Path
import pandas as pd

import contratos

ADAPTACIONES = []  # qué sinónimos se usaron en la última lectura (para la bitácora)


def load_denuncias(csv_path: str | Path) -> pd.DataFrame:
    cabecera = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", nrows=0).columns
    mapa, adapt = contratos.resolver("denuncias_mi", cabecera)
    ADAPTACIONES[:] = adapt
    df = pd.read_csv(csv_path, sep=";", encoding="utf-8-sig", dtype=str, usecols=list(mapa.values()))
    df = df.rename(columns={real: logico for logico, real in mapa.items()})
    for c in contratos.CONTRATOS["denuncias_mi"]["opcionales"]:
        if c not in df.columns:
            df[c] = None
    contratos.verificar_volumen("denuncias_mi", len(df))
    df["FECHA"] = pd.to_datetime(df["FECHA"], format="%d.%m.%Y", errors="coerce")
    if df["FECHA"].isna().mean() > 0.5:  # ¿cambió el formato de fecha?
        df["FECHA"] = pd.to_datetime(df["FECHA"].astype(str), errors="coerce", dayfirst=True, format="mixed")
    bad = df["FECHA"].isna().sum()
    if bad:
        print(f"[ingest] aviso: {bad} filas con fecha inválida descartadas")
    df = df.dropna(subset=["FECHA"])
    df["HORA"] = pd.to_numeric(df["HORA"], errors="coerce")  # 'SIN DATO' -> NaN
    df["SECCIONAL_ID"] = df["DEPTO"] + " · " + df["JURISDICCION"].fillna("SIN DATO")
    for c in ["DELITO", "DEPTO", "BARRIO_MONTEVIDEO", "DIA_SEMANA", "VICT_RAP", "VICT_HUR", "TENTATIVA"]:
        df[c] = df[c].astype("category")
    return df


def check_quality(df: pd.DataFrame) -> dict:
    """Controles automáticos: 3S los corre en cada ingesta y se detiene si fallan."""
    report = {
        "filas": len(df),
        "fecha_min": str(df["FECHA"].min().date()),
        "fecha_max": str(df["FECHA"].max().date()),
        "delitos": df["DELITO"].value_counts().to_dict(),
    }
    problems = []
    if len(df) < 1_000_000:
        problems.append("muy pocas filas: ¿descarga incompleta?")
    if (pd.Timestamp.today() - df["FECHA"].max()).days > 200:
        problems.append("los datos tienen más de 200 días: ¿cambió la fuente?")
    report["problemas"] = problems
    return report


if __name__ == "__main__":
    import json, sys
    src = sys.argv[1]
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/denuncias.parquet")
    df = load_denuncias(src)
    rep = check_quality(df)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    if rep["problemas"]:
        sys.exit("[ingest] control de calidad falló; no se sobrescriben los datos")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"[ingest] guardado {out}")
