"""El agente en Discord, al instante: atiende los comandos con barra (/) que Discord le envía.

Cada vez que alguien usa un comando, Discord le manda un pedido FIRMADO a la función de 3S en Vercel,
que tiene 3 segundos para contestar. Este módulo decide la respuesta; no sabe nada de HTTP.

Reglas (las mismas de agente/__init__.py):
  - Sin firma válida de Discord, no se atiende nada.
  - Solo obedece a DISCORD_USUARIOS. A cualquier otra cuenta le contesta, solo a ella, que no está autorizada.
  - Herramientas de solo lectura. Las únicas acciones son correr, apagar y prender el workflow "3S semanal",
    con un permiso de GitHub limitado a eso. Correr y prender piden tocar "Confirmar" (vence en 10 minutos,
    y el botón desaparece al usarlo). Apagar es inmediato: 3S nunca se resiste a que lo apaguen.
  - El texto libre solo entra por /preguntar y va al modelo de lenguaje como pregunta, nunca como orden.
  - Nunca menciona a nadie: las menciones están desactivadas en todas las respuestas.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

from . import ed25519
from . import herramientas as H

# tipos de Discord
PING, COMANDO, BOTON, AUTOCOMPLETAR = 1, 2, 3, 4
R_PONG, R_MENSAJE, R_ACTUALIZAR, R_OPCIONES = 1, 4, 7, 8
SOLO_VOS = 64          # mensaje que solo ve quien usó el comando
VENCE_SEG = 600
VENTANA_FIRMA_SEG = 300

AYUDA = """**Qué puede hacer 3S** (escribí `/` y elegí)
• `/estado` · última corrida, datos, campeones y alertas
• `/alertas` · alertas de desvío del último trimestre (podés filtrar por delito)
• `/barrio` · cómo viene un barrio (te sugiere los nombres mientras escribís)
• `/ranking` · los 10 barrios con más denuncias del último trimestre
• `/preguntar` · preguntas en tus palabras (cuando tenga un modelo de lenguaje)
• `/correr` · correr 3S ahora (pide confirmación)
• `/apagar` · apagar las corridas automáticas (inmediato)
• `/encender` · volver a prenderlas (pide confirmación)"""

SIN_MODELO = ("Todavía no tengo un modelo de lenguaje enchufado, así que no entiendo preguntas libres. "
              "Probá con `/barrio`, `/alertas`, `/ranking` o `/estado`.")

QUE = {"correr": "correr 3S ahora", "encender": "volver a prender las corridas automáticas"}
HECHO = {"correr": "▶️ Listo: la corrida arrancó. Te aviso en #avisos cuando termine.",
         "encender": "✅ Corridas automáticas prendidas de nuevo.",
         "apagar": "⛔ Corridas automáticas apagadas. Para volver a prenderlas: `/encender`."}


# ------------------------------------------------------------------------------------------ firma
def firma_valida(cuerpo: bytes, firma_hex: str, marca: str, clave_hex: str, ahora=None) -> bool:
    try:
        if abs((ahora or time.time()) - int(marca)) > VENTANA_FIRMA_SEG:   # evita reenvíos viejos
            return False
        return ed25519.verificar(bytes.fromhex(clave_hex), marca.encode() + cuerpo, bytes.fromhex(firma_hex))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------------------- GitHub
class GitHub:
    """Las tres únicas acciones. El token es fino: solo Actions de este repositorio."""
    API = "https://api.github.com"

    def __init__(self, token, repo, flujo="semanal.yml"):
        self._token, self.repo, self.flujo = token, repo, flujo

    def _pedir(self, metodo, ruta, cuerpo=None):
        import guardas
        url = f"{self.API}/repos/{self.repo}/actions/workflows/{self.flujo}{ruta}"
        guardas.verificar_url(url)
        req = urllib.request.Request(url, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo else None,
                                     headers={"Authorization": f"Bearer {self._token}",
                                              "Accept": "application/vnd.github+json",
                                              "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "3S-agente"})
        with urllib.request.urlopen(req, timeout=2.2):   # Discord espera como máximo 3 segundos
            pass

    def correr(self):
        self._pedir("POST", "/dispatches", {"ref": "main"})

    def apagar(self):
        self._pedir("PUT", "/disable")

    def encender(self):
        self._pedir("PUT", "/enable")


# ---------------------------------------------------------------------------------------- botones
def _sello_boton(accion, emitido, clave):
    return hmac.new(clave, f"{accion}|{emitido}".encode(), hashlib.sha256).hexdigest()[:16]


def boton(accion, emitido, clave):
    return f"{accion}|{emitido}|{_sello_boton(accion, emitido, clave)}"


def leer_boton(custom_id, clave, ahora):
    """Devuelve (accion, error)."""
    try:
        accion, emitido, sello = custom_id.split("|")
        emitido = int(emitido)
    except ValueError:
        return None, "Botón inválido."
    if accion == "cancelar":
        return "cancelar", None
    if accion not in QUE or not hmac.compare_digest(sello, _sello_boton(accion, emitido, clave)):
        return None, "Botón inválido."
    if ahora - emitido > VENCE_SEG:
        return None, "Esta confirmación venció. Pedí la acción de nuevo."
    return accion, None


# ------------------------------------------------------------------------------------------ armado
def _texto(contenido, solo_vos=False, tipo=R_MENSAJE, botones=None):
    if len(contenido) > 1990:
        contenido = contenido[:1980].rsplit("\n", 1)[0] + "\n…"
    datos = {"content": contenido, "allowed_mentions": {"parse": []}}
    if solo_vos:
        datos["flags"] = SOLO_VOS
    if botones is not None:
        datos["components"] = botones
    return {"type": tipo, "data": datos}


def _opciones(inter):
    return {o["name"]: o.get("value") for o in inter.get("data", {}).get("options", [])}


def _usuario(inter):
    return (inter.get("member", {}).get("user") or inter.get("user") or {}).get("id")


class Config:
    def __init__(self, usuarios, github=None, clave_botones=b"", proveedor=None):
        self.usuarios, self.github, self.clave_botones, self.proveedor = usuarios, github, clave_botones, proveedor

    @classmethod
    def desde_entorno(cls):
        import tomllib
        from .proveedor import cargar
        usuarios = {u.strip() for u in os.environ.get("DISCORD_USUARIOS", "").split(",") if u.strip()}
        token = os.environ.get("GITHUB_TOKEN_ACCIONES", "")
        repo = os.environ.get("GITHUB_REPO", "lbenenatia/3s-self-sustained-system")
        cfg = tomllib.loads((H.RAIZ / "config.toml").read_text(encoding="utf-8"))
        clave = hashlib.sha256(b"3s-botones|" + token.encode()).digest()
        return cls(usuarios, GitHub(token, repo) if token else None, clave, cargar(cfg))


def _accion(cfg, accion):
    if cfg.github is None:
        return "No tengo permiso de GitHub configurado (falta GITHUB_TOKEN_ACCIONES en Vercel)."
    try:
        getattr(cfg.github, accion)()
        return HECHO[accion]
    except urllib.error.HTTPError as e:
        return f"❌ GitHub respondió {e.code} al intentar {accion}. Revisá el permiso GITHUB_TOKEN_ACCIONES."
    except Exception as e:
        return f"❌ No pude {accion}: {type(e).__name__}. Probá de nuevo o hacelo desde GitHub Actions."


def atender(inter, cfg: Config, ahora=None):
    """Recibe el pedido de Discord (ya con la firma verificada) y devuelve la respuesta."""
    ahora = int(ahora or time.time())
    tipo = inter.get("type")
    if tipo == PING:
        return {"type": R_PONG}
    autorizado = _usuario(inter) in cfg.usuarios
    if tipo == AUTOCOMPLETAR:
        if not autorizado:
            return {"type": R_OPCIONES, "data": {"choices": []}}
        texto = str(_opciones(inter).get("nombre") or "")
        return {"type": R_OPCIONES, "data": {"choices": H.sugerir_barrios(texto)}}
    if not autorizado:
        return _texto("No estás autorizado para usar 3S.", solo_vos=True)

    if tipo == BOTON:
        accion, error = leer_boton(inter.get("data", {}).get("custom_id", ""), cfg.clave_botones, ahora)
        if error:
            return _texto(error, tipo=R_ACTUALIZAR, botones=[])
        if accion == "cancelar":
            return _texto("Cancelado. No se hizo nada.", tipo=R_ACTUALIZAR, botones=[])
        quien = f"<@{_usuario(inter)}>"
        return _texto(f"{_accion(cfg, accion)} (confirmó {quien})", tipo=R_ACTUALIZAR, botones=[])

    if tipo != COMANDO:
        return _texto("No entendí ese pedido.", solo_vos=True)
    nombre = inter.get("data", {}).get("name")
    op = _opciones(inter)
    if nombre == "ayuda":
        return _texto(AYUDA)
    if nombre == "estado":
        return _texto(H.estado())
    if nombre == "alertas":
        return _texto(H.alertas(op.get("delito")))
    if nombre == "barrio":
        return _texto(H.barrio(str(op.get("nombre", ""))))
    if nombre == "ranking":
        return _texto(H.ranking(op.get("delito") or "RAPIÑA"))
    if nombre == "preguntar":
        pregunta = str(op.get("texto", ""))[:500]
        respuesta = None
        if cfg.proveedor is not None:
            try:
                respuesta = cfg.proveedor.responder(pregunta, H.contexto())
            except Exception as e:
                print(f"[agente] el modelo falló: {type(e).__name__}")
        return _texto(respuesta or SIN_MODELO)
    if nombre == "apagar":
        return _texto(_accion(cfg, "apagar"))
    if nombre in QUE:
        botones = [{"type": 1, "components": [
            {"type": 2, "style": 4 if nombre == "correr" else 3, "label": "Confirmar",
             "custom_id": boton(nombre, ahora, cfg.clave_botones)},
            {"type": 2, "style": 2, "label": "Cancelar", "custom_id": "cancelar|0|-"}]}]
        return _texto(f"¿Confirmás **{QUE[nombre]}**? Tenés 10 minutos.", botones=botones)
    return _texto("No conozco ese comando. Probá `/ayuda`.", solo_vos=True)
