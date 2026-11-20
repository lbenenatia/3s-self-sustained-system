"""El agente en Discord: lee el canal #agente, contesta y decide acciones (que ejecuta el workflow).

No guarda estado propio: sabe qué mensajes ya atendió porque son los anteriores a su última respuesta
en el canal, y verifica las confirmaciones leyendo sus propios mensajes. Así no hay archivos que se
puedan desincronizar ni commits cada pocos minutos.
"""
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from . import herramientas as H

PREFIJOS = ("!", "/")
VENTANA = timedelta(hours=3)        # mensajes más viejos que esto no se atienden (por ejemplo, tras una caída)
VENCE = timedelta(minutes=20)       # tiempo para confirmar una acción (el bot se despierta cada ~10 min)
ACCIONES_CON_CONFIRMACION = {"correr", "encender"}
MARCA = re.compile(r"\[acción:(\w+) · código:([A-Z0-9]{4})\]")
HECHA = re.compile(r"\[hecho:([A-Z0-9]{4})\]")

AYUDA = """**Comandos de 3S** (empezá con `!`)
• `!estado` · cómo está 3S: última corrida, datos, campeones
• `!alertas` o `!alertas rapiña` · alertas del último trimestre
• `!barrio Cerro` · cómo viene un barrio
• `!ranking hurto` · los 10 barrios con más denuncias del último trimestre
• `!correr` · correr 3S ahora (pide confirmación)
• `!apagar` · apagar las corridas automáticas (inmediato)
• `!encender` · volver a prenderlas (pide confirmación)
Cuando tenga un modelo de lenguaje, también vas a poder preguntarme en texto libre."""

SIN_MODELO = ("Por ahora entiendo solo comandos (todavía no tengo un modelo de lenguaje enchufado). "
              "Escribí `!ayuda` para ver cuáles.")


def _hora(dt):
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/Montevideo")).strftime("%H:%M")
    except Exception:
        return (dt - timedelta(hours=3)).strftime("%H:%M")


def _fecha(m):
    return datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))


def pendientes(mensajes, yo, ahora):
    """Mensajes de personas posteriores a la última respuesta del bot, del más viejo al más nuevo."""
    nuevos = []
    for m in mensajes:                        # vienen del más nuevo al más viejo
        if m["author"]["id"] == yo:
            break
        if ahora - _fecha(m) > VENTANA:
            break
        nuevos.append(m)
    return list(reversed(nuevos))


def _confirmar(codigo, mensajes, yo, ahora):
    """Busca la acción que el bot propuso con ese código. Devuelve (accion, error)."""
    codigo = codigo.upper()
    for m in mensajes:
        if m["author"]["id"] != yo:
            continue
        if any(h == codigo for h in HECHA.findall(m["content"])):
            return None, "Ese código ya se usó."
        for accion, cod in MARCA.findall(m["content"]):
            if cod == codigo:
                if ahora - _fecha(m) > VENCE:
                    return None, "Ese código venció. Pedí la acción de nuevo."
                return accion, None
    return None, "No encontré ese código. Pedí la acción de nuevo."


def atender(texto, mensajes, yo, ahora, proveedor):
    """Devuelve (respuesta, accion o None). Solo reconoce comandos fijos; el resto es una pregunta."""
    t = texto.strip()
    if not t.startswith(PREFIJOS):
        if proveedor is not None:
            try:
                r = proveedor.responder(t[:1000], H.contexto())
            except Exception as e:
                r = None
                print(f"[agente] el modelo falló: {type(e).__name__}")
            if r:
                return r, None
        return SIN_MODELO, None
    partes = t[1:].split(maxsplit=1)
    cmd = H.norm(partes[0]) if partes else ""
    arg = partes[1].strip() if len(partes) > 1 else ""
    if cmd in ("ayuda", "help", "comandos"):
        return AYUDA, None
    if cmd == "estado":
        return H.estado(), None
    if cmd == "alertas":
        d = H.delito(arg)
        if arg and not d:
            return "No conozco ese delito. Probá con rapiña, hurto o lesiones.", None
        return H.alertas(d), None
    if cmd == "barrio":
        return (H.barrio(arg) if arg else "Decime cuál: `!barrio Cerro`"), None
    if cmd == "ranking":
        d = H.delito(arg) if arg else "RAPIÑA"
        return (H.ranking(d) if d else "No conozco ese delito. Probá con rapiña, hurto o lesiones."), None
    if cmd == "apagar":
        return ("⛔ Apago las corridas automáticas de 3S [acción:apagar · inmediata]. "
                "Para volver a prenderlas: `!encender`."), "apagar"
    if cmd in ACCIONES_CON_CONFIRMACION:
        codigo = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))
        que = {"correr": "correr 3S ahora", "encender": "volver a prender las corridas automáticas"}[cmd]
        return (f"¿Confirmás **{que}**? Escribí `!confirmar {codigo}` antes de las {_hora(ahora + VENCE)}. "
                f"[acción:{cmd} · código:{codigo}]"), None
    if cmd == "confirmar":
        if not arg:
            return "Falta el código: `!confirmar ABCD`", None
        accion, error = _confirmar(arg.split()[0], mensajes, yo, ahora)
        if error:
            return error, None
        hecho = {"correr": "▶️ Listo, la corrida arranca en un minuto. Te aviso en #avisos cuando termine.",
                 "encender": "✅ Corridas automáticas prendidas de nuevo."}[accion]
        return f"{hecho} [hecho:{arg.split()[0].upper()}]", accion
    return f"No conozco `!{cmd}`. Escribí `!ayuda`.", None


def ciclo(cliente, usuarios, proveedor=None, ahora=None):
    """Una vuelta: atiende los mensajes pendientes. Devuelve las acciones a ejecutar."""
    ahora = ahora or datetime.now(timezone.utc)
    yo = cliente.yo()
    mensajes = cliente.mensajes()
    acciones = []
    for m in pendientes(mensajes, yo, ahora):
        if m["author"].get("bot") or m["author"]["id"] not in usuarios:
            continue                          # solo las dos cuentas autorizadas
        texto = m.get("content", "")
        if not texto.strip():
            continue
        respuesta, accion = atender(texto, mensajes, yo, ahora, proveedor)
        cliente.responder(respuesta, referencia=m["id"])
        # lo que el bot acaba de decir cuenta para las próximas confirmaciones de esta misma vuelta
        mensajes.insert(0, {"author": {"id": yo, "bot": True}, "content": respuesta,
                            "timestamp": ahora.isoformat()})
        if accion and accion not in acciones:
            acciones.append(accion)
        print(f"[agente] atendido {texto.split()[0][:20]!r} → {accion or 'respuesta'}")
    return acciones


def main():
    import tomllib
    import guardas
    from .discord import Discord
    from .proveedor import cargar

    token, canal = os.environ.get("DISCORD_TOKEN"), os.environ.get("DISCORD_CANAL_AGENTE")
    usuarios = {u.strip() for u in os.environ.get("DISCORD_USUARIOS", "").split(",") if u.strip()}
    if not (token and canal and usuarios):
        print("[agente] faltan DISCORD_TOKEN, DISCORD_CANAL_AGENTE o DISCORD_USUARIOS: no hay nada que hacer")
        return 0
    try:
        guardas.verificar()
        cfg = tomllib.loads((H.RAIZ / "config.toml").read_text(encoding="utf-8"))
        proveedor = cargar(cfg)
        acciones = ciclo(Discord(token, canal), usuarios, proveedor)
    except guardas.Detener as e:
        print(f"[agente] detenido por las guardas: {e}")
        return 1
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a") as f:
            for a in ("correr", "apagar", "encender"):
                f.write(f"{a}={'true' if a in acciones else 'false'}\n")
    print(f"[agente] acciones: {acciones or 'ninguna'}")
    return 0
