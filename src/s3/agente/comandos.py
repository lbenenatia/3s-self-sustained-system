"""Comandos con barra (/) de 3S en Discord, y cómo registrarlos.

Se registran en el servidor de 3S (no globalmente), así que solo existen ahí y se actualizan al instante.
El workflow "3S comandos" los vuelve a registrar solo cuando este archivo cambia en main.

  python run.py --registrar-comandos   (necesita DISCORD_TOKEN, DISCORD_APP_ID y DISCORD_SERVIDOR)
"""
import os

DELITOS = [{"name": "Rapiña", "value": "RAPIÑA"}, {"name": "Hurto", "value": "HURTO"},
           {"name": "Lesiones", "value": "LESIONES"}]
_STRING = 3


def _delito(requerido=False):
    return {"type": _STRING, "name": "delito", "description": "Rapiña, hurto o lesiones",
            "required": requerido, "choices": DELITOS}


COMANDOS = [
    {"name": "ayuda", "description": "Qué puede hacer 3S"},
    {"name": "estado", "description": "Última corrida, datos, campeones y alertas"},
    {"name": "alertas", "description": "Alertas de desvío del último trimestre", "options": [_delito()]},
    {"name": "barrio", "description": "Cómo viene un barrio de Montevideo", "options": [
        {"type": _STRING, "name": "nombre", "description": "Empezá a escribir y elegí", "required": True,
         "autocomplete": True}]},
    {"name": "ranking", "description": "Los 10 barrios con más denuncias del último trimestre", "options": [_delito()]},
    {"name": "preguntar", "description": "Preguntale a 3S en tus palabras", "options": [
        {"type": _STRING, "name": "texto", "description": "Tu pregunta", "required": True, "max_length": 500}]},
    {"name": "correr", "description": "Correr 3S ahora (pide confirmación)"},
    {"name": "apagar", "description": "Apagar las corridas automáticas (inmediato)"},
    {"name": "encender", "description": "Volver a prender las corridas automáticas (pide confirmación)"},
]


def registrar():
    from .discord import Discord
    token, app, servidor = (os.environ.get(k) for k in ("DISCORD_TOKEN", "DISCORD_APP_ID", "DISCORD_SERVIDOR"))
    if not (token and app and servidor):
        print("[comandos] faltan DISCORD_TOKEN, DISCORD_APP_ID o DISCORD_SERVIDOR")
        return 1
    hechos = Discord(token, canal=None)._pedir("PUT", f"/applications/{app}/guilds/{servidor}/commands", COMANDOS)
    print(f"[comandos] registrados: {', '.join('/' + c['name'] for c in hechos)}")
    return 0
