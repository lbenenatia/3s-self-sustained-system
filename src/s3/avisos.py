"""Avisos de 3S: Discord (canal #avisos) y, mientras dure la transición, también Telegram.

Las direcciones y tokens NUNCA están en el código: se leen de variables de entorno
(en GitHub: Settings → Secrets and variables → Actions):
  DISCORD_WEBHOOK_AVISOS            webhook del canal #avisos (lo principal)
  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID  el canal anterior; se puede borrar cuando Discord ande bien
Si no hay ninguno definido, 3S imprime el aviso y sigue: un aviso que no sale nunca debe frenar una corrida.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse
import urllib.request

import guardas

API_TELEGRAM = "https://api.telegram.org"
AGENTE_HTTP = "DiscordBot (https://github.com/lbenenatia/3s-self-sustained-system, 1.0)"
LIMITE_DISCORD = 1900   # Discord corta en 2000 caracteres por mensaje


def partir(texto: str, limite: int = LIMITE_DISCORD):
    """Divide un texto largo en trozos que respetan los saltos de línea."""
    trozos, actual = [], ""
    for linea in texto.split("\n"):
        while len(linea) > limite:
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.append(linea[:limite])
            linea = linea[limite:]
        if len(actual) + len(linea) + 1 > limite:
            trozos.append(actual)
            actual = linea
        else:
            actual = f"{actual}\n{linea}" if actual else linea
    if actual:
        trozos.append(actual)
    return trozos or [""]


def _discord(texto: str) -> bool:
    url = os.environ.get("DISCORD_WEBHOOK_AVISOS")
    if not url:
        return False
    try:
        guardas.verificar_url(url)
        for trozo in partir(texto):
            cuerpo = json.dumps({"content": trozo, "username": "3S",
                                 "allowed_mentions": {"parse": []}}).encode()   # nunca @everyone
            req = urllib.request.Request(url, data=cuerpo, method="POST", headers={
                "Content-Type": "application/json", "User-Agent": AGENTE_HTTP})
            with urllib.request.urlopen(req, timeout=30):
                pass
        return True
    except Exception as e:  # nunca imprimir la URL: quien la tenga puede escribir en el canal
        print(f"[aviso] no se pudo enviar por Discord: {type(e).__name__}")
        return False


def _telegram(texto: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    url = f"{API_TELEGRAM}/bot{token}/sendMessage"
    try:
        guardas.verificar_url(url)
        datos = urllib.parse.urlencode({"chat_id": chat, "text": texto[:4000],
                                        "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:  # nunca imprimir la URL: contiene el token
        print(f"[aviso] no se pudo enviar por Telegram: {type(e).__name__}")
        return False


def enviar(texto: str) -> bool:
    print("[aviso]", texto.replace("\n", " | ")[:500])
    ok_discord = _discord(texto)
    ok_telegram = _telegram(texto)
    return ok_discord or ok_telegram


def latido(max_dias=10):
    """Avisa si hace demasiado que no hay una corrida exitosa (por ejemplo, si GitHub pausó el workflow)."""
    f = Path(__file__).resolve().parents[2] / "state" / "ultima_ok.json"
    if not f.exists():
        enviar("⚠️ 3S · latido: nunca hubo una corrida exitosa registrada")
        return False
    dias = (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(f.read_text())["fecha"])).days
    if dias > max_dias:
        enviar(f"⚠️ 3S · latido: hace {dias} días que no hay una corrida exitosa. Revisá GitHub Actions "
               "(o si alguien la apagó con !apagar, prendela con !encender).")
        return False
    print(f"[latido] OK: última corrida exitosa hace {dias} días")
    return True
