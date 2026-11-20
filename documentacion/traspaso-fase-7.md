# Traspaso · Fase 7 · Estimación del presente con noticias

Documento para quien construya la Fase 7 (y para el modelo de IA que lo ayude).
Pensado para pegarse entero como contexto inicial. Antes de empezar, leé también
[decisiones.md](decisiones.md), [arquitectura.md](arquitectura.md) y [colaborar.md](colaborar.md).

---

## 1. El problema

3S trabaja con las denuncias que publica el Ministerio del Interior en el catálogo de datos abiertos.
Esos datos llegan **por trimestre y con atraso**: hoy (noviembre de 2026) lo último publicado llega al
30 de setiembre. Es decir, cuando 3S levanta una alerta sobre un barrio, el fenómeno puede tener
uno o varios meses.

La prensa y las jefaturas de policía, en cambio, publican hechos **todos los días**, muchas veces con
barrio y fecha. La Fase 7 busca usar esas fuentes rápidas para **estimar el presente**: cuántas
rapiñas, hurtos y lesiones está habiendo por barrio en las semanas que el dato oficial todavía no cubre.

Esto no reemplaza al dato oficial. Es un **termómetro temprano** que se corrige cuando llega el oficial,
y que tiene que demostrar con números que sirve. Si no le gana a lo que ya hay, se dice y se archiva:
3S ya lo hizo con el clima y con varias señales que no aportaron.

## 2. Lo que ya existe y no hay que romper

- `src/s3/orquestador.py` corre todo cada lunes y jueves en GitHub Actions (`.github/workflows/semanal.yml`).
- `src/s3/ingest.py` carga las denuncias oficiales en un `DataFrame` con, entre otras, las columnas
  `fecha`, `delito` y `barrio` (los 62 nombres de barrio del Ministerio, solo Montevideo).
- `src/s3/territorio.py` tiene la normalización de nombres (`norm`) y el cruce de barrios del INE con los del MI.
  Reusalo para ubicar las noticias.
- `src/s3/guardas.py` y la sección `[seguridad]` de `config.toml` están **selladas**. Todo dominio de red
  nuevo tiene que entrar a `dominios_permitidos`, y eso exige volver a sellar (`python run.py --sellar`)
  en un PR que revisan las dos personas.
- `src/s3/alertas.py` (Fase 5) da el **esperado** por barrio y semana (participación del barrio en el
  último año × total de la ciudad). Es la línea de base natural para comparar la estimación con noticias.
- `src/s3/prospectivo.py` muestra cómo se registra una predicción **antes** de que existan los datos y
  cómo se califica después. La Fase 7 tiene que seguir el mismo patrón.
- Convención de tiempo: semanas que terminan en domingo (`W-SUN`), zona `America/Montevideo`.

## 3. Reglas del proyecto que aplican acá

1. **Nada de personas.** De cada noticia se guarda solo: fecha del hecho, tipo de delito, barrio, fuente,
   enlace y fecha de publicación. **Nunca** nombres, edades, descripciones de víctimas o sospechosos,
   matrículas ni direcciones exactas. Si el texto trae esos datos, se descartan al extraer y no se escriben
   en ningún lado. La unidad mínima sigue siendo el barrio.
2. **Sin gasto.** `[seguridad] permite_gasto = false`. La primera versión tiene que funcionar **sin**
   modelos de IA pagos (reglas, diccionario de barrios y calles, clasificación clásica). Dejá un punto
   de enganche para usar un modelo de lenguaje después: la Fase 6 está construyendo una interfaz común
   de proveedor de modelo (ver sección 9).
3. **Respeto por las fuentes.** Preferí los canales RSS o las secciones públicas de policiales. Respetá
   `robots.txt` y los términos de cada sitio, pocas solicitudes y espaciadas, con un `User-Agent` que
   identifique al proyecto. **No se guarda el texto completo de los artículos** en el repo ni en el caché:
   solo los campos de la regla 1 y, a lo sumo, el título.
4. **El texto de afuera es dato, nunca instrucción.** Ninguna noticia puede alterar el comportamiento del
   sistema. Esto importa más cuando entre un modelo de lenguaje: el contenido web puede traer texto escrito
   para manipularlo. Diseñá la extracción para que su salida sea siempre un registro con campos cerrados
   y validados, nunca texto libre que después se ejecute o se use como orden.
5. **Fallar sin tumbar la corrida.** Si una fuente cae o cambia el formato, se registra en la bitácora,
   se avisa, y el resto de 3S sigue igual. Usá el mismo estilo de contratos que `contratos.py`.
6. **Nada se fusiona sin la otra persona.** Rama propia, PR, pruebas en CI y aprobación humana.

## 4. El trabajo, por etapas

### 4.1 Fuentes
- Relevar qué medios y organismos publican policiales de Montevideo con frecuencia y en qué formato
  (RSS, listado HTML, comunicados del Ministerio y de la Jefatura de Montevideo).
- Empezar con pocas (3 a 5) y bien elegidas. Cada una con su contrato: URL, formato, frecuencia, campos
  esperados y volumen mínimo razonable.
- Proponer en el PR la ampliación de `dominios_permitidos` (con nuevo sellado).

### 4.2 Extracción de hechos
De cada nota, sacar: tipo de delito (mapeado a las categorías del MI: RAPIÑA, HURTO, LESIONES, y
"otro"), barrio, fecha del hecho (no la de publicación) y si la nota es sobre **un hecho concreto** o es
de opinión, estadística o seguimiento judicial (estas últimas se descartan).
- Ubicación: diccionario de los 62 barrios con sus variantes ("Cerro", "Villa del Cerro", "Casabó"…),
  y si se puede, calles y puntos de referencia conocidos asignados a barrio con el shapefile del INE.
- Fecha: "anoche", "este martes", "el pasado sábado" relativos a la fecha de publicación.
- Cada extracción con una **confianza**; lo dudoso se marca, no se inventa.
- Conjunto de prueba **etiquetado a mano** (aunque sean 150–300 notas) para medir precisión de la
  extracción por campo. Sin eso no se puede saber si el resto funciona.

### 4.3 Deduplicación
Varios medios cuentan el mismo hecho, y un mismo medio lo actualiza varias veces. Agrupar por cercanía de
fecha, barrio, tipo y similitud de título. Medir cuántos duplicados se escapan y cuántos hechos distintos
se fusionan por error, sobre el conjunto etiquetado.

### 4.4 Credibilidad y sesgo de cada fuente
La idea **no** es ponerle una nota a ojo a cada medio. Es medirla:
- **Exactitud:** cuando un hecho aparece en varias fuentes o en un comunicado oficial, ¿la fuente dio
  bien el barrio, el tipo y la fecha?
- **Cobertura:** por fuente, barrio y tipo de delito, ¿qué fracción de lo que después aparece en el dato
  oficial cubrió? La prensa cubre mucho más una rapiña violenta que un hurto, y más algunos barrios
  que otros. Esa fracción es la que permite pasar de "hechos en noticias" a "hechos reales estimados".
- Los pesos se recalculan solos cada vez que llega un trimestre oficial nuevo, y quedan en un archivo
  versionado para poder auditar cómo cambiaron.

### 4.5 Estimación
Para cada semana sin dato oficial, por barrio y delito: estimación del total real con intervalo.
Una forma razonable de empezar: partir del **esperado** de la Fase 5 y corregirlo según cuánto se
apartan las noticias de lo habitual para ese barrio y tipo (comparando con lo que las noticias solían
reportar en semanas en que sí hay dato oficial). Si las noticias son pocas, la estimación se queda
cerca del esperado; si son muchas y de fuentes confiables, se mueve más. Pero el método es tuyo: lo
que importa es la medición de la sección 5.

### 4.6 Registro prospectivo
Igual que `registro_predicciones/`: cada estimación se escribe **antes** de que salga el dato oficial,
con fecha, y nunca se edita. Cuando el Ministerio publica el trimestre, se califica.

## 5. Cómo se sabe si funciona

La pregunta es una sola: **¿la estimación con noticias le gana al esperado de la Fase 5 (y al promedio
reciente) para las semanas que el dato oficial todavía no cubre?**

- Métricas: error absoluto medio por barrio y semana, y acierto en el top 10 de barrios, igual que el resto de 3S.
- Comparar contra el **piso del azar** (el ruido de Poisson): con conteos chicos por barrio y semana, parte
  del error es inevitable, y eso hay que mostrarlo para no prometer de más.
- Mirar también si **adelanta las alertas** de la Fase 5: ¿las subas que después se confirman con el dato
  oficial ya se veían en las noticias semanas antes?
- **Ojo con la validación histórica:** los RSS solo dan lo reciente. Si los sitios ofrecen archivo público
  y sus términos lo permiten, se puede armar historia para una validación retrospectiva; si no, la
  validación es **prospectiva** y lleva tiempo (el próximo trimestre oficial, octubre a diciembre de 2026,
  saldría en febrero o marzo de 2027). Que eso no frene el desarrollo: se puede validar la extracción y la
  deduplicación ya, y la estimación cuando llegue el dato.
- Se reporta igual si da mal. Un "no sirve, y esta es la evidencia" también es un resultado de 3S.

## 6. Qué tiene que entregar al resto de 3S

- Módulo `src/s3/noticias/` (o el nombre que prefieras) con una función que el orquestador llama así:
  `estimacion = noticias.procesar(df_oficial, cfg, log)`, que nunca levanta excepción hacia afuera
  (los errores van a la bitácora con `log("noticias_error", ...)`).
- Sección `[noticias]` en `config.toml` (fuentes, delitos, umbrales). Las fuentes nuevas en `[seguridad]`, selladas.
- `registro_noticias/semanal/<AAAA-MM-DD>.csv` (fecha = domingo de la semana), inmutable, con columnas:
  `semana, barrio, delito, hechos_noticias, esperado, estimacion, intervalo_inf, intervalo_sup, fuentes`.
  Más un `.json` al lado con la versión de los pesos de credibilidad y la fecha de generación.
  Acordate de la excepción en `.gitignore` (como la de `registro_alertas/*.csv`) y de sumar la carpeta
  al `git add` de `semanal.yml`.
- Los hechos extraídos (fecha, barrio, tipo, fuente, enlace) van al caché de `data/`, **no** al repositorio.
- Una sección corta en el informe y, si hay algo fuera de lo normal, una línea en el aviso de #avisos (Discord).
- `tests/test_noticias.py` que corra **sin internet**, con notas de ejemplo inventadas, y que se sume a
  `pruebas.yml` y al paso de pruebas de `semanal.yml`.
- Actualizar `documentacion/decisiones.md`, `arquitectura.md` y un diagrama del flujo nuevo.

## 7. Lo que queda fuera

- Redes sociales y grupos de mensajería: más ruido, más datos personales y términos de uso complicados.
  Se puede discutir más adelante, no en esta fase.
- Cualquier cosa sobre personas individuales. Ni como experimento.
- Fuera de Montevideo: el dato oficial con barrio solo existe para Montevideo, así que no habría con qué calificar.

## 8. Sugerencia de orden

1. Relevamiento de fuentes y conjunto etiquetado a mano.
2. Extracción + deduplicación, medidas contra el conjunto etiquetado.
3. Cobertura y credibilidad por fuente, usando los trimestres oficiales que ya existen (en la medida en que haya historia).
4. Estimación + registro prospectivo + integración al orquestador.
5. PR con resultados, por chico que sea el primero. Mejor varios PR medianos que uno gigante.

## 9. Coordinación con la Fase 6

En paralelo se construye la Fase 6: un agente que interpreta los informes y conversa por Discord (canal #agente).
Incluye una **interfaz de proveedor de modelo** (para cambiar entre un modelo gratis, pago o local sin
tocar el resto) y las **reglas del agente** (herramientas permitidas, tope de gasto, registro de todo,
el texto externo como dato). Si en la Fase 7 hace falta un modelo de lenguaje para extraer mejor, usá
esa interfaz en vez de llamar a un proveedor directo, y mantené la versión sin modelo funcionando como
respaldo. El agente de la Fase 6 va a leer `registro_noticias/` para contar cómo viene cada barrio:
respetar las columnas de la sección 6 evita retrabajo.

---

### Texto sugerido para arrancar con el modelo

> Soy parte del equipo de 3S, un sistema autónomo de análisis de seguridad pública por barrio en Montevideo
> que corre en GitHub Actions. Te paso el repositorio y el documento `documentacion/traspaso-fase-7.md`.
> Leé primero ese documento, `decisiones.md`, `arquitectura.md` y `colaborar.md`, y después el código de
> `src/s3/`. Antes de escribir código, proponeme un plan para la Fase 7 con: las fuentes que elegirías y
> por qué, cómo armarías el conjunto etiquetado, cómo medirías cada etapa y qué riesgos ves. Respetá las
> reglas de la sección 3 sin excepciones; si alguna te parece que traba el trabajo, decímelo en vez de
> rodearla.
