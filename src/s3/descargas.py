"""Descargas automáticas de 3S.

Cada fuente se baja a un archivo temporal, se valida (tamaño mínimo y que no sea una página de error)
y recién entonces reemplaza a la versión anterior. Si algo falla, 3S sigue con la última copia buena.
Solo se descarga de los dominios de la lista blanca sellada (ver guardas.py).
"""
import json
import shutil
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import guardas

RAIZ = Path(__file__).resolve().parents[2]
ESTADO = RAIZ / "state" / "descargas.json"
AGENTE = "3S-modulo-seguridad/0.3 (proyecto personal; datos abiertos)"


def _estado():
    return json.loads(ESTADO.read_text()) if ESTADO.exists() else {}


def _bajar(url, destino: Path, minimo_mb: float):
    guardas.verificar_url(url)
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    destino.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        guardas.verificar_url(r.geturl())  # también la URL final, por si hubo redirección
        shutil.copyfileobj(r, f, length=1 << 20)
    mb = tmp.stat().st_size / 1e6
    inicio = tmp.open("rb").read(200).lower()
    if mb < minimo_mb:
        tmp.unlink()
        raise ValueError(f"archivo demasiado chico ({mb:.2f} MB < {minimo_mb} MB)")
    if inicio.lstrip().startswith((b"<!doctype html", b"<html")):
        tmp.unlink()
        raise ValueError("el servidor devolvió una página web en lugar de datos")
    tmp.replace(destino)
    return round(mb, 2)


def actualizar(cfg, log):
    """Descarga las fuentes vencidas. Devuelve {fuente: 'nuevo' | 'vigente' | 'error: ...'}."""
    estado, res = _estado(), {}
    for nombre, f in cfg.get("descargas", {}).items():
        destino = RAIZ / f["destino"]
        ultimo = estado.get(nombre, {}).get("ok_en", 0)
        if destino.exists() and time.time() - ultimo < f["cada_dias"] * 86400:
            res[nombre] = "vigente"
            continue
        url = f["url"].replace("{ayer}", (date.today() - timedelta(days=1)).isoformat())
        try:
            mb = _bajar(url, destino, f["tamano_minimo_mb"])
            estado[nombre] = {"ok_en": time.time(), "mb": mb, "url": url}
            res[nombre] = "nuevo"
            log("descarga", fuente=nombre, mb=mb)
        except guardas.Detener:
            raise
        except Exception as e:  # red caída, servidor cambió, etc.: se sigue con la copia anterior
            estado.setdefault(nombre, {})["ultimo_error"] = f"{type(e).__name__}: {e}"
            res[nombre] = f"error: {type(e).__name__}: {e}"
            log("descarga_fallida", fuente=nombre, detalle=str(e)[:200], usa_copia_anterior=destino.exists())
    ESTADO.parent.mkdir(exist_ok=True)
    ESTADO.write_text(json.dumps(estado, indent=1))
    return res
