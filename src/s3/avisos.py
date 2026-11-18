"""Avisos por Telegram.

El token del bot y el chat NUNCA están en el código: se leen de variables de entorno
(en GitHub: Settings → Secrets and variables → Actions → TELEGRAM_TOKEN y TELEGRAM_CHAT_ID).
Si no están definidas, 3S imprime el aviso y sigue: un aviso que no sale nunca debe frenar una corrida.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse
import urllib.request

import guardas

API = "https://api.telegram.org"


def enviar(texto: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print("[aviso]", texto.replace("\n", " | ")[:500])
    if not token or not chat:
        return False
    url = f"{API}/bot{token}/sendMessage"
    try:
        guardas.verificar_url(url)
        datos = urllib.parse.urlencode({"chat_id": chat, "text": texto[:4000],
                                        "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(urllib.request.Request(url, data=datos), timeout=30) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:  # nunca imprimir la URL: contiene el token
        print(f"[aviso] no se pudo enviar por Telegram: {type(e).__name__}")
        return False


def latido(max_dias=10):
    """Avisa si hace demasiado que no hay una corrida exitosa (por ejemplo, si GitHub pausó el workflow)."""
    f = Path(__file__).resolve().parents[2] / "state" / "ultima_ok.json"
    if not f.exists():
        enviar("⚠️ 3S · latido: nunca hubo una corrida exitosa registrada")
        return False
    dias = (datetime.now(timezone.utc) - datetime.fromisoformat(json.loads(f.read_text())["fecha"])).days
    if dias > max_dias:
        enviar(f"⚠️ 3S · latido: hace {dias} días que no hay una corrida exitosa. Revisá GitHub Actions.")
        return False
    print(f"[latido] OK: última corrida exitosa hace {dias} días")
    return True
