"""Cliente mínimo de la API de Discord (solo biblioteca estándar).

El bot no queda conectado: cada pocos minutos el workflow lo despierta, lee los mensajes nuevos del
canal #agente, contesta y termina. Todas las direcciones pasan por la lista blanca sellada.
"""
import json
import time
import urllib.error
import urllib.request

import guardas
from avisos import AGENTE_HTTP, partir

API = "https://discord.com/api/v10"


class ErrorDiscord(Exception):
    pass


class Discord:
    def __init__(self, token: str, canal: str):
        self._token = token
        self.canal = canal
        self._yo = None

    def _pedir(self, metodo, ruta, cuerpo=None, reintentar=True):
        url = API + ruta
        guardas.verificar_url(url)
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(url, data=datos, method=metodo, headers={
            "Authorization": f"Bot {self._token}", "User-Agent": AGENTE_HTTP,
            "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                texto = r.read()
                return json.loads(texto) if texto else None
        except urllib.error.HTTPError as e:
            if e.code == 429 and reintentar:   # límite de velocidad: esperar lo que pide y reintentar una vez
                espera = float(json.loads(e.read() or b"{}").get("retry_after", 2))
                time.sleep(min(espera, 10))
                return self._pedir(metodo, ruta, cuerpo, reintentar=False)
            # nunca se imprime el token; solo el código y la ruta
            raise ErrorDiscord(f"Discord respondió {e.code} en {metodo} {ruta.split('?')[0]}") from None

    def yo(self) -> str:
        if self._yo is None:
            self._yo = self._pedir("GET", "/users/@me")["id"]
        return self._yo

    def mensajes(self, limite=50):
        """Últimos mensajes del canal, del más nuevo al más viejo."""
        return self._pedir("GET", f"/channels/{self.canal}/messages?limit={limite}") or []

    def responder(self, texto, referencia=None):
        for i, trozo in enumerate(partir(texto)):
            cuerpo = {"content": trozo, "allowed_mentions": {"parse": []}}
            if referencia and i == 0:
                cuerpo["message_reference"] = {"message_id": referencia, "fail_if_not_exists": False}
            self._pedir("POST", f"/channels/{self.canal}/messages", cuerpo)
