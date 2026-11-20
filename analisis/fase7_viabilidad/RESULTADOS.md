# Fase 7 · prueba de viabilidad (20/11/2026)

**Resultado: con estas fuentes, las noticias no agregan nada al esperado de la Fase 5.** Ni por barrio ni
para la ciudad entera, en ninguno de los tres delitos. Y no es solo porque sean pocas: la cantidad de
notas no sigue a la cantidad de delitos.

Es un análisis local, fuera de 3S: no lo llama el orquestador, no corre en GitHub Actions y no tocó la
lista sellada de dominios.

## Qué se hizo

1. `01_bajar_indices.py` bajó los índices mensuales que Subrayado y El Observador publican en su
   `robots.txt` (enlace y fecha de cada nota): 119 meses de Subrayado (2017–2026) y 70 de El Observador
   (completo desde 2021). Fueron 191 solicitudes, una cada 2 segundos. No se bajó el texto de ninguna nota.
2. `extraccion.py` saca del título (que viene en el enlace) el tipo de delito y el barrio, con reglas y un
   diccionario de los 62 barrios. Los títulos no se guardan: solo fecha, medio, señal de delito y barrio.
3. `02_analizar.py` simula la situación real en 31 trimestres (2019 a setiembre de 2026): con el dato
   oficial conocido hasta el cierre de un trimestre, estima cada semana del siguiente, con y sin noticias.
   Los modelos se ajustan solo con trimestres anteriores al evaluado.

## Cuánto cubre la prensa

| | Notas con palabras de delito | Hechos concretos | Con barrio de Montevideo |
|---|---|---|---|
| Subrayado (desde 2017) | 14.587 | 9.738 | 2.351 |
| El Observador (desde 2017, completo desde 2021) | 6.405 | 3.971 | 837 |

Subrayado en 2025, hechos con barrio respecto de las denuncias de Montevideo:

| Delito | Prensa | Denuncias | Cobertura |
|---|---|---|---|
| Rapiña (notas de robo o rapiña) | 103 | 12.554 | 0,8% |
| Hurto (las mismas notas) | 103 | 53.412 | 0,2% |
| Lesiones (notas de baleados, heridos, agresiones) | 208 | 4.609 | 4,5% |

Solo entre el 2% y el 4% de las combinaciones de barrio y semana tiene alguna nota. La cobertura además
cambia con los años (la de rapiña pasó de 0,1% en 2022 a 1,1% en 2026), lo que la hace difícil de calibrar.

## Qué aportan las noticias

Mejora del error medio al sumar las noticias, respecto de la misma estimación sin noticias. Positivo es
mejor; entre corchetes, el intervalo de confianza del 90% (bootstrap por trimestres). Solo Subrayado, 31 trimestres.

| Delito | Por barrio y semana | Total de la ciudad por semana |
|---|---|---|
| Rapiña | −0,4% [−2,4 a +1,5] | −1,9% [−12,2 a +7,3] |
| Hurto | +0,1% [−0,5 a +0,6] | +1,4% [−2,8 a +5,7] |
| Lesiones | −0,2% [−0,4 a +0,1] | −1,7% [−6,1 a +2,3] |

- Con los dos medios juntos (15 trimestres, desde 2022) da lo mismo: todas las mejoras entre −0,2% y +0,1%
  por barrio, con intervalos que incluyen el cero.
- **No adelantan las subas.** Entre los barrios que terminaron un trimestre 40% o más por encima de lo
  esperado en rapiñas (192 casos), el 13,5% tenía más noticias que lo habitual; en el resto, el 19,1%.
  La correlación trimestral entre noticias y desvío oficial es prácticamente cero (−0,01 a 0,03).

## Control: el método sí detecta señal cuando la hay

Se reemplazaron las noticias por una muestra al azar de las denuncias reales, con cobertura fija. Mejora
de la estimación de rapiñas:

| Cobertura al azar | Por barrio y semana | Total de la ciudad |
|---|---|---|
| 0,5% | +0,9% [+0,3 a +1,5] | +5,5% [+1,5 a +10,1] |
| 2% | +4,3% [+1,7 a +7,6] | +18% [+4 a +29] |
| 5% | +7,6% [+4,5 a +11,5] | +36% [+22 a +46] |
| 20% | +14% [+11 a +18] | +52% [+41 a +61] |

Una muestra al azar del 0,5% ya alcanzaría para mejorar el total de la ciudad. La prensa real cubre algo
parecido en rapiñas y nueve veces más en lesiones, y no mejora nada. Entonces el problema no es la
cantidad: lo que publica un medio depende de criterios editoriales (gravedad, día flojo de noticias, tema
del momento), no del volumen de delitos.

## Límites de esta prueba

- **Extracción solo del título.** Con el cuerpo de la nota se ubicarían más hechos, pero el control indica
  que el cuello de botella no es la cantidad.
- **Precisión sin medir formalmente.** Revisé 60 notas a ojo: el barrio estaba bien en unas 9 de cada 10.
  Los errores eran "Hospital del Cerro", notas que nombran varios barrios y heridos de tránsito; los dos
  últimos tipos se corrigieron antes de la corrida final. No hay conjunto etiquetado todavía.
- **La fecha es la de última modificación de la nota**, no la del hecho (96 notas caían fuera del mes de su índice).
- **Un medio principal.** El País y Montevideo Portal no publican archivo, así que no se pudieron evaluar hacia atrás.
- **"Lesiones" en la prensa son sobre todo baleados**, que coinciden solo en parte con la categoría del Ministerio.
- No se probaron comunicados de la Jefatura: no se encontró un canal público con archivo.

## Dato lateral

El esperado de la Fase 5, proyectado un trimestre hacia adelante, le gana al promedio reciente del barrio:
error de 2,42 contra 2,47 en rapiñas, 4,75 contra 4,86 en hurtos y 0,93 contra 0,95 en lesiones. Sirve
como línea de base para cualquier estimación futura del presente.

Los números completos están en `resultados.json`.

## ¿Hay una fuente oficial más frecuente? (relevamiento del 20/11/2026)

- **Catálogo de datos abiertos:** el único conjunto del Ministerio del Interior sobre delitos es el que 3S
  ya usa, con frecuencia declarada de 90 días. El último trimestre (hasta el 30/09) se publicó el 20/10:
  unas 3 semanas de atraso. No hay versión mensual ni semanal.
- **Noticias del Ministerio (gub.uy):** no tienen RSS y son comunicados institucionales de todo el país
  (operativos, condenas, actividades). Tienen el mismo problema que la prensa: se elige qué contar.
- **Jefatura de Montevideo:** no se encontró un canal público con partes diarios.

Con lo que hoy es público no hay cómo estimar el presente. La vía que queda es pedirle al Ministerio
conteos agregados más frecuentes (por barrio y mes o semana, sin datos de personas), por ejemplo con un
pedido de acceso a la información pública. Eso lo tienen que decidir y hacer las personas del equipo.
