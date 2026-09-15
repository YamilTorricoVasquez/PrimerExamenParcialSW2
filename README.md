# Pipeline de Análisis Predictivo de Video de Fútbol

Sistema base (100% open source) para procesar un video de fútbol y generar
métricas tácticas colectivas e individuales: detección y seguimiento de
jugadores/balón, identificación de equipos por color de camiseta, mapas de
calor, distancia recorrida, velocidad estimada y alertas de fatiga —
presentado en un dashboard web (Flask) pensado para que lo entienda un
entrenador sin conocimientos técnicos.

**El modelo de detección (YOLOv8n) ya está incluido en `models/yolov8n.pt`**
— no se descarga ni se entrena nada en tiempo de uso. El usuario final solo
sube su video en el dashboard y obtiene el análisis, sin tocar código.

> Proyecto académico — pipeline de referencia para adaptar y extender,
> no un producto comercial terminado. Pensado para video de **cámara fija
> elevada** (mejor precisión). Con video broadcast o de celular funcionará,
> pero con menor cobertura de jugadores (ver limitaciones en el protocolo
> de tesis).

## 1. Instalación (una sola vez, la hace quien despliega el sistema)

Requiere Python 3.9+.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

No hace falta descargar ningún modelo: `models/yolov8n.pt` ya viene en el
proyecto.

## 2. Estructura del proyecto

```
code_project/
├── Procfile                    # Comando de arranque para Render (gunicorn)
├── render.yaml                 # Configuración de despliegue (Blueprint) para Render
├── runtime.txt                 # Versión de Python fijada para el entorno de Render
├── run_app.bat                 # Doble clic para levantar todo LOCALMENTE (Windows)
├── run_app.sh                  # Equivalente para Mac/Linux (uso local)
├── requirements.txt
├── models/
│   └── yolov8n.pt              # Modelo de detección YA INCLUIDO (6.5 MB)
├── templates/
│   ├── index.html              # Página de subida de video / configuración de equipos
│   └── result.html             # Página de resultados (progreso + análisis)
├── static/
│   ├── style.css                # Estilos del dashboard
│   ├── app.js                   # JS de la página de inicio (sugerencia de marcador)
│   └── result.js                # JS de resultados (polling de progreso, renderizado)
├── src/
│   ├── detect_track.py         # Detección (YOLOv8) + tracking + color de camiseta
│   ├── homography.py           # Calibración de campo: píxeles -> coordenadas reales
│   ├── analytics.py            # Métricas: distancia, velocidad, heatmaps, fatiga
│   ├── teams.py                 # Identificación de equipos por color de camiseta
│   ├── jersey_ocr.py            # OCR experimental de número de camiseta
│   ├── scoreboard_ocr.py        # OCR experimental sobre el marcador de TV
│   └── reports.py               # Resumen del partido + ficha PDF por jugador
└── app.py                      # Backend Flask (rutas, API JSON, procesamiento)
```

## 3. Arquitectura del backend (Flask)

A diferencia de un dashboard de una sola pieza, aquí el video se procesa
**en un hilo en segundo plano** para que la página no se quede bloqueada
mientras se analiza:

1. El usuario sube el video vía `POST /analyze` (formulario HTML normal).
2. Flask guarda el video, crea un `job_id` único, lanza un hilo con
   `process_video_job(...)` y redirige a `/result/<job_id>`.
3. Esa página de resultados consulta `GET /api/status/<job_id>` cada
   1.5 segundos (JavaScript) para actualizar la barra de progreso.
4. Cuando el análisis termina, la página pide los datos a
   `GET /api/data/<job_id>` y los muestra: resumen, equipos, jugadores.
5. Los mapas de calor se sirven como imágenes PNG generadas al vuelo
   (`/image/team_heatmap/...`, `/image/player_heatmap/...`), y la ficha de
   cada jugador se genera bajo demanda en `/download/pdf/<job_id>/<track_id>`.

**Limitación importante a documentar en la tesis**: el estado de cada
análisis (`JOBS`) se guarda en memoria del proceso Python, no en una base
de datos. Esto significa que el servidor **debe correr con un solo
worker/proceso** (ver `Procfile`: `--workers 1`). Si se reinicia el
servidor, los análisis en curso o recientes se pierden. Para un uso con
múltiples usuarios simultáneos a mayor escala, el siguiente paso natural
sería mover `JOBS` a Redis o una base de datos — queda fuera del alcance
de este proyecto académico, pero es una buena mención en la sección de
trabajo futuro de la tesis.

## 4. Funciones del dashboard

- **Identificación automática de equipos por color de camiseta** (sin
  entrenar ningún modelo): k-means sobre el color de camiseta detectado en
  cada jugador (`src/teams.py`); el entrenador confirma/invierte la
  asignación con un botón si hace falta.
- **Nombres reales de jugadores**: sube una plantilla (número + nombre) y
  asigna cada nombre al jugador detectado con un clic en la pestaña
  "Asignar nombres". Opcionalmente, activa la lectura experimental de
  dorsal (`src/jersey_ocr.py`) para que el sistema sugiera automáticamente
  la asignación cuando logre leer el número — esto falla con frecuencia
  (el número está en la espalda, es pequeño y el jugador se mueve), así
  que trátalo como ayuda, no como certeza.
- **Sugerencia experimental desde el marcador de TV** (`src/scoreboard_ocr.py`):
  si el video es de transmisión y tiene un marcador visible, se puede
  intentar leer el texto con OCR como sugerencia de nombre de equipo.
- **Comparación cabeza a cabeza entre equipos**: distancia total y
  promedio por jugador, y conteo de jugadores por nivel de actividad,
  presentado como barras enfrentadas por color de equipo.
- **Resumen automático del partido en lenguaje simple** (`src/reports.py`):
  un párrafo generado a partir de los números reales (sin IA generativa,
  sin depender de ninguna API externa ni costo adicional).
- **Clasificación de actividad física en palabras simples** ("Alto",
  "Medio", "Bajo") en vez de solo mostrar km/h o metros.
- **Zona de campo predominante**: en qué tercio del campo pasó más tiempo
  cada jugador (informativo — no es una posición táctica real, ya que el
  sistema no sabe hacia qué lado ataca cada equipo).
- **Alerta de fatiga**: compara la primera mitad del video contra la
  segunda y avisa si un jugador bajó notablemente su actividad.
- **Ficha individual descargable en PDF** por jugador, con el nombre real
  si fue asignado.

## 5. Identidad visual

El dashboard sigue una paleta "cancha nocturna" en vez del estilo genérico
de tarjetas blancas con sombra: fondo verde oscuro tipo campo bajo luces de
estadio, tipografía condensada (Oswald) para títulos y números grandes
inspirada en marcadores deportivos, y un único color de acento (ámbar)
reservado para las acciones principales. Los colores de cada equipo
(calculados automáticamente) llevan el peso visual de la comparación entre
equipos en vez de competir con una paleta genérica.

## 6. Uso — flujo para el usuario final (entrenador)

**La forma más simple: doble clic en `run_app.bat`** (Windows) o ejecutar
`./run_app.sh` (Mac/Linux) desde la carpeta del proyecto. Este script crea
el entorno virtual la primera vez, instala dependencias si faltan, y
levanta el servidor.

Si prefieres hacerlo manualmente:

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Luego abre **http://localhost:5000** en el navegador. Ahí el entrenador:

1. **Sube su video**, escribe el nombre de los dos equipos, y opcionalmente
   la plantilla de jugadores (número + nombre).
2. Presiona **"Analizar video"** — se le redirige a una página con barra de
   progreso mientras el sistema corre detección, tracking y métricas.
3. Al terminar, ve: resumen del partido, comparación entre equipos, mapas
   de calor, y puede asignar nombres reales a cada jugador detectado y
   descargar su ficha en PDF.

### Uso opcional por línea de comandos (para desarrollo/depuración)

```bash
python src/detect_track.py --source /ruta/a/tu_video.mp4 --output data/tracking.csv
```

## 7. Calibración de campo (recomendado para métricas reales en metros)

Por defecto el sistema usa 4 puntos de ejemplo en `src/homography.py` para
convertir píxeles a metros. Para que la distancia y velocidad reflejen la
realidad de TU cámara y TU campo, edita esos 4 puntos siguiendo las
instrucciones comentadas en ese archivo. Sin calibrar, el dashboard sigue
funcionando pero las métricas de distancia/velocidad no son reales — los
mapas de calor (posición relativa) siguen siendo útiles igualmente.

## 8. Despliegue en Render (nube)

El proyecto ya incluye lo necesario: `Procfile`, `render.yaml`, `runtime.txt`.

### Pasos

1. **Sube el proyecto a un repositorio de GitHub** (incluye `models/yolov8n.pt`
   — pesa 6.5 MB, sin problema para Git/GitHub).
2. En Render: **New +** → **Web Service**, conecta tu repositorio.
3. Render detecta automáticamente `render.yaml`. Si prefieres configurarlo
   a mano, usa estos valores:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`
   - **Environment**: Python 3
4. Despliega. La primera build tarda varios minutos (instala PyTorch, OpenCV, etc.).

**Por qué `--workers 1`**: el estado de cada análisis vive en memoria
(diccionario `JOBS` en `app.py`). Con más de un worker, cada proceso
tendría su propia copia y las consultas de estado fallarían al azar según
qué worker las atienda. `--threads 4` sí permite atender varias peticiones
HTTP a la vez dentro de ese único worker (necesario para que la barra de
progreso funcione mientras el análisis corre en su propio hilo).

### Nota sobre el OCR del marcador y Render

`easyocr` (usado por la función experimental de lectura del marcador) es
una dependencia pesada: aumenta el tiempo de build y descarga modelos de
reconocimiento la primera vez que se usa esa función específica (no al
arrancar el servidor). Si tu build falla por espacio o tarda demasiado,
puedes quitarla de `requirements.txt` — el resto del dashboard sigue
funcionando igual; solo desaparece esa opción experimental.

### Limitaciones reales a tener en cuenta (importante para tu tesis/demo)

- **Plan gratuito de Render probablemente no alcance**: ~512 MB de RAM no
  suele bastar para cargar YOLOv8 + procesar video, y el servicio "duerme"
  tras inactividad. Recomiendo al menos el plan **Starter**.
- **Videos largos = timeouts**: usa clips cortos (1-3 minutos) para la demo
  y/o sube "Procesar 1 de cada N fotogramas" al subir el video.
- **Almacenamiento efímero**: los videos subidos se borran del disco apenas
  termina el análisis; solo los resultados quedan en memoria hasta que el
  servidor se reinicie.
- **Un solo servidor a la vez** (ver nota de `--workers 1` arriba) — no
  pensado para múltiples analistas trabajando en paralelo sin modificar la
  arquitectura de almacenamiento de resultados.

## 9. Qué adaptar según tu caso

- **Puntos de homografía**: cambian si cambias de cancha o de ángulo de
  cámara — no son universales.
- **Umbrales de actividad física** (`classify_activity_level` en
  `src/analytics.py`): ajústalos según la categoría/edad real de tus
  jugadores.
- **Detección de eventos (pases, tiros)**: no incluido en esta versión base;
  buen siguiente paso para ampliar el alcance de la tesis.
- **Persistencia de resultados**: si necesitas guardar análisis entre
  reinicios del servidor o para varios usuarios a la vez, reemplaza el
  diccionario `JOBS` en memoria por una base de datos (ver limitación en
  la sección de Render).

## 10. Solución de problemas

**PowerShell dice que no reconoce `run_app.bat`**

Ejecuta con la ruta explícita: `.\run_app.bat` — PowerShell no busca
comandos en la carpeta actual por seguridad.

**La página no carga o da error de conexión**

- Verifica en la terminal que diga `Running on http://127.0.0.1:5000` (o
  el puerto que hayas configurado) sin errores debajo.
- Prueba `http://127.0.0.1:5000` en vez de `localhost:5000`.
- Si hay un traceback de Python real en la terminal, ese es el error a
  resolver — revisa el mensaje específico.

**El análisis tarda mucho**

Sube el valor de "Procesar 1 de cada N fotogramas" al subir el video — en
una computadora sin GPU esto reduce drásticamente el tiempo de procesamiento.

**Errores de conexión reiniciados (`ConnectionResetError` en Windows)**

Son avisos benignos del sistema operativo cuando una conexión (navegador,
antivirus, etc.) se cierra abruptamente contra el socket del servidor. No
significa que el servidor se haya caído — confirma que el dashboard
responde en el navegador antes de preocuparte por este mensaje.

## 11. Referencia técnica

- Detección: [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- Tracking: ByteTrack, integrado en Ultralytics (`model.track(...)`)
- Backend web: [Flask](https://flask.palletsprojects.com/) + [Gunicorn](https://gunicorn.org/) (producción)

Verifica siempre la documentación oficial de estas herramientas: las APIs
pueden cambiar de versión a versión.
