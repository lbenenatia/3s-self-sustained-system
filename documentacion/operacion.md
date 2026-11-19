# Operación

## Workflows (`.github/workflows/`)
| Workflow | Cuándo | Qué hace |
|---|---|---|
| **3S semanal** | Lunes y jueves 03:17 (Uruguay) y a mano con "Run workflow" | Corrida completa, pruebas posteriores y commit del registro y la bitácora |
| **3S latido** | Todos los días 10:43 | Avisa por Telegram si hace más de 10 días que no hay una corrida exitosa |
| **3S pruebas** | En cada pull request | Verifica el sello, prepara los datos y corre las pruebas |

## Secretos (Settings → Secrets and variables → Actions)
| Nombre | Contenido |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot (de @BotFather) |
| `TELEGRAM_CHAT_ID` | Id del chat o del grupo que recibe los avisos (un grupo tiene id negativo) |

Si un token se filtra, mandá `/revoke` a @BotFather y cargá el nuevo. **Nunca** pongas un token en el código, en un commit o en un issue.

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
