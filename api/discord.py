"""Función de Vercel que recibe los comandos de Discord (Fase 6).

Discord la llama cada vez que alguien usa un comando con barra en el servidor de 3S. Se despliega sola
con cada cambio en main, así que siempre lee los datos que dejó la última corrida semanal.

Variables de entorno en Vercel (Settings → Environment Variables):
  DISCORD_PUBLIC_KEY      clave pública de la aplicación (portal de Discord → General Information)
  DISCORD_USUARIOS        ids de las cuentas autorizadas, separados por coma
  GITHUB_TOKEN_ACCIONES   token fino de GitHub, solo "Actions: read and write" en este repositorio
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "s3"))
import guardas  # noqa: E402
from agente import interacciones as I  # noqa: E402

MAX_CUERPO = 64_000


class handler(BaseHTTPRequestHandler):
    def _responder(self, codigo, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._responder(200, {"3S": "agente en línea", "uso": "Discord envía los comandos por POST"})

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > MAX_CUERPO:
            return self._responder(400, {"error": "pedido inválido"})
        cuerpo = self.rfile.read(largo)
        if not I.firma_valida(cuerpo, self.headers.get("X-Signature-Ed25519", ""),
                              self.headers.get("X-Signature-Timestamp", ""),
                              os.environ.get("DISCORD_PUBLIC_KEY", "")):
            return self._responder(401, {"error": "firma inválida"})
        try:
            inter = json.loads(cuerpo)
        except ValueError:
            return self._responder(400, {"error": "pedido inválido"})
        if inter.get("type") == I.PING:          # Discord verifica así que la dirección es nuestra
            return self._responder(200, {"type": I.R_PONG})
        try:
            guardas.verificar()
            respuesta = I.atender(inter, I.Config.desde_entorno())
        except guardas.Detener as e:
            respuesta = I._texto(f"⛔ 3S está detenido por sus guardas: {e}", solo_vos=True)
        except Exception as e:                   # siempre contestar algo; nunca un error mudo
            print(f"[agente] error: {type(e).__name__}: {e}")
            respuesta = I._texto(f"❌ Algo falló de mi lado ({type(e).__name__}). Probá de nuevo en un rato.",
                                 solo_vos=True)
        self._responder(200, respuesta)

    def log_message(self, *args):   # sin registros con datos de los pedidos
        pass
