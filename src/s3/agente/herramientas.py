"""Herramientas del agente: SOLO lectura de archivos que 3S ya publica en el repositorio.

  state/ultima_ok.json, state/corridas/, state/registro.json   estado de las corridas y campeones
  state/resumen_barrios.json                                   conteos por barrio (los escribe cada corrida)
  registro_alertas/<trimestre>.csv                             alertas de la Fase 5
  registro_predicciones/                                       predicciones registradas por adelantado

Ninguna escribe, borra ni toca la red. Todas devuelven texto listo para mandar.
"""
import csv
import difflib
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
TIPO = {"pico": "🔺 Pico", "suba": "🔺 Suba sostenida", "baja": "🔻 Baja sostenida"}
SINONIMOS_DELITO = {"rapina": "RAPIÑA", "rapinas": "RAPIÑA", "hurto": "HURTO", "hurtos": "HURTO",
                    "lesion": "LESIONES", "lesiones": "LESIONES"}


def norm(txt) -> str:
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def _json(ruta):
    f = RAIZ / ruta
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _titulo(nombre):
    return nombre.title().replace("Pque.", "Parque").replace("Pta.", "Punta").replace("V. ", "Villa ")


def delito(texto):
    return SINONIMOS_DELITO.get(norm(texto)) if texto else None


# ------------------------------------------------------------------------------------------- estado
def estado() -> str:
    lineas = ["**Estado de 3S**"]
    ok = _json("state/ultima_ok.json")
    if ok:
        cuando = datetime.fromisoformat(ok["fecha"])
        dias = (datetime.now(timezone.utc) - cuando).days
        lineas.append(f"• Última corrida exitosa: {cuando:%d/%m/%Y} (hace {dias} días)")
    else:
        lineas.append("• Todavía no hubo una corrida exitosa registrada")
    corridas = sorted((RAIZ / "state" / "corridas").glob("*.json"))
    if corridas:
        ult = json.loads(corridas[-1].read_text(encoding="utf-8"))
        lineas.append(f"• Última corrida registrada: {corridas[-1].stem[:8]} → {ult.get('estado')}")
    res = _json("state/resumen_barrios.json")
    if res:
        lineas.append(f"• Datos oficiales hasta: {res['datos_hasta']} (último trimestre completo: {res['ultimo_trimestre']})")
    reg = _json("state/registro.json") or {}
    for esc, r in reg.items():
        lineas.append(f"• Campeón {esc}: {r.get('campeon')}")
    preds = sorted((RAIZ / "registro_predicciones").glob("*/*.csv"))
    if preds:
        lineas.append(f"• Última predicción registrada por adelantado: {preds[-1].parent.name} {preds[-1].stem}")
    q = _ultimo_trimestre_alertas()
    if q:
        lineas.append(f"• Alertas registradas: {q} ({len(_alertas(q))} en total)")
    return "\n".join(lineas)


# ------------------------------------------------------------------------------------------ alertas
def _ultimo_trimestre_alertas():
    archivos = sorted((RAIZ / "registro_alertas").glob("*Q*.csv"))
    return archivos[-1].stem if archivos else None


def _alertas(trimestre):
    f = RAIZ / "registro_alertas" / f"{trimestre}.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8") as h:
        filas = list(csv.DictReader(h))
    for a in filas:
        for c in ("observado", "esperado", "variacion_pct", "cusum", "umbral"):
            try:
                a[c] = float(a[c])
            except (TypeError, ValueError):
                a[c] = None
    return filas


def _fuerza(a):
    if a["tipo"] == "pico":
        return 50.0
    return (a["cusum"] or 0) / a["umbral"] if a.get("umbral") else 0.0


def _linea_alerta(a):
    var = f"{a['variacion_pct']:+.0f}%" if a.get("variacion_pct") is not None else ""
    desde = datetime.fromisoformat(a["desde"][:10]).strftime("%d/%m")
    cuando = f"semana del {desde}" if a["tipo"] == "pico" else f"desde el {desde}"
    return (f"{TIPO.get(a['tipo'], a['tipo'])} · {a['delito'].title()} · {_titulo(a['barrio'])}: {var} "
            f"({a['observado']:.0f} vs {a['esperado']:.0f} esperadas) {cuando}")


def alertas(delito_filtro=None, maximo=10) -> str:
    q = _ultimo_trimestre_alertas()
    if not q:
        return "Todavía no hay alertas registradas."
    lista = [a for a in _alertas(q) if not delito_filtro or a["delito"] == delito_filtro]
    titulo = f"**Alertas de {q}**" + (f" · {delito_filtro.title()}" if delito_filtro else "")
    if not lista:
        return f"{titulo}\nNingún barrio se desvió de lo esperable."
    lista.sort(key=_fuerza, reverse=True)
    lineas = [f"{titulo} ({len(lista)} en total)"] + [f"• {_linea_alerta(a)}" for a in lista[:maximo]]
    if len(lista) > maximo:
        lineas.append(f"… y {len(lista) - maximo} más en registro_alertas/{q}.csv")
    return "\n".join(lineas)


# ------------------------------------------------------------------------------------------ barrios
ABREVIATURAS = {"pque": "parque", "pta": "punta", "v": "villa", "p": "perez"}


def _clave(txt):
    return " ".join(ABREVIATURAS.get(p, p) for p in norm(txt).split())


def buscar_barrio(texto):
    """Devuelve (nombre_oficial, candidatos). Si no hay uno claro, nombre_oficial es None."""
    res = _json("state/resumen_barrios.json")
    if not res or not texto.strip():
        return None, []
    nombres = list(res["barrios"])
    q = _clave(texto)
    partes = {n: [_clave(p) for p in n.split(",")] + [_clave(n)] for n in nombres}
    completo = [n for n in nombres if _clave(n) == q]
    if completo:
        return completo[0], []
    exactos = [n for n in nombres if q in partes[n]]
    if len(exactos) == 1:
        return exactos[0], []
    if exactos:
        return None, exactos
    contiene = [n for n in nombres if q in _clave(n)]
    if len(contiene) == 1:
        return contiene[0], []
    if contiene:
        return None, contiene[:6]
    claves = {c: n for n in nombres for c in partes[n]}
    parecidos = difflib.get_close_matches(q, list(claves), n=4, cutoff=0.75)
    candidatos = list(dict.fromkeys(claves[c] for c in parecidos))
    if len(candidatos) == 1:
        return candidatos[0], []
    return None, candidatos


def _pct(a, b):
    return f"{(a - b) / b * 100:+.0f}%" if b else "s/d"


def barrio(texto) -> str:
    res = _json("state/resumen_barrios.json")
    if not res:
        return "Todavía no tengo el resumen por barrio: se genera en la próxima corrida de 3S."
    nombre, candidatos = buscar_barrio(texto)
    if not nombre:
        if candidatos:
            return "¿Cuál de estos?\n" + "\n".join(f"• {_titulo(c)}" for c in candidatos)
        return f"No encontré un barrio parecido a «{texto[:40]}». Probá con otro nombre."
    datos, qs = res["barrios"][nombre], res["trimestres"]
    lineas = [f"**{_titulo(nombre)}** · último trimestre completo {qs[-1]} (datos oficiales hasta {res['datos_hasta']})"]
    for d in res["delitos"]:
        serie = datos[d]
        ranking = sorted(res["barrios"], key=lambda b: res["barrios"][b][d][-1], reverse=True)
        puesto = ranking.index(nombre) + 1
        lineas.append(f"• {d.title()}: {serie[-1]} denuncias · vs trimestre anterior {_pct(serie[-1], serie[-2])} · "
                      f"vs un año antes {_pct(serie[-1], serie[0])} · puesto {puesto} de {len(ranking)}")
    q = _ultimo_trimestre_alertas()
    propias = [a for a in _alertas(q) if a["barrio"] == nombre] if q else []
    if propias:
        lineas.append(f"Alertas de {q}:")
        lineas += [f"• {_linea_alerta(a)}" for a in sorted(propias, key=_fuerza, reverse=True)]
    elif q:
        lineas.append(f"Sin alertas en {q}: se mantuvo dentro de lo esperable para el barrio.")
    lineas.append("_Son denuncias, no todos los delitos que ocurren._")
    return "\n".join(lineas)


def ranking(delito_elegido="RAPIÑA", n=10) -> str:
    res = _json("state/resumen_barrios.json")
    if not res:
        return "Todavía no tengo el resumen por barrio: se genera en la próxima corrida de 3S."
    if delito_elegido not in res["delitos"]:
        return f"Por ahora sigo {', '.join(d.title() for d in res['delitos'])}."
    orden = sorted(res["barrios"].items(), key=lambda kv: kv[1][delito_elegido][-1], reverse=True)[:n]
    total = res["ciudad"][delito_elegido][-1]
    lineas = [f"**{delito_elegido.title()} · {res['trimestres'][-1]}** · Montevideo: {total} denuncias"]
    for i, (b, v) in enumerate(orden, 1):
        lineas.append(f"{i}. {_titulo(b)}: {v[delito_elegido][-1]} ({_pct(v[delito_elegido][-1], v[delito_elegido][0])} vs un año antes)")
    return "\n".join(lineas)


def contexto() -> dict:
    """Todo lo que un modelo de lenguaje puede usar para contestar (solo datos ya publicados)."""
    q = _ultimo_trimestre_alertas()
    return {"estado": estado(), "resumen_barrios": _json("state/resumen_barrios.json"),
            "alertas": _alertas(q) if q else [], "trimestre_alertas": q}
