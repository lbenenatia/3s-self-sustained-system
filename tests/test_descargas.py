"""Prueba de las descargas con un servidor local (sin internet).
Reproduce lo que pasó en el CI: el servidor corta la conexión a mitad de archivo sin avisar el
tamaño total (sin Content-Length). 3S tiene que darse cuenta, reanudar desde donde quedó y terminar
con el archivo completo. También verifica que una página de error se rechace sin reemplazar la copia anterior."""
import sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src" / "s3"))
import descargas
import guardas

guardas.verificar_url = lambda url: None  # el servidor de prueba es local, fuera de la lista blanca
descargas.ESPERA_S = 0

DATOS = bytes(range(256)) * 8_000  # ~2 MB
CORTE = 300_000
pedidos = []
si_rango = []


class Servidor(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        rango = self.headers.get("Range")
        pedidos.append(rango)
        if self.path == "/error":
            cuerpo = b"<!DOCTYPE html><html><body>Mantenimiento</body></html>" * 50_000
            self.send_response(200)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
        elif self.path == "/goteo":  # corta cada CORTE bytes, siempre: muchos más cortes que intentos
            desde = int(rango.split("=")[1].rstrip("-")) if rango else 0
            self.send_response(206 if rango else 200)
            if rango:
                self.send_header("Content-Range", f"bytes {desde}-{len(DATOS) - 1}/{len(DATOS)}")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(DATOS[desde:desde + CORTE // 3])
            self.close_connection = True
        elif self.path == "/cambia":  # el archivo se republica entre el primer tramo y la reanudación
            if rango is None:
                self.send_response(200)
                self.send_header("ETag", '"vieja"')
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(DATOS[:CORTE])
                self.close_connection = True
            else:
                si_rango.append(self.headers.get("If-Range"))
                nueva = DATOS[::-1]  # If-Range no coincide con la versión actual: se manda la nueva entera
                self.send_response(200)
                self.send_header("ETag", '"nueva"')
                self.send_header("Content-Length", str(len(nueva)))
                self.end_headers()
                self.wfile.write(nueva)
        elif rango is None:  # primer pedido: sin Content-Length y cortado a mitad
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(DATOS[:CORTE])
            self.close_connection = True
        else:
            desde = int(rango.split("=")[1].rstrip("-"))
            resto = DATOS[desde:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {desde}-{len(DATOS) - 1}/{len(DATOS)}")
            self.send_header("Content-Length", str(len(resto)))
            self.end_headers()
            self.wfile.write(resto)


    def do_HEAD(self):
        pedidos.append("HEAD")
        self.send_response(200)
        self.send_header("ETag", ETAG)
        self.send_header("Content-Length", str(len(DATOS)))
        self.end_headers()


ETAG = '"v1"'
srv = ThreadingHTTPServer(("127.0.0.1", 0), Servidor)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
minimo_mb = len(DATOS) / 1e6 * 0.9

with tempfile.TemporaryDirectory() as tmp:
    destino = Path(tmp) / "fuente.csv"

    # 1. Corte silencioso: se reanuda y termina completo
    mb, _ = descargas._bajar(f"{base}/datos", destino, minimo_mb)
    assert destino.read_bytes() == DATOS, "el archivo reanudado no coincide con el original"
    assert pedidos == [None, f"bytes={CORTE}-"], f"pedidos inesperados: {pedidos}"
    print(f"ok: corte sin aviso detectado y reanudado ({mb} MB)")

    # 2. Página de error: se rechaza enseguida y la copia anterior queda intacta
    pedidos.clear()
    try:
        descargas._bajar(f"{base}/error", destino, minimo_mb)
        raise AssertionError("una página web no debería aceptarse como datos")
    except descargas.NoSonDatos:
        pass
    assert len(pedidos) == 1, "una página de error no debe reintentarse"
    assert destino.read_bytes() == DATOS, "la copia anterior no debe tocarse"
    assert not destino.with_suffix(".csv.parcial").exists()
    print("ok: página de error rechazada sin tocar la copia anterior")

    # 3. Muchos cortes seguidos: mientras cada intento avance, se sigue (el límite es el tiempo)
    pedidos.clear()
    goteo = Path(tmp) / "goteo.csv"
    descargas._bajar(f"{base}/goteo", goteo, minimo_mb)
    assert goteo.read_bytes() == DATOS, "el archivo con muchos cortes no coincide"
    assert len(pedidos) > descargas.INTENTOS_SIN_AVANCE, "debió reanudar más veces que el límite sin avance"
    print(f"ok: {len(pedidos)} cortes seguidos, reanudado hasta el final")

    # 4. Si el archivo publicado no cambió (mismo ETag), no se vuelve a bajar
    assert descargas._sin_cambios(f"{base}/datos", {"etag": ETAG}) is True
    assert descargas._sin_cambios(f"{base}/datos", {"etag": '"v0"'}) is False
    assert descargas._sin_cambios(f"{base}/datos", {}) is False
    print("ok: un archivo sin cambios no se vuelve a descargar")

    # 5. Si el archivo se republica a mitad de la descarga, no se mezclan dos versiones
    cambia = Path(tmp) / "cambia.csv"
    _, version = descargas._bajar(f"{base}/cambia", cambia, minimo_mb)
    assert si_rango == ['"vieja"'], f"la reanudación debió mandar If-Range con el ETag: {si_rango}"
    assert cambia.read_bytes() == DATOS[::-1], "el archivo mezcló la versión vieja con la nueva"
    assert version.get("etag") == '"nueva"', f"debió quedar anotada la versión nueva: {version}"
    print("ok: archivo republicado a mitad de descarga, sin mezclar versiones")

srv.shutdown()
print("test_descargas: todo bien")
