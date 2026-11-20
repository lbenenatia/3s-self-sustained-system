"""Fase 7 · prueba de viabilidad: extracción gruesa de delito y barrio a partir del título de una nota.

El título sale del propio enlace (los medios lo escriben ahí, sin tildes y separado por guiones).
Es una extracción con reglas y diccionario, sin modelo de lenguaje. Devuelve solo campos cerrados:
señales de delito y nombre de barrio del Ministerio. El título no se guarda en ningún lado.
"""
import re

VACIAS = {"de", "del", "en", "a", "y", "al"}

# alias (como aparece en un título) -> barrio del Ministerio del Interior
ALIAS = {
    "aguada": "AGUADA", "aires puros": "AIRES PUROS", "atahualpa": "ATAHUALPA", "barrio sur": "BARRIO SUR",
    "banados carrasco": "BAÑADOS DE CARRASCO", "belvedere": "BELVEDERE", "brazo oriental": "BRAZO ORIENTAL",
    "buceo": "BUCEO", "capurro": "CAPURRO, BELLA VISTA", "carrasco": "CARRASCO", "carrasco norte": "CARRASCO NORTE",
    "casabo": "CASABO, PAJAS BLANCAS", "pajas blancas": "CASABO, PAJAS BLANCAS", "santa catalina": "CASABO, PAJAS BLANCAS",
    "casavalle": "CASAVALLE", "marconi": "CASAVALLE", "borro": "CASAVALLE", "40 semanas": "CASAVALLE",
    "cuarenta semanas": "CASAVALLE", "perez castellanos": "CASTRO, P. CASTELLANOS",
    "centro montevideo": "CENTRO", "pleno centro": "CENTRO", "cerrito": "CERRITO", "cerrito la victoria": "CERRITO",
    "cerro": "CERRO", "cerro norte": "CERRO", "villa cerro": "CERRO", "ciudad vieja": "CIUDAD VIEJA",
    "colon": "COLON CENTRO Y NOROESTE", "abayuba": "COLON SURESTE, ABAYUBA", "conciliacion": "CONCILIACION",
    "cordon": "CORDON", "flor maronas": "FLOR DE MAROÑAS", "ituzaingo": "ITUZAINGO", "jacinto vera": "JACINTO VERA",
    "jardines hipodromo": "JARDINES DEL HIPODROMO", "la blanqueada": "LA BLANQUEADA", "la comercial": "LA COMERCIAL",
    "la figurita": "LA FIGURITA", "tomkinson": "LA PALOMA, TOMKINSON", "la teja": "LA TEJA",
    "barrio larranaga": "LARRAÑAGA", "las acacias": "LAS ACACIAS", "las canteras": "LAS CANTERAS",
    "cruz carrasco": "LAS CANTERAS", "lezica": "LEZICA, MELILLA", "malvin": "MALVIN", "malvin norte": "MALVIN NORTE",
    "barrio manga": "MANGA", "toledo chico": "MANGA, TOLEDO CHICO", "maronas": "MAROÑAS, PARQUE GUARANI",
    "parque guarani": "MAROÑAS, PARQUE GUARANI", "mercado modelo": "MERCADO MODELO, BOLIVAR",
    "nuevo paris": "NUEVO PARIS", "palermo": "PALERMO", "parque rodo": "PARQUE RODO",
    "paso la arena": "PASO DE LA ARENA", "paso las duranas": "PASO DE LAS DURANAS",
    "barrio penarol": "PEÑAROL, LAVALLEJA", "barrio lavalleja": "PEÑAROL, LAVALLEJA",
    "piedras blancas": "PIEDRAS BLANCAS", "pocitos": "POCITOS", "parque batlle": "PQUE. BATLLE, V. DOLORES",
    "villa dolores": "PQUE. BATLLE, V. DOLORES", "prado": "PRADO, NUEVA SAVONA",
    "punta rieles": "PTA. RIELES, BELLA ITALIA", "bella italia": "PTA. RIELES, BELLA ITALIA",
    "punta carretas": "PUNTA CARRETAS", "punta gorda": "PUNTA GORDA", "reducto": "REDUCTO", "sayago": "SAYAGO",
    "tres cruces": "TRES CRUCES", "tres ombues": "TRES OMBUES, VICTORIA", "pueblo victoria": "TRES OMBUES, VICTORIA",
    "la union": "UNION", "barrio union": "UNION", "villa espanola": "VILLA ESPAÑOLA",
    "villa garcia": "VILLA GARCIA, MANGA RURAL", "villa munoz": "VILLA MUÑOZ, RETIRO", "goes": "VILLA MUÑOZ, RETIRO",
}
_ALIAS_ORDEN = sorted(ALIAS, key=len, reverse=True)   # primero los más largos ("carrasco norte" antes que "carrasco")

# frases que contienen un alias pero no son el barrio
FALSOS = ["cerro largo", "cerro chato", "cerro colorado", "cerro pelado", "cerro san antonio", "cerro toro",
          "aeropuerto carrasco", "paso carrasco", "union europea", "teatro colon", "cristobal colon",
          "cordon cuneta", "cordon policial", "cordon sanitario", "cordon vereda", "hipodromo maronas",
          "hospital cerro", "arroyo carrasco", "rural prado", "expo prado", "palermo buenos aires", "carcel punta rieles", "punta rieles carcel"]

# otro departamento u otro país: la nota no se asigna a un barrio de Montevideo
FUERA = ["canelones", "maldonado", "punta este", "rocha", "salto", "paysandu", "rivera", "tacuarembo", "artigas",
         "durazno", "florida", "treinta tres", "cerro largo", "melo", "soriano", "colonia", "san jose", "rio negro",
         "fray bentos", "ciudad costa", "las piedras", "pando", "ciudad plata", "piriapolis", "san carlos", "chuy",
         "barros blancos", "paso carrasco", "el pinar", "solymar", "atlantida", "santa lucia", "delta tigre",
         "bella union", "juan lacaze", "parque plata", "salinas", "argentina", "argentino", "brasil", "buenos aires",
         "chile", "eeuu", "estados unidos", "espana", "mexico", "colombia", "ecuador", "paraguay", "peru",
         "venezuela", "israel", "rusia", "ucrania", "francia", "italia", "gaza"]

DEPORTE = {"futbol", "partido", "hincha", "hinchas", "clasico", "gol", "goles", "campeonato", "clausura", "apertura",
           "basquetbol", "basquet", "liga", "copa", "libertadores", "sudamericana", "tecnico", "dt", "jugador",
           "jugadores", "seleccion", "torneo", "club", "tabla", "carnaval", "murga"}
JUDICIAL = ("conden", "imput", "formaliz", "juicio", "sentenc", "procesa", "prision")

ROBO = {"robo", "robos", "robar", "robaron", "roban", "robado", "robada", "robados", "robadas", "robaba", "robaban",
        "robarle", "robarles", "robarlo", "robarla", "ladron", "ladrones"}
PREFIJOS = {
    "rap": ("rapin", "asalt", "copami", "arrebat"),
    "robo": ("rapin", "asalt", "copami", "arrebat", "hurt"),
    "viol": ("balead", "baleo", "balearon", "balazo", "disparo", "dispar", "tiroteo", "balacera", "herid", "apunal",
             "golpiza", "agredi", "agresion", "lesion"),
    "hom": ("asesin", "homicid", "mataron", "ultimaron"),
}
TRANSITO = ("choc", "choque", "accident", "atropell", "volc", "siniestr", "despist")
SENALES = ("rap", "robo", "viol", "hom")


def titulo(url):
    """Palabras del título según el enlace, sin el número final ni las palabras vacías."""
    tramo = url.rstrip("/").rsplit("/", 1)[-1].lower()
    tramo = re.sub(r"-n\d+$", "", tramo)
    return [p for p in re.split(r"[^a-z0-9]+", tramo) if p and p not in VACIAS]


def extraer(url):
    """Devuelve (señales de delito, barrio o None, es_hecho_concreto)."""
    pal = titulo(url)
    senales = {s for s, pre in PREFIJOS.items() if any(p.startswith(pre) for p in pal)}
    if ROBO & set(pal):
        senales.add("robo")
    if "tiros" in pal or "bala" in pal or "balas" in pal:
        senales.add("viol")
    if any(p.startswith(TRANSITO) for p in pal):
        senales.discard("viol")   # heridos de tránsito o de un accidente: no son lesiones denunciadas como delito
    if not senales:
        return senales, None, False
    texto = " " + " ".join(pal) + " "
    concreto = not (DEPORTE & set(pal)) and not any(p.startswith(JUDICIAL) for p in pal)
    fuera = any(f" {f} " in texto for f in FUERA)
    for f in FALSOS:
        texto = texto.replace(f" {f} ", " · ")
    barrio = None
    if not fuera:
        for a in _ALIAS_ORDEN:
            if f" {a} " in texto:
                barrio = ALIAS[a]
                break
    return senales, barrio, concreto and not fuera
