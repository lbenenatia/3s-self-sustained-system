# Decisiones de diseño y hallazgos

## La idea
3S (*Self Sustained System*) busca ser un sistema **autónomo**: que funcione solo durante años, se corrija, se actualice y se proteja, y que haga un trabajo que a las personas les llevaría demasiado tiempo. Su primer módulo analiza la **seguridad pública en Uruguay** con datos abiertos.

## Cómo se eligió el objetivo
Se evaluaron varias opciones: exploración matemática, alertas ambientales (cianobacterias, inundaciones, sequía), tránsito, educación terciaria y seguridad. Se eligió **seguridad**, enfocada en **lugares y momentos, no en personas**, por tres razones:
- Es la principal preocupación de la población.
- El Ministerio del Interior publica microdatos abiertos de buena calidad: 2,5 millones de denuncias desde 2013.
- Un sistema que detecta dónde y cuándo se concentra el riesgo sirve para prevenir (iluminación, espacio público, programas sociales) sin señalar a nadie.

## Lo que 3S no hace, y por qué
**3S no predice delitos de personas individuales ni señala sospechosos.** No es una limitación técnica pendiente, es una decisión de diseño:
- **Falacia de la tasa base.** En Uruguay hay unos 350 homicidios por año en 3,4 millones de habitantes. Un sistema con un 99% de acierto marcaría por error a unas 34.000 personas: 99 de cada 100 señalados serían inocentes.
- **No se puede verificar.** Si se interviene sobre alguien señalado, nunca se sabe si iba a hacer algo, así que el sistema no puede aprender de sus errores.
- **Los datos policiales están sesgados de origen.** Registran dónde se denuncia y dónde se patrulla, no dónde ocurre el delito. Entrenar más con esos datos produce un sistema más seguro de sí mismo, no uno más justo.

## Reglas de diseño (selladas en el código)
1. **No se replica** fuera de su entorno.
2. **Nunca se resiste a ser apagado:** el interruptor lo controlan las personas.
3. **Automodificación acotada:** no puede tocar sus propias reglas de seguridad ni su interruptor de apagado.
4. **No gasta dinero** por su cuenta.
5. **No usa ni produce datos de personas,** solo conteos agregados por barrio y período.
6. **Red solo por `https`** y hacia una lista blanca de dominios oficiales.

Las reglas tienen una huella sellada (`state/sello.json`). Si alguien las cambia sin volver a sellar, 3S se detiene.

## Lo que se aprendió, fase por fase

### Fase 1 · MVP
Primer modelo de rapiñas por barrio de Montevideo, con autoevaluación honesta contra predicciones simples. **Resultado: empata con "el promedio reciente".** No fue un fracaso: el sistema no se hizo pasar por algo que no era.

### Fase 2 · Núcleo autónomo
- Orquestador, guardas selladas y autocorrección por campeón y retador: un modelo nuevo solo reemplaza al vigente si el intervalo de confianza del 90% de su mejora es mayor que cero.
- Se probaron señales de calendario uruguayo (incluidos Carnaval y Turismo), horas de oscuridad, otros delitos y escalada reciente.
- **Hallazgo clave: el techo de predicción.** Semana a semana, cada barrio tiene unas 4 rapiñas, así que casi todo es azar y ni un modelo perfecto mejoraría más de un 13%. A escala trimestral sí queda margen, hasta un 60%.

### Fase 3 · Fuentes que se actualizan solas
- Se sumaron 1,36 millones de reclamos ciudadanos a la Intendencia (alumbrado, limpieza, áreas verdes, espacios públicos, calles), ubicados en su barrio con un cruce espacial. Se ubicaron 1.364.966 de 1.364.977.
- Se sumó el clima diario.
- **Resultado: ninguna fuente pública mejora la predicción trimestral de forma segura.** Lo comprobaron 31 trimestres evaluados desde 2019.
- **Conclusión:** el margen que queda depende de información que no es pública: operativos, intervenciones, ubicación exacta de los hechos. 3S demuestra con números qué datos le faltan.
- **Lección de mantenimiento:** el portal de reclamos dice que entrega coordenadas UTM, pero el archivo real trae latitud y longitud. De ahí nacieron los contratos de datos con sinónimos.

### Fase 4 · Producción
- Corre gratis en GitHub Actions: semanal, más un latido diario y pruebas en cada pull request.
- Avisos por Telegram.
- **Registro prospectivo:** las predicciones se publican antes de que existan los datos reales y se califican cuando llegan. Es la forma de construir evidencia que cualquiera pueda verificar.

## Resultados actuales (datos al 30/09/2026)
| Escenario | Mejor método | Error medio | Piso del azar | Margen máximo |
|---|---|---|---|---|
| Semanal, por barrio | Modelo + clima | 1,76 | 1,54 | 13% |
| Trimestral, por barrio | Promedio reciente | 16,5 | 6,6 | 60% |

## Hacia dónde va
- **Alertas de desvío:** avisar cuándo un barrio se aparta de lo esperable. Aprovecha justamente que el promedio predice bien: lo valioso es lo que se sale de él.
- **Evaluación de intervenciones:** medir si una política funcionó, comparando con barrios parecidos donde no se aplicó (control sintético, diferencias en diferencias).
- **Interior del país,** por seccionales.
- **Automejora acotada:** 3S propone mejoras como pull requests con pruebas. Nunca se fusionan solos.
