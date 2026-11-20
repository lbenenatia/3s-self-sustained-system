# 3S · Self Sustained System

**Un sistema autónomo y auditable que analiza datos abiertos de seguridad pública de Uruguay.**
Corre solo cada semana, se evalúa a sí mismo, solo cambia de modelo cuando la mejora está demostrada,
y registra sus predicciones **antes** de que se conozcan los resultados, para que cualquiera pueda verificarlas.

> Módulo actual: **rapiñas por barrio en Montevideo**, con datos abiertos del Ministerio del Interior,
> la Intendencia de Montevideo, el INE y Open-Meteo.

📚 **Documentación completa:** [documentacion/](documentacion/), con decisiones de diseño, arquitectura con diagramas, operación y cómo colaborar.

## Qué hace
1. **Descarga** las fuentes oficiales y las valida con contratos de datos. Si una fuente cambia un nombre de columna conocido, se adapta sola. Si no puede, avisa y sigue con la última copia buena.
2. **Construye señales por barrio:** historia de rapiñas, calendario uruguayo y horas de oscuridad, otros delitos, reclamos a la Intendencia (alumbrado, limpieza, áreas verdes…) y clima.
3. **Compite contra lo simple:** cada variante del modelo se evalúa contra "el promedio reciente" con un backtest de origen móvil. Solo reemplaza al campeón si el intervalo de confianza del 90% de su mejora es mayor que cero.
4. **Mide su propio techo:** calcula cuánto error dejaría el puro azar aunque se conociera la tasa real de cada barrio.
5. **Alerta desvíos por barrio:** cada trimestre señala picos, subas y bajas sostenidas de rapiñas, hurtos y lesiones respecto de lo habitual del barrio, con como máximo una falsa alarma esperada por trimestre. En 42 trimestres de historia, el 76% de las subas y el 88% de las bajas alertadas se mantuvieron el trimestre siguiente. Quedan en [`registro_alertas/`](registro_alertas/).
6. **Registra predicciones a ciegas** en [`registro_predicciones/`](registro_predicciones/) y las **califica** cuando el Ministerio publica los datos reales.

## Qué NO hace
- **No usa ni produce datos sobre personas.** Las señales son conteos agregados por barrio y período, y las guardas bloquean cualquier campo personal.
- **No predice delitos individuales ni señala sospechosos.** Ese enfoque es estadísticamente inviable por la falacia de la tasa base y éticamente inaceptable.
- **No gasta dinero ni modifica su propio código.** Un cambio de código solo entra a producción mediante un pull request aprobado por un humano.

## Reglas de seguridad (selladas)
Las reglas viven en `src/s3/guardas.py` y en la sección `[seguridad]` de `config.toml`. Su huella está sellada en `state/sello.json`, y si cambian sin que un humano vuelva a sellar, el sistema se detiene.
- **Interruptor de apagado:** `python run.py --apagar`.
- **Red solo por `https`** y hacia una lista blanca de dominios oficiales.
- **Sin datos personales, sin gasto y sin automodificación.**

## Resultados hasta ahora (datos al 30/09/2026)
| Escenario | Campeón | Error medio | Piso del azar | Margen máximo |
|---|---|---|---|---|
| Semanal, por barrio | Modelo + clima | 1,76 | 1,54 | 13% |
| Trimestral, por barrio | Promedio reciente | 16,5 | 6,6 | 60% |

**Hallazgo principal:** con datos públicos, "el promedio reciente" es casi imbatible para predecir rapiñas por barrio. El margen que queda a escala trimestral depende de información que no es pública: operativos, intervenciones y ubicación exacta de los hechos.

## Cómo correrlo
```bash
pip install -r requirements.txt
python run.py --sellar      # solo un humano, después de revisar las reglas
python run.py               # ciclo completo (descarga unos 430 MB)
```
En producción corre con GitHub Actions (`.github/workflows/semanal.yml`) los lunes y jueves a las 03:17 de Uruguay (si las fuentes no cambiaron, no vuelve a descargarlas). Hay además un latido diario y pruebas automáticas en cada pull request.

## Fuentes
- Ministerio del Interior: *Delitos denunciados en el Uruguay* (catalogodatos.gub.uy).
- Intendencia de Montevideo: *Reclamos registrados en el Sistema Único de Reclamos* (ckan.montevideo.gub.uy).
- INE: mapas vectoriales 2011.
- Open-Meteo: archivo histórico de clima.

Los datos no se guardan en este repositorio: se descargan de sus fuentes oficiales en cada corrida.

## Licencia
Código bajo licencia MIT. Los datos pertenecen a sus organismos de origen y se usan según sus licencias de datos abiertos.
