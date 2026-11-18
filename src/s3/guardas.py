"""Guardas de seguridad de 3S. Este archivo está SELLADO: el sistema no puede modificarlo.

Reglas que se hacen cumplir en cada corrida:
  1. Interruptor de apagado: si existe state/STOP, 3S no hace nada.
  2. Integridad: si este archivo o la sección [seguridad] de config.toml cambiaron sin que
     un humano vuelva a sellar (python run.py --sellar), 3S se detiene.
  3. Sin datos de personas: las señales solo pueden ser conteos agregados por barrio y período.
  4. Sin gasto: 3S no tiene credenciales de pago ni llama a servicios pagos.
  5. Red solo con permiso: 3S solo descarga de los dominios de la lista blanca sellada.
"""
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[2]
STOP = RAIZ / "state" / "STOP"
SELLO = RAIZ / "state" / "sello.json"
PROHIBIDAS = ("EDAD", "SEXO", "NACIONALIDAD", "ANTECEDENTES", "ID_VICTIMA", "ID_EVENTO", "REL_VICT")


class Detener(Exception):
    pass


def _huella():
    cfg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8"))
    partes = {
        # se normalizan los saltos de línea para que el sello valga igual en Windows y en Linux
        "guardas.py": hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "config.seguridad": hashlib.sha256(json.dumps(cfg.get("seguridad", {}), sort_keys=True).encode()).hexdigest(),
    }
    return partes


def sellar():
    """Solo lo corre un humano: registra la versión aprobada de las reglas."""
    SELLO.parent.mkdir(exist_ok=True)
    SELLO.write_text(json.dumps(_huella(), indent=1))
    print("[guardas] reglas selladas:", SELLO)


def verificar():
    if STOP.exists():
        raise Detener("interruptor de apagado activado (state/STOP). Borralo para reactivar.")
    if not SELLO.exists():
        raise Detener("las reglas no están selladas. Un humano debe correr: python run.py --sellar")
    if json.loads(SELLO.read_text()) != _huella():
        raise Detener("las reglas de seguridad cambiaron sin aprobación humana. Revisá y volvé a sellar.")


def verificar_url(url):
    seg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8")).get("seguridad", {})
    if not seg.get("permite_red", False):
        raise Detener("la red está desactivada en las reglas selladas")
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or host not in seg.get("dominios_permitidos", []):
        raise Detener(f"dominio no permitido: {host} (solo https y la lista blanca sellada)")


def verificar_senales(columnas):
    malas = [c for c in columnas if any(p in c.upper() for p in PROHIBIDAS)]
    if malas:
        raise Detener(f"señales con datos de personas no permitidas: {malas}")


if __name__ == "__main__":
    if "--sellar" in sys.argv:
        sellar()
    else:
        verificar()
        print("[guardas] OK")
