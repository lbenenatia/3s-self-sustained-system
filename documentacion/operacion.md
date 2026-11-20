# Operación

## Workflows (`.github/workflows/`)
| Workflow | Cuándo | Qué hace |
|---|---|---|
| **3S semanal** | Lunes y jueves 03:17 (Uruguay) y a mano con "Run workflow" | Corrida completa, pruebas posteriores y commit del registro y la bitácora |
| **3S agente** | Cada ~10 minutos | Lee #agente en Discord, contesta y, si se lo piden, corre, apaga o prende 3S |
| **3S latido** | Todos los días 10:43 | Avisa en #avisos si hace más de 10 días que no hay una corrida exitosa |
| **3S pruebas** | En cada pull request | Verifica el sello, prepara los datos y corre las pruebas |

## Secretos (Settings → Secrets and variables → Actions)
| Nombre | Contenido |
|---|---|
| `DISCORD_WEBHOOK_AVISOS` | Webhook del canal #avisos (Editar canal → Integraciones → Webhooks) |
| `DISCORD_TOKEN` | Token del bot (discord.com/developers → la aplicación → Bot → Reset Token) |
| `DISCORD_CANAL_AGENTE` (o `DISCORD_CANAL_CHARLA`) | Id del canal #agente |
| `DISCORD_USUARIOS` | Ids de las cuentas autorizadas, separados por coma. El bot ignora a cualquier otra |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | El canal anterior. Mientras existan, los avisos salen también por Telegram; se pueden borrar cuando Discord ande bien |

Si un token o el webhook se filtran: en Discord, borrá el webhook y creá otro, o tocá Reset Token en el bot, y cargá el nuevo valor. **Nunca** pongas un token en el código, en un commit o en un issue.

## Hablar con el agente (canal #agente)
| Comando | Qué hace |
|---|---|
| `!ayuda` | Lista de comandos |
| `!estado` | Última corrida, datos, campeones, última predicción y alertas |
| `!alertas` / `!alertas rapiña` | Alertas del último trimestre, de la más fuerte a la más débil |
| `!barrio Cerro` | Cómo viene un barrio: último trimestre, cambio, puesto en la ciudad y sus alertas. Entiende nombres aproximados y abreviaturas |
| `!ranking hurto` | Los 10 barrios con más denuncias del último trimestre |
| `!correr` | Corre 3S ahora. Pide `!confirmar CÓDIGO` (vence en 20 minutos) |
| `!apagar` | Apaga las corridas automáticas (desactiva el workflow "3S semanal"). Inmediato, sin confirmación |
| `!encender` | Las vuelve a prender. Pide confirmación |

El bot se despierta cada ~10 minutos, así que la respuesta puede tardar un rato. Para apagar también el agente: Actions → 3S agente → "Disable workflow".

## Dónde mirar
- `registro_predicciones/ultimo_informe.md`: el informe más reciente.
- `registro_predicciones/trimestral/`: predicciones registradas a ciegas (`.csv`) y cuándo y con qué datos se hicieron (`.json`).
- `registro_predicciones/calificaciones.csv`: cómo le fue a cada predicción frente a la realidad. Aparece después de la primera calificación.
- `registro_alertas/<trimestre>.csv`: alertas de desvío de cada trimestre (pico, suba o baja; observado contra esperado). Se escribe una sola vez.
- `registro_alertas/validacion.json`: cómo les fue a las alertas en la historia.
- `state/corridas/`: la bitácora completa de cada corrida.
- `state/registro.json`: el campeón vigente y el historial de promociones.

## Qué hacer cuando…
| Aviso o síntoma | Qué significa | Qué hacer |
|---|---|---|
| ⛔ **detenido: reglas cambiaron sin aprobación** | Alguien modificó `guardas.py` o la sección `[seguridad]` sin volver a sellar | Revisar el cambio. Si es correcto, `python run.py --sellar` y commit de `state/sello.json`. Si no, revertirlo |
| ⛔ **detenido: interruptor de apagado** | Existe `state/STOP` | `python run.py --encender` (localmente) |
| • **descarga fallida** | Una fuente no respondió | Nada, si es puntual: 3S siguió con la copia anterior. Si se repite varias semanas, la URL pudo cambiar: actualizar `config.toml` |
| • **contrato adaptado** | Una fuente cambió un nombre de columna conocido y 3S se adaptó | Nada; queda registrado |
| • **contrato incumplido** | Una fuente cambió de una forma desconocida | Ver las columnas nuevas en el aviso, agregar el sinónimo en `contratos.py` y abrir un PR |
| ⛔ **dominio no permitido** | Una URL apunta fuera de la lista blanca | Si el organismo se mudó de dominio, agregarlo a `dominios_permitidos` y volver a sellar |
| ⚠️ **latido** | Más de 10 días sin una corrida exitosa | Pestaña Actions: ver si el workflow está pausado (GitHub pausa los programados tras 60 días sin actividad) o si falla |
| 🚨 **alertas de desvío** | Llegó un trimestre nuevo y hay barrios que se desviaron | Leer el mensaje y `registro_alertas/<trimestre>.csv`. Una alerta indica un cambio a investigar, no una causa |
| • **alertas_error** | Falló el cálculo de alertas | La corrida siguió igual. Ver el detalle en la bitácora y abrir un PR con el arreglo |
| ❌ **el agente falló** | Una vuelta del agente no pudo leer o escribir en Discord | Si se repite: revisar que los secretos de Discord estén bien y que el bot siga en el servidor con permiso de ver y escribir en #agente |
| ❌ **error** | Falla inesperada | Abrir la corrida en Actions, ver el paso rojo y su registro |

## Correrlo localmente
```bash
pip install -r requirements.txt
python run.py               # ciclo completo
python run.py trimestral    # un solo escenario
python run.py --solo-datos  # solo descargar y preparar
python run.py --apagar      # interruptor de apagado (python run.py --encender para reactivar)
```
Los datos se guardan en `data/`, que nunca se sube al repositorio.
