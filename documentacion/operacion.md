# Operación

## Workflows (`.github/workflows/`)
| Workflow | Cuándo | Qué hace |
|---|---|---|
| **3S semanal** | Lunes y jueves 03:17 (Uruguay) y a mano con "Run workflow" | Corrida completa, pruebas posteriores y commit del registro y la bitácora |
| **3S comandos** | Cuando cambia `src/s3/agente/comandos.py` en main, o a mano | Registra los comandos con barra en el servidor de Discord |
| **3S latido** | Todos los días 10:43 | Avisa en #avisos si hace más de 10 días que no hay una corrida exitosa |
| **3S pruebas** | En cada pull request | Verifica el sello, prepara los datos y corre las pruebas |

## Secretos (Settings → Secrets and variables → Actions)
| Nombre | Contenido |
|---|---|
| `DISCORD_WEBHOOK_AVISOS` | Webhook del canal #avisos (Editar canal → Integraciones → Webhooks) |
| `DISCORD_TOKEN` | Token del bot (discord.com/developers → la aplicación → Bot → Reset Token). Solo para registrar los comandos |
| `DISCORD_APP_ID` | Id de la aplicación (portal de Discord → General Information → Application ID) |
| `DISCORD_SERVIDOR` | Id del servidor 3S (clic derecho en el servidor → Copiar ID) |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | El canal anterior. Mientras existan, los avisos salen también por Telegram; se pueden borrar cuando Discord ande bien |

Si un token o el webhook se filtran: en Discord, borrá el webhook y creá otro, o tocá Reset Token en el bot, y cargá el nuevo valor. **Nunca** pongas un token en el código, en un commit o en un issue.

## El agente en Vercel
Los comandos con barra llegan, firmados por Discord, a la función `api/discord.py` desplegada en Vercel. Vercel la vuelve a desplegar sola con cada cambio en `main` (incluidos los commits de las corridas), así que siempre lee los datos al día. Variables de entorno en Vercel (Settings → Environment Variables, solo *Production*):

| Nombre | Contenido |
|---|---|
| `DISCORD_PUBLIC_KEY` | Clave pública de la aplicación (portal de Discord → General Information → Public Key) |
| `DISCORD_USUARIOS` | Ids de las cuentas autorizadas, separados por coma. A cualquier otra le contesta que no está autorizada |
| `GITHUB_TOKEN_ACCIONES` | Token fino de GitHub: solo este repositorio, permiso **Actions: Read and write**. Vence: renovarlo antes de la fecha que se le puso |

En el portal de Discord, **Interactions Endpoint URL** = `https://<proyecto>.vercel.app/api/discord`.

## Hablar con el agente (canal #agente)
| Comando | Qué hace |
|---|---|
| `/ayuda` | Lista de comandos |
| `/estado` | Última corrida, datos, campeones, última predicción y alertas |
| `/alertas` (delito opcional) | Alertas del último trimestre, de la más fuerte a la más débil |
| `/barrio` | Cómo viene un barrio: último trimestre, cambio, puesto en la ciudad y sus alertas. Sugiere los nombres mientras escribís |
| `/ranking` (delito opcional) | Los 10 barrios con más denuncias del último trimestre |
| `/preguntar` | Preguntas en lenguaje natural (cuando haya un modelo de lenguaje) |
| `/correr` | Corre 3S ahora. Pide tocar **Confirmar** (vence en 10 minutos; el botón desaparece al usarlo) |
| `/apagar` | Apaga las corridas automáticas (desactiva el workflow "3S semanal"). Inmediato, sin confirmación |
| `/encender` | Las vuelve a prender. Pide confirmación |

Responde en uno o dos segundos. Para desconectar el agente del todo: borrar la Interactions Endpoint URL en el portal de Discord, o pausar el proyecto en Vercel.

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
| Discord dice **"La aplicación no respondió"** | La función de Vercel no contestó en 3 segundos o no está desplegada | Vercel → el proyecto → Deployments / Logs. Revisar las variables de entorno y que la URL del portal termine en `/api/discord` |
| ❌ **GitHub respondió 401/403** al correr o apagar | El token de GitHub venció o le falta el permiso | Crear un token fino nuevo (Actions: Read and write) y reemplazar `GITHUB_TOKEN_ACCIONES` en Vercel |
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
