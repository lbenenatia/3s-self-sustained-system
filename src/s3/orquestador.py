"""Orquestador de 3S: corre el ciclo completo de forma autónoma y deja registro de todo.

  guardas → ingesta → control de calidad → señales → backtest → promoción → predicción → informe
"""
import json
import os
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import avisos
import contratos
import descargas
import guardas
import ingest as ing
import prospectivo
import registro
import territorio as terr
from features import panel, CONJUNTOS
from ingest import load_denuncias, check_quality
from modelo import backtest, metricas, bootstrap_mejora, nuevo_modelo, piso_azar

RAIZ = Path(__file__).resolve().parents[2]


def log(bitacora, etapa, **datos):
    bitacora.append({"etapa": etapa, "hora": datetime.now(timezone.utc).isoformat(timespec="seconds"), **datos})
    print(f"[3S] {etapa}: {json.dumps(datos, ensure_ascii=False, default=str)[:300]}")


def ingesta(cfg, bitacora):
    pq = RAIZ / cfg["datos"]["parquet"]
    csv = (RAIZ / cfg["datos"]["csv_denuncias"]).resolve()
    respaldo = (RAIZ / cfg["datos"]["csv_respaldo"]).resolve() if cfg["datos"].get("csv_respaldo") else None
    if respaldo and respaldo.is_file() and (not csv.exists() or respaldo.stat().st_mtime > csv.stat().st_mtime):
        csv = respaldo
    if csv.exists() and (not pq.exists() or csv.stat().st_mtime > pq.stat().st_mtime):
        try:
            df = load_denuncias(csv)
        except contratos.Incumplido as e:
            log(bitacora, "contrato_incumplido", fuente="denuncias_mi", detalle=str(e)[:300])
            if not pq.exists():
                raise guardas.Detener(f"la fuente de denuncias cambió y no hay copia anterior: {e}")
            df = None
    else:
        df = None
    if df is not None:
        if ing.ADAPTACIONES:
            log(bitacora, "contrato_adaptado", fuente="denuncias_mi", cambios=ing.ADAPTACIONES)
        rep = check_quality(df)
        if rep["problemas"]:
            raise guardas.Detener(f"control de calidad falló: {rep['problemas']}")
        pq.parent.mkdir(exist_ok=True)
        df.to_parquet(pq, index=False)
        log(bitacora, "ingesta", nuevo=True, filas=rep["filas"], hasta=rep["fecha_max"])
    if df is None:
        if not pq.exists():
            raise guardas.Detener("no hay datos de denuncias: la descarga falló y no hay copia anterior")
        df = pd.read_parquet(pq)
        log(bitacora, "ingesta", nuevo=False, filas=len(df), hasta=str(df["FECHA"].max().date()))
    atraso = (pd.Timestamp.today() - df["FECHA"].max()).days
    if atraso > cfg["datos"]["max_dias_desactualizado"]:
        raise guardas.Detener(f"datos con {atraso} días de atraso: ¿cambió la fuente?")
    return df


def senales_territorio(df, cfg, bitacora):
    zsur, zine = RAIZ / "data/fuentes/reclamos_sur.zip", RAIZ / "data/fuentes/mapas_vectoriales_2011.zip"
    if not (zsur.exists() and zine.exists()):
        log(bitacora, "territorio", disponible=False, motivo="faltan reclamos SUR o barrios INE")
        return None
    try:
        barrios_mi = sorted(df.loc[df["DEPTO"] == "MONTEVIDEO", "BARRIO_MONTEVIDEO"].dropna().astype(str).unique())
        t = terr.construir(zsur, zine, barrios_mi, cfg["territorio"]["areas"],
                           log=lambda e, **k: log(bitacora, e, **k))
        log(bitacora, "territorio", disponible=True, filas=len(t))
        return t
    except Exception as e:  # una fuente nueva rota no debe tumbar el sistema
        log(bitacora, "territorio_error", tipo=type(e).__name__, detalle=str(e)[:300])
        return None


def correr_escenario(df, nombre, esc, cfg, bitacora, territorio=None):
    t0 = time.time()
    pan, conj, bases = panel(df, esc["freq"], territorio=territorio)
    guardas.verificar_senales(list(conj.values())[-1])
    res = backtest(pan, conj, bases, esc["backtest_desde"], esc["reentrenar_cada"])
    metr = metricas(res)
    reg = registro.cargar(nombre, cfg["promocion"]["campeon_inicial"])
    campeon = reg[nombre]["campeon"]
    intervalos = {m: bootstrap_mejora(res, m, campeon, cfg["promocion"]["bootstrap_n"])
                  for m in metr if m != campeon}
    nuevo, motivo = registro.decidir(metr, intervalos, campeon, cfg["promocion"]["max_perdida_top10_pts"])
    registro.anotar(reg, nombre, nuevo, motivo, metr)
    registro.guardar(reg)
    piso = piso_azar(res, nuevo)
    margen = 1 - piso / metr[nuevo]["error_medio"]
    log(bitacora, f"diagnostico_{nombre}", piso_azar=round(piso, 3), margen_mejorable=round(margen, 3))
    log(bitacora, f"promocion_{nombre}", campeon_anterior=campeon, campeon=nuevo, motivo=motivo)

    # predicción del próximo período con el campeón
    ext, conj_e, bases_e = panel(df, esc["freq"], extender=True, territorio=territorio)
    futuro = ext[ext["t"] == ext["t"].max()]
    if nuevo in conj_e:
        mdl = nuevo_modelo(conj_e[nuevo]).fit(ext[ext["t"] < ext["t"].max()][conj_e[nuevo]],
                                              ext[ext["t"] < ext["t"].max()]["y"])
        pred = mdl.predict(futuro[conj_e[nuevo]])
    else:
        pred = futuro[bases_e[nuevo.replace("base_", "")]].values
    prediccion = (pd.DataFrame({"barrio": futuro["barrio"].values, "esperado": pred,
                                "promedio_reciente": futuro[bases_e["corta"]].values})
                  .sort_values("esperado", ascending=False))
    registrado = None
    if nombre in cfg.get("prospectivo", {}).get("escenarios", []):
        registrado = prospectivo.registrar(nombre, ext["t"].max(), prediccion, df["FECHA"].max(), nuevo)
        if registrado:
            log(bitacora, "prediccion_registrada", escenario=nombre, archivo=str(registrado.relative_to(RAIZ)))
    out = RAIZ / "outputs"
    out.mkdir(exist_ok=True)
    res.to_csv(out / f"backtest_{nombre}.csv", index=False)
    prediccion.to_csv(out / f"prediccion_{nombre}.csv", index=False)
    log(bitacora, f"escenario_{nombre}", segundos=round(time.time() - t0), periodo_predicho=str(ext["t"].max().date()))
    return {"metricas": metr, "intervalos": intervalos, "campeon": nuevo, "motivo": motivo,
            "periodo_predicho": str(ext["t"].max().date()), "prediccion": prediccion.head(15).to_dict("records"),
            "periodos_evaluados": int(res["t"].nunique()),
            "piso_azar": round(piso, 3), "margen_mejorable": round(margen, 3),
            "campeon_anterior": campeon, "registrado": str(registrado.relative_to(RAIZ)) if registrado else None}


def informe(resultados, bitacora):
    nombres = {"base_corta": "Promedio reciente", "base_estacional": "Igual que hace un año",
               "base": "Modelo: historia", "calendario": "Modelo: + calendario y oscuridad",
               "otros": "Modelo: + otros delitos", "escalada": "Modelo: + escalada",
               "territorio": "Modelo: + reclamos del barrio", "clima": "Modelo: + clima"}
    lineas = [f"# Informe 3S · {datetime.now().strftime('%d/%m/%Y %H:%M')}", ""]
    for esc, r in resultados.items():
        lineas += [f"## Escenario {esc}", "", f"**Campeón:** {nombres.get(r['campeon'], r['campeon'])}. {r['motivo']}.", "",
                   "| Método | Error medio | Acierto top 10 | Mejora vs campeón anterior (IC 90%) |", "|---|---|---|---|"]
        for m, v in r["metricas"].items():
            iv = r["intervalos"].get(m)
            ivs = f"{iv[0]:+.1%} a {iv[1]:+.1%}" if iv else "—"
            lineas.append(f"| {nombres.get(m, m)} | {v['error_medio']:.2f} | {v['acierto_top10']:.0%} | {ivs} |")
        lineas += ["", f"**Techo de predicción:** aunque se conociera la tasa real de cada barrio, el azar dejaría un error de "
                   f"{r['piso_azar']:.2f} (el campeón tiene {r['metricas'][r['campeon']]['error_medio']:.2f}). Ni un modelo perfecto podría reducir el error más de un {r['margen_mejorable']:.0%} a esta escala.", ""]
        lineas += ["", f"**Barrios con más rapiñas esperadas ({r['periodo_predicho']}):** " +
                   ", ".join(f"{p['barrio'].title()} ({p['esperado']:.1f})" for p in r["prediccion"][:10]), ""]
    hist = prospectivo.resumen()
    if hist:
        lineas += ["## Registro prospectivo", "",
                   f"{hist['calificadas']} predicciones calificadas. Error medio de 3S: {hist['error_3s']} · "
                   f"del promedio reciente: {hist['error_promedio']} · 3S fue mejor {hist['veces_3s_mejor']} veces.", ""]
    texto = "\n".join(lineas)
    (RAIZ / "outputs").mkdir(exist_ok=True)
    (RAIZ / "outputs" / "informe.md").write_text(texto, encoding="utf-8")
    prospectivo.CARPETA.mkdir(exist_ok=True)
    (prospectivo.CARPETA / "ultimo_informe.md").write_text(texto + "\n", encoding="utf-8")
    log(bitacora, "informe", archivo="outputs/informe.md")


def resumen_aviso(estado, bitacora, resultados):
    icono = {"ok": "✅", "detenido": "⛔", "error": "❌"}[estado]
    lineas = [f"{icono} 3S · corrida {estado}"]
    for b in bitacora:
        e = b["etapa"]
        if e in ("detenido", "error", "territorio_error", "contrato_incumplido"):
            lineas.append(f"• {e}: {b.get('motivo') or b.get('detalle')}"[:300])
        elif e == "descarga_fallida":
            copia = "se usa la copia anterior" if b.get("usa_copia_anterior") else "SIN copia anterior"
            lineas.append(f"• descarga fallida: {b['fuente']} ({copia}): {b.get('detalle', '')}"[:300])
        elif e == "contrato_adaptado":
            lineas.append(f"• {b['fuente']} cambió columnas y 3S se adaptó: {b['cambios']}")
        elif e == "prediccion_registrada":
            lineas.append(f"• predicción registrada: {b['archivo']}")
        elif e == "prediccion_calificada":
            lineas.append(f"• calificada {b['periodo']}: error 3S {b['error_3s']} vs promedio {b['error_promedio']}")
    for esc, r in resultados.items():
        if r["campeon"] != r["campeon_anterior"]:
            lineas.append(f"• nuevo campeón {esc}: {r['campeon']} ({r['motivo']})")
    return "\n".join(lineas)


def preparar_datos():
    """Guardas + descargas + ingesta, sin modelos. Lo usan las pruebas automáticas de cada cambio."""
    bitacora = []
    cfg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8"))
    guardas.verificar()
    try:
        if os.environ.get("S3_SIN_DESCARGAS") == "1":
            # pruebas de cada cambio: usan la copia que dejó la corrida semanal, sin bajar 400 MB por PR
            log(bitacora, "descargas_omitidas", motivo="S3_SIN_DESCARGAS=1")
        elif cfg["seguridad"].get("permite_red"):
            descargas.actualizar(cfg, lambda e, **k: log(bitacora, e, **k))
        ingesta(cfg, bitacora)
    except guardas.Detener as e:
        log(bitacora, "detenido", motivo=str(e))
        return False
    return True


def correr(escenarios=None):
    bitacora = []
    cfg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8"))
    estado = "ok"
    resultados = {}
    try:
        guardas.verificar()
        log(bitacora, "guardas", ok=True)
        if cfg["seguridad"].get("permite_red"):
            descargas.actualizar(cfg, lambda e, **k: log(bitacora, e, **k))
        df = ingesta(cfg, bitacora)
        nuevas = prospectivo.calificar(df, {n: e["freq"] for n, e in cfg["escenarios"].items()})
        for c in nuevas:
            log(bitacora, "prediccion_calificada", **c)
        territorio = senales_territorio(df, cfg, bitacora)
        for nombre, esc in cfg["escenarios"].items():
            if escenarios and nombre not in escenarios:
                continue
            resultados[nombre] = correr_escenario(df, nombre, esc, cfg, bitacora, territorio)
        informe(resultados, bitacora)
    except guardas.Detener as e:
        estado = "detenido"
        log(bitacora, "detenido", motivo=str(e))
    except Exception as e:  # cualquier falla queda registrada; el campeón anterior sigue vigente
        estado = "error"
        log(bitacora, "error", tipo=type(e).__name__, detalle=str(e))
    if estado == "ok":
        (RAIZ / "state" / "ultima_ok.json").write_text(
            json.dumps({"fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
    avisos.enviar(resumen_aviso(estado, bitacora, resultados))
    runs = RAIZ / "state" / "corridas"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps({"estado": estado, "bitacora": bitacora, "resultados": resultados}, ensure_ascii=False, indent=1, default=str))
    return estado, resultados
