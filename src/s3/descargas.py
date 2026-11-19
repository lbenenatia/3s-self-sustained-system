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


INTENTOS_SIN_AVANCE = 5   # intentos seguidos que no suman ni un byte antes de rendirse
ESPERA_S = 20
TOPE_S = 100 * 60         # tiempo máximo por archivo: desde GitHub el catálogo del MI va a ~200 KB/s


class Cortada(IOError):
    """El servidor cerró la conexión antes de mandar el archivo completo."""


class NoSonDatos(ValueError):
    """El servidor devolvió una página web en lugar del archivo: reintentar no sirve."""


def _verificar_completo(tmp: Path, minimo_mb: float):
    """Detecta cortes que el servidor no avisa (respuestas sin Content-Length).

    Una página de error se rechaza enseguida; un archivo más chico que el mínimo se trata como
    descarga cortada, así el próximo intento la continúa desde donde quedó.
    """
    if tmp.open("rb").read(200).lower().lstrip().startswith((b"<!doctype html", b"<html")):
        raise NoSonDatos("el servidor devolvió una página web en lugar de datos")
    mb = tmp.stat().st_size / 1e6
    if mb < minimo_mb:
        raise Cortada(f"archivo incompleto ({mb:.2f} MB < {minimo_mb} MB)")


def _bajar(url, destino: Path, minimo_mb: float, avisar=lambda etapa, **datos: None):
    """Descarga con reintentos y reanudación.

    Los servidores oficiales a veces se cuelgan o cortan la conexión a mitad de un archivo grande.
    Cada reintento continúa desde el último byte recibido (HTTP Range) si el servidor lo permite.
    """
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)  # nunca se reanuda un parcial de otra corrida: podría ser otra versión
    inicio, sin_avance, meta = time.monotonic(), 0, {}
    while True:
        antes = tmp.stat().st_size if tmp.exists() else 0
        try:
            _bajar_tramo(url, tmp, meta)
            _verificar_completo(tmp, minimo_mb)
            break
        except (guardas.Detener, NoSonDatos):
            tmp.unlink(missing_ok=True)
            raise
        except Exception as e:
            # mientras cada intento sume bytes, se sigue: el límite es el tiempo, no la cantidad de cortes
            despues = tmp.stat().st_size if tmp.exists() else 0
            sin_avance = 0 if despues > antes else sin_avance + 1
            if sin_avance >= INTENTOS_SIN_AVANCE or time.monotonic() - inicio > TOPE_S:
                tmp.unlink(missing_ok=True)
                raise
            avisar("descarga_reanuda", mb=round(despues / 1e6, 1), minutos=round((time.monotonic() - inicio) / 60, 1),
                   sin_avance=sin_avance, motivo=f"{type(e).__name__}: {e}"[:120])
            time.sleep(min(ESPERA_S * max(sin_avance, 1), 120))
    mb = tmp.stat().st_size / 1e6
    tmp.replace(destino)  # recién ahora, ya validado, reemplaza a la copia anterior
    return round(mb, 2), meta


def _version(headers):
    """Lo que identifica la versión publicada de un archivo (para no volver a bajarlo si no cambió)."""
    v = {"etag": headers.get("ETag"), "modificado": headers.get("Last-Modified")}
    return {k: x for k, x in v.items() if x}


def _sin_cambios(url, previo: dict):
    """Pregunta al servidor (HEAD, sin bajar nada) si el archivo sigue siendo el mismo que ya tenemos."""
    if not previo.get("etag") and not previo.get("modificado"):
        return False
    guardas.verificar_url(url)
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            guardas.verificar_url(r.geturl())
            actual = _version(r.headers)
    except guardas.Detener:
        raise
    except Exception:
        return False  # si la consulta falla, se intenta la descarga normal
    claves = [k for k in ("etag", "modificado") if previo.get(k) and actual.get(k)]
    return bool(claves) and all(previo[k] == actual[k] for k in claves)


def _bajar_tramo(url, tmp: Path, meta: dict | None = None):
    """Baja (o continúa bajando) el archivo en `tmp`. Lanza Cortada si llegó incompleto.
    En el primer tramo anota en `meta` la versión publicada (ETag / Last-Modified)."""
    guardas.verificar_url(url)
    ya = tmp.stat().st_size if tmp.exists() else 0
    headers = {"User-Agent": AGENTE}
    if ya:
        headers["Range"] = f"bytes={ya}-"
        # If-Range: si el archivo publicado cambió desde el primer tramo, el servidor manda la versión
        # nueva completa (200) en vez del resto de la vieja, así nunca se mezclan dos versiones
        etag = (meta or {}).get("etag", "")
        validador = etag if etag and not etag.startswith("W/") else (meta or {}).get("modificado")
        if validador:
            headers["If-Range"] = validador
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        guardas.verificar_url(r.geturl())  # también la URL final, por si hubo redirección
        if ya and r.status == 206:
            modo = "ab"
            total = int(r.headers.get("Content-Range", "/0").rsplit("/", 1)[-1] or 0)
        else:  # primer tramo, o el servidor ignoró el Range: se empieza de cero
            modo, ya = "wb", 0
            total = int(r.headers.get("Content-Length") or 0)
            if meta is not None:
                meta.clear()
                meta.update(_version(r.headers))
        with open(tmp, modo) as f:
            shutil.copyfileobj(r, f, length=1 << 20)
    recibido = tmp.stat().st_size
    if total and recibido < total:
        raise Cortada(f"conexión cortada: {recibido / 1e6:.1f} de {total / 1e6:.1f} MB")


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
            previo = estado.get(nombre, {})
            if destino.exists() and previo.get("url") == url and _sin_cambios(url, previo):
                previo["ok_en"] = time.time()
                previo.pop("ultimo_error", None)
                res[nombre] = "vigente"
                log("descarga_sin_cambios", fuente=nombre)
                continue
            mb, version = _bajar(url, destino, f["tamano_minimo_mb"], avisar=lambda e, **k: log(e, fuente=nombre, **k))
            estado[nombre] = {"ok_en": time.time(), "mb": mb, "url": url, **version}
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
