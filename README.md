# 💻 IoT Backend

## 📝 Descripción

Este backend en **Flask** permite gestionar dispositivos IoT que envían su estado y configuración mediante **MQTT** o que son **reclamados vía HTTP** (por ejemplo, desde QR generado en IoT Alchemy).  
Soporta tanto **dispositivos físicos** como **dispositivos simulados** y **actualización en tiempo real** con **SSE (Server-Sent Events)** para la vista de dispositivos en la app móvil.

> Para un entorno doméstico (≈20 dispositivos, 5 usuarios) el SSE es más que suficiente: latencia muy baja en LAN y complejidad mínima.

> Para instalar el certificado, ir a ca/rootcadev/ e instalar rootCa.pem y rootCa-key.pemm (certificado valido para localhost y subred de windoes hotspot 192.168.137.1 y 192.168.137.1.sslip.io)

> Para utilizar el servicio mDNS debe de instalarse Bonjour de Apple

---

## 📁 Estructura del Proyecto

```
    |--config.py
    |--requirements.txt
    |--run.py
    |--app/
        |--db.py
        |--models.py
        |--mqtt_client.py
        |--routes.py
        |--sse.py
        |--utils_time.py
        |--__init__.py
        |--iotelligence/
            |--core.py
            |--routes.py
            |--worker.py
            |--data/
                |--river_models.json
                |--estandar.json
                |--limites.json
            |--rules/
                |--base.py
                |--rule1.py
                |--rule2.py
                |--rule3.py
                |--rule4.py
                |--__init__.py
    |--instance/
```

- `app/__init__.py` ⚙️ — Inicializa la app Flask, base de datos y MQTT.  
- `app/db.py` 💾 — Configuración de SQLAlchemy.  
- `app/models.py` ✨ — Modelos `Dispositivo` y `EstadoLog`.  
- `app/mqtt_client.py` 📨 — Cliente MQTT que recibe mensajes y actualiza dispositivos.  
- `app/routes.py` 🔗 — API REST + SSE para gestionar dispositivos y estados.  
- `app/sse.py` 📡 — Manejador de suscriptores para emitir eventos en vivo (cola por cliente).  
- `config.py` ⚙️ — Configuración de la app (BD, MQTT, URL pública de backend).  
- `run.py` 🚀 — Arranque de la app (modo desarrollo).

---

## ⚙️ Configuración rápida (LAN)

En `config.py` puedes dejar una IP fija de tu PC en la red local:

```python
class Config:
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///iot.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BACKEND_HOST = "0.0.0.0"
    BACKEND_PORT = 5000
    PUBLIC_BACKEND_URL = "http://192.168.0.106:5000"  # <- dirección a usar en clientes

    MQTT_BROKER_URL = "192.168.0.106"
    MQTT_BROKER_PORT = 1883
    MQTT_KEEPALIVE = 60
    MQTT_TLS_ENABLED = False
```

> Abre los puertos 5000 (HTTP) y 1883 (MQTT) en tu firewall. En Android, habilita tráfico claro para esa IP si no usas HTTPS.

---

## ▶️ Ejecución

```bash
pip install -r requirements.txt
python run.py
```

---

## 🌐 Endpoints

- `GET /dispositivos` 🟢 Lista todos los dispositivos.  

- `GET /dispositivos/<id>` 🔍 Obtiene detalles de un dispositivo.  
- `PUT /dispositivos/<int:id>` ⚙️ Actualiza datos y **configuración** respetando el **modo** (`manual` o `horario`):  
  - **manual**: `encendido` manda → deriva `estado`.  
  - **horario**: `estado` manda → deriva `encendido`.  
- `GET /dispositivos/no-reclamados` ❓ Lista dispositivos detectados vía MQTT pero aún no reclamados.  
- `POST /dispositivos/reclamar` ✅ Reclama un dispositivo (nombre, tipo, modelo, descripción, configuración).  
- `GET /dispositivos/<id>/logs` 📜 Obtiene logs de estado del dispositivo, utiliza `dispositivos/<id>/logs?page=1&per_page=50` para ver por paginas.  
- `GET /stream/dispositivos` 📡 **SSE en tiempo real** (filtros opcionales):  
  - `?serial=SERIAL_NUMBER`  
  - `?reclamado=true|false`  

---

## 🔄 Funcionamiento General

Cada dispositivo IoT se representa con:

- `id` 🆔 (backend)  
- `serial_number` 🔢 (único)  
- `nombre` 🏷️, `tipo` 🔌, `modelo` 🛠️, `descripcion` 📝  
- `estado` 📊 (activo/inactivo)  
- `parametros {}` 📈 (ej. temperatura, watts)  
- `configuracion {}` ⚙️ (ej. `modo`, `encendido`, `horarios`)  
- `reclamado` ✅

### 🤖 Flujo con MQTT (automático)

1) El dispositivo (o simulador) publica por MQTT: `serial_number`, `estado`, `parametros`.  
2) El backend crea/actualiza el dispositivo en BD.  
3) Aparece en `/dispositivos/no-reclamados` hasta que la app lo **reclama**.  
4) Cada cambio dispara un **evento SSE** a los clientes conectados.

### 📲 Flujo con HTTP (reclamo via QR)

1) La app escanea un QR con datos: `serial_number`, `nombre`, `tipo`, `modelo`, `descripcion`, `configuracion`.  
2) Envía `POST /dispositivos/reclamar`.  
3) El backend marca `reclamado=True` y actualiza la información.

> **Nota:** `serial_number`, `estado` y `parametros` provienen del dispositivo/MQTT (no se editan por app).  
> `nombre`, `tipo`, `modelo`, `descripcion` y `configuracion` sí se editan por HTTP.

---

## 📡 SSE: Event streaming en tiempo real

Cuando un dispositivo cambia (por MQTT o `PUT`), el backend emite eventos SSE a `/stream/dispositivos`.  
El endpoint incluye **heartbeats** periódicos y JSON **compacto** para mayor estabilidad/eficiencia.

### 📦 Ejemplo de **evento SSE** (lo que recibe el cliente)

```
event: hello
data: {}

data: {"id":1,"serial_number":"TMP0603IF1WD","nombre":"Sensor Temp","tipo":"sensor","modelo":"T-01","descripcion":"Termómetro","estado":"activo","parametros":{"temp":23.4},"configuracion":{"modo":"manual","encendido":true},"reclamado":true,"event":"device_update"}

event: ping
data: {}
```

- `hello` → saludo inicial.  
- `device_update` → actualización de un dispositivo.  
- `ping` → heartbeat para mantener viva la conexión.

---

## 🐍 Script de prueba (Python) — **`sse_client.py`**

Este script se conecta al SSE (IP fija `192.168.0.106:5000`), acepta filtros y reconecta con **backoff**.

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import sys
import time
from urllib.parse import urlencode
import requests

BASE_URL = "http://192.168.0.106:5000"
STREAM_PATH = "/stream/dispositivos"

def pretty_json(s: str) -> str:
    try:
        return json.dumps(json.loads(s), ensure_ascii=False, indent=2)
    except Exception:
        return s

def build_url(base: str, path: str, serial: str | None, reclamado: str | None) -> str:
    qs = {}
    if serial:
        qs["serial"] = serial
    if reclamado:
        qs["reclamado"] = reclamado
    q = f"?{urlencode(qs)}" if qs else ""
    return f"{base.rstrip('/')}{path}{q}"

def consume_sse(url: str, show_raw: bool = False, session: requests.Session | None = None):
    sess = session or requests.Session()
    headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache", "Connection": "keep-alive"}
    with sess.get(url, headers=headers, stream=True, timeout=None) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} {resp.reason}")
        buffer_lines = []
        for raw_line in resp.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip("
")
            if show_raw:
                print(f"» {line}")
            if line == "":
                if buffer_lines:
                    data_lines = [l[5:].strip() for l in buffer_lines if l.startswith("data:")]
                    if data_lines:
                        data = "
".join(data_lines)
                        print("
📥 Evento dispositivo:")
                        print(pretty_json(data))
                    buffer_lines.clear()
                continue
            buffer_lines.append(line)

def main():
    parser = argparse.ArgumentParser(description="Cliente SSE para /stream/dispositivos (Flask).")
    parser.add_argument("--serial", help="Filtra por serial_number", default=None)
    parser.add_argument("--reclamado", choices=["true", "false"], help="Filtra por reclamado", default=None)
    parser.add_argument("--show-raw", action="store_true", help="Muestra las líneas crudas del stream")
    parser.add_argument("--max-retries", type=int, default=0, help="Máximo de reintentos (0 = infinito)")
    args = parser.parse_args()

    url = build_url(BASE_URL, STREAM_PATH, args.serial, args.reclamado)
    print(f"🔌 Conectando a: {url}
Ctrl+C para salir.
")

    attempt, backoff, backoff_max = 0, 2, 30
    sess = requests.Session()
    try:
        while True:
            if args.max_retries > 0 and attempt >= args.max_retries:
                print(f"🚫 Máximo de reintentos alcanzado ({args.max_retries}). Saliendo.")
                break
            attempt += 1
            try:
                print("✅ Conectado. Esperando eventos...")
                consume_sse(url, show_raw=args.show_raw, session=sess)
                print("ℹ️  Stream cerrado por el servidor. Reintentando...")
            except KeyboardInterrupt:
                print("
👋 Cancelado por el usuario.")
                break
            except Exception as e:
                print(f"⚠️  Error en el stream: {e}")
            time.sleep(backoff)
            backoff = min(backoff * 2, backoff_max)
    finally:
        sess.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
```

**Uso:**
```bash
python sse_client.py
python sse_client.py --serial TMP0603IF1WD
python sse_client.py --reclamado true
python sse_client.py --show-raw
```

---

## 🧪 Ejemplos de payloads HTTP

- **Actualizar dispositivo (modo manual):**
```bash
curl -X PUT http://192.168.0.106:5000/dispositivos/1   -H "Content-Type: application/json"   -d '{"configuracion":{"modo":"manual","encendido":true}}'
```

- **Reclamar dispositivo:**
```bash
curl -X POST http://192.168.0.106:5000/dispositivos/reclamar   -H "Content-Type: application/json"   -d '{"serial_number":"TMP0603IF1WD","nombre":"Sensor Temp","tipo":"sensor","modelo":"T-01","descripcion":"Termómetro","configuracion":{"modo":"manual","encendido":true}}'
```

---
  

## ⚖️ IoTelligence Rules

Además de la gestión básica de dispositivos, este backend incluye un motor de **reglas de IA** que monitorea automáticamente el comportamiento y configuración de los dispositivos.

Las notificaciones de reglas se emiten en tiempo real por **SSE** en el endpoint `/stream/ai`.


### 📏 Rule 1 — Valores Extremos (`extremos`)

- Evalúa métricas **numéricas** (`temperatura`, `humedad`, `watts`, etc.).
- Usa dos fuentes para definir límites aceptables:
1.  **`limites.json`** → valores estáticos por tipo de dispositivo.
2.  **Histórico** → percentiles calculados en base a registros previos.

- Si el valor se sale de los límites (con tolerancia configurable), emite:

```json
{
"event":  "ai_anomaly",
"rule":  "extremos",
"dispositivo_id":  1,
"serial_number":  "TMP0123...",
"metric":  "temperatura",
"value":  120.5,
"bounds": {"min":  10, "max":  80, "source":  "limits"},
"ts_local":  "...",
"ts_utc":  "..."
}
```

### ⚙️ Rule 2 — Misconfiguración (`misconfig`)

- Evalúa la **configuración declarada** de un dispositivo (`configuracion` en BD).
- Reglas mínimas definidas en **`estandar.json`**:
- El dispositivo debe estar en **modo `horario`**.

- El `intervalo_envio` debe estar dentro del rango `[min, max]`.

- Si no cumple, se genera un aviso con sugerencia de corrección:

```json
{
"event":  "ai_misconfig",
"rule":  "misconfig",
"dispositivo_id":  1,
"serial_number":  "RGD0...",
"issues": ["config.modo = 'manual' → se recomienda 'horario'"],
"suggested_patch": {"configuracion": {"modo":  "horario"}},
"severity":  "low",
"ts_local":  "...",
"ts_utc":  "..."
}
```

### 🧠 Rule 3 — Aprendizaje de Horarios  (`learn`)

- Aprende patrones de encendido/apagado por día de la semana y hora, y sugiere ventanas de operación.

- Modo real (online): modelo incremental (River) entrenado con la señal de estado/encendido.:

-  Post-procesado: une bins cercanos, redondea a minutos y limita nº de ventanas por día.

- Auditoría: si el dispositivo ya está en modo="horario", compara lo aprendido vs lo configurado y propone cambios solo si la diferencia supera un umbral.

**Modo Demo (opcional)**:

- Permite sugerencias sin entrenar en vivo.

- Fuente de datos: CSV o PKL por serial (whitelist de seriales demo).

- Útil para demos: genera sugerencias consistentes y replicables.

- Nombres de archivos esperados (por serial):

	- Modelo River: app/iotelligence/data/river_models/<SERIAL>.river.pkl

	- CSV demo: app/iotelligence/data/river_models/<SERIAL>.csv

	> Si AI_R3_DEMO_REQUIRE_FILES=True, solo se sugerirá para seriales listados en AI_R3_DEMO_SERIALS y con archivo presente.

```json
{
  "event": "ai_suggest",
  "rule": "learn",
  "dispositivo_id": 2,
  "serial_number": "RGD0ABC123",
  "suggested_horarios": {
    "lunes": [ {"inicio":"06:00","fin":"06:30"}, {"inicio":"18:00","fin":"18:30"} ],
    "jueves": [ {"inicio":"08:30","fin":"09:00"} ]
  },
  "bin_minutes": 30,
  "threshold": 0.55,
  "ts_local": "..."
}
```


### 🛑 Rule 4 — Watchdog Offlines  (`offline`)

- Detecta cuando un dispositivo reclamado deja de emitir durante un tiempo configurable.
	- Emite ai_offline al detectar la caída y, al regresar, ai_back_online.

```json
Ejemplo ai_offline:

{
  "event": "ai_offline",
  "rule": "offline",
  "dispositivo_id": 1,
  "serial_number": "TMP07JDE1RMQ",
  "seconds_offline": 129,
  "since_ts_local": "...",
  "ts_local": "...",
  "severity": "medium"
}

Ejemplo ai_back_online:

{
  "event": "ai_back_online",
  "rule": "offline",
  "dispositivo_id": 1,
  "serial_number": "TMP07JDE1RMQ",
  "was_offline_secs": 149,
  "ts_local": "...",
  "severity": "info"
}
```

### 🔔 SSE en `/stream/ai`

  

Eventos posibles:

  

-  `ai_anomaly` → regla 1 (valores fuera de rango).

  

-  `ai_misconfig` → regla 2 (configuración incorrecta).

  

---

  

## ⚙️ Configuración IoTelligence (`config.py`)

  

La lógica de IoTelligence se controla con parámetros configurables en `config.py`.

Estos valores permiten ajustar la sensibilidad y frecuencia de las notificaciones.

  

### 🔹 Rule 1 – Anomalías en métricas (`ai_anomaly`)

-  **AI_HIST_MIN_POINTS**: número mínimo de lecturas necesarias para calcular límites basados en histórico (ej. 150).

-  **AI_HIST_WINDOW_DAYS**: ventana de tiempo en días para usar datos históricos.

-  **AI_HIST_PMIN / AI_HIST_PMAX**: percentiles que definen el rango normal de la métrica (ej. 1% – 99%).

-  **AI_HIST_PAD_FRAC**: margen adicional (en %) alrededor de los límites históricos (ej. 5%).

-  **AI_HIST_PAD_ABS**: margen absoluto extra en las unidades de la métrica.

-  **AI_ALERT_TOL_FRAC**: tolerancia relativa (%) antes de disparar la alerta.

-  **AI_ALERT_TOL_ABS**: tolerancia absoluta en unidades (ej. 0.5°C).

> La tolerancia final será el valor **mayor** entre tolerancia absoluta y fraccional.

-  **AI_ALERT_COOLDOWN_S**: tiempo de enfriamiento (segundos) entre notificaciones de la misma métrica/dispositivo para evitar spam.

  

### 🔹 Rule 2 – Misconfiguraciones (`ai_misconfig`)

-  **AI_MISCONFIG_COOLDOWN_S**: tiempo mínimo (segundos) entre notificaciones de configuración incorrecta para un mismo dispositivo.

> Solo se notifica en la transición de **OK → MISCONFIG**. Si sigue en error, no se repite hasta que termine el cooldown.

### 🔹 Rule 3 – Learn (`ai_suggest`)

Resolución/umbral: AI_R3_BIN_MINUTES, AI_R3_PROB_THRESH, AI_R3_MIN_SPAN_BINS

Modelo: AI_R3_MODEL_DIR, AI_R3_SAVE_EVERY_N, AI_R3_WARM_START, AI_R3_RESET_ON_START

Sugerencias: AI_R3_COOLDOWN_S, AI_R3_MIN_EVENTS, AI_R3_SUGGEST_MIN_DIFF

Post-procesado: AI_R3_MIN_GAP_BINS, AI_R3_ROUND_TO_MIN, AI_R3_MAX_WINDOWS_PER_DAY

Auditoría vs horario: AI_R3_AUDIT_WHEN_HORARIO, AI_R3_DIFF_THRESH

Modo demo:

AI_R3_DEMO_MODE = True|False

AI_R3_DEMO_SOURCE = "csv"|"pkl"

AI_R3_DEMO_CSV_DIR = "app/iotelligence/data/river_models"

AI_R3_DEMO_TOPK_PER_DAY = 0 (0 = sin límite por día)

AI_R3_DEMO_SERIALS = ["RGD0ABC123"]

AI_R3_DEMO_REQUIRE_FILES = True

  
 ### 🔹 Rule 4 – Offline (`ai_offline / ai_back_online`)

AI_R4_OFFLINE_SECS (segundos sin señal para considerarlo offline)

AI_R4_WATCHDOG_TICK_SECS (intervalo de revisión)

AI_R4_REMIND_SECS (recordatorios mientras sigue offline; 0 = desactivado)

AI_R4_STARTUP_GRACE_SECS (gracia al arrancar el backend)

---

  

👉 Estos parámetros permiten balancear entre **sensibilidad** y **ruido de alertas**.

En pruebas locales se recomienda usar valores bajos (ej. cooldown de 60s).