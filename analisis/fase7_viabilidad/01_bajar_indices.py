"""Fase 7 · prueba de viabilidad · paso 1: bajar los índices mensuales de dos medios.

Análisis LOCAL, fuera de 3S: no lo llama el orquestador ni corre en GitHub Actions, y no toca la
lista blanca sellada. Solo baja los índices mensuales que cada medio publica en su robots.txt
(enlace y fecha de cada nota). Nunca baja el texto de las notas.

Los archivos quedan en data/noticias_viabilidad/ (fuera del repositorio).

Uso:  python analisis/fase7_viabilidad/01_bajar_indices.py [desde=201701]
"""
import re
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "data" / "noticias_viabilidad"
MEDIOS = {
    "subrayado": "https://www.subrayado.com.uy/sitemap/news-full/sitemap-index.xml",
    "observador": "https://www.elobservador.com.uy/sitemap/news-full/sitemap-index.xml",
}
PERMITIDOS = {urlparse(u).hostname for u in MEDIOS.values()}
AGENTE = "Mozilla/5.0 (compatible; relevamiento-indices/0.1)"
PAUSA_S = 2.0


def bajar(url):
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in PERMITIDOS:
        raise ValueError(f"dominio no previsto: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as r:
        if urlparse(r.geturl()).hostname not in PERMITIDOS:
            raise ValueError(f"redirección a un dominio no previsto: {r.geturl()}")
        return r.read()


def main(desde="201701"):
    for medio, indice in MEDIOS.items():
        carpeta = DESTINO / medio
        carpeta.mkdir(parents=True, exist_ok=True)
        meses = re.findall(r"<loc>([^<]+sitemap-(\d{6})\.xml\.gz)</loc>", bajar(indice).decode("utf-8", "ignore"))
        time.sleep(PAUSA_S)
        actual = max(m for _, m in meses)
        nuevos = fallas = 0
        for url, mes in sorted(meses, key=lambda x: x[1]):
            archivo = carpeta / f"{mes}.xml.gz"
            if mes < desde or (archivo.exists() and mes != actual):
                continue
            try:
                archivo.write_bytes(bajar(url))
                nuevos += 1
            except Exception as e:  # un mes que falla no frena el resto
                fallas += 1
                print(f"[{medio}] {mes}: {type(e).__name__}: {e}"[:200])
            time.sleep(PAUSA_S)
        print(f"[{medio}] meses publicados: {len(meses)} · bajados ahora: {nuevos} · fallas: {fallas}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
