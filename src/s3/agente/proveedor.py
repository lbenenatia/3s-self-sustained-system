"""Proveedor de modelo de lenguaje: el "cerebro" enchufable del agente.

Hoy 3S funciona SIN modelo (proveedor = "ninguno"): el agente entiende comandos fijos y los avisos
salen con el texto de siempre. Cuando se elija un modelo (gratis, pago o local), se agrega una clase
acá con los mismos dos métodos y se cambia [agente] proveedor en config.toml. Nada más cambia.

Regla de gasto: un proveedor con costo no carga mientras la sección sellada [seguridad] tenga
permite_gasto = false. Habilitarlo exige que un humano cambie esa sección, vuelva a sellar y
fije un tope mensual en [agente] tope_usd_mes.
"""
import guardas


class SinModelo:
    """No entiende texto libre: el agente usa solo comandos fijos."""
    nombre = "ninguno"
    con_costo = False

    def responder(self, pregunta: str, contexto: dict):
        """Contesta una pregunta en lenguaje natural usando SOLO el contexto dado. None si no puede."""
        return None

    def redactar(self, contexto: dict):
        """Reescribe en lenguaje humano el resumen de una corrida. None si no puede."""
        return None


PROVEEDORES = {"ninguno": SinModelo}


def cargar(cfg):
    ag = cfg.get("agente", {})
    nombre = ag.get("proveedor", "ninguno")
    if nombre not in PROVEEDORES:
        raise guardas.Detener(f"proveedor de modelo desconocido: {nombre}")
    clase = PROVEEDORES[nombre]
    if clase.con_costo:
        if not cfg.get("seguridad", {}).get("permite_gasto", False):
            raise guardas.Detener(f"el proveedor '{nombre}' tiene costo y las reglas selladas no permiten gastar")
        if not ag.get("tope_usd_mes"):
            raise guardas.Detener(f"el proveedor '{nombre}' tiene costo y no hay tope_usd_mes en [agente]")
    return clase()
