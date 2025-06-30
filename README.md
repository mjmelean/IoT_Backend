
# Backend IoT - Gestión de Dispositivo

## Descripción

Este backend en Flask permite gestionar dispositivos IoT que envían su estado y configuración mediante MQTT. Los dispositivos se registran automáticamente en la base de datos cuando envían mensajes MQTT con toda su información. La aplicación móvil es la encargada de "reclamar" los dispositivos, confirmando que pertenecen al usuario/proyecto. Además, la app puede actualizar configuraciones, pero no los parámetros reales enviados por MQTT.

---

## Estructura del Proyecto

* `app/__init__.py` — Inicializa la app Flask, base de datos y MQTT.
* `app/db.py` — Configuración de SQLAlchemy.
* `app/models.py` — Modelos `Dispositivo` y `EstadoLog`.
* `app/mqtt_client.py` — Cliente MQTT que recibe mensajes y actualiza dispositivos.
* `app/routes.py` — API REST para gestionar dispositivos y estados.
* `config.py` — Configuración de la app (base de datos, MQTT).
* `run.py` — Script para arrancar la app y reiniciar base de datos (para pruebas).

---

## Funcionamiento General

1. **Dispositivos IoT** envían mensajes MQTT con:

   * `serial_number`
   * `estado`
   * `parametros` (datos reales como temperatura, humedad)
   * `configuracion` (configuración completa del dispositivo)

2. El backend crea o actualiza el dispositivo en la base de datos automáticamente al recibir el MQTT.

3. Los dispositivos aparecen en la lista de dispositivos **no reclamados**.

4. La **app móvil** consulta esta lista y decide si reclamar un dispositivo, enviando una petición a la API para confirmarlo y actualizar sus datos si es necesario.

5. Una vez reclamado, el dispositivo queda marcado como tal y no aparece en la lista de no reclamados.

6. La app móvil puede cambiar solo la configuración (`configuracion`) del dispositivo vía API, **pero no los parámetros reales** que siempre provienen del MQTT.

---

## Endpoints Clave

* `GET /dispositivos/no-reclamados`
  Lista dispositivos detectados vía MQTT pero aún no reclamados.

* `POST /dispositivos/reclamar`
  Reclama un dispositivo existente con la información enviada (nombre, tipo, configuración, etc).

* `GET /dispositivos`
  Lista todos los dispositivos.

* `GET /dispositivos/<id>`
  Obtiene detalles de un dispositivo.

* `PUT /dispositivos/<id>/estado`
  Actualiza estado y configuración (para uso interno).

* `GET /dispositivos/<id>/logs`
  Obtiene logs de estado del dispositivo.

---

## Ejemplo para Simular un Dispositivo y Reclamarlo

```python
import time
import json
import requests
import paho.mqtt.publish as publish

serial = "ABC123456"
mqtt_payload = json.dumps({
    "serial_number": serial,
    "estado": "activo",
    "parametros": {
        "temperatura": 22.5,
        "humedad": 55
    },
    "configuracion": {
        "intervalo_medicion": 60,
        "modo": "automático"
    }
})
base_url = "http://localhost:5000"

# Enviar mensaje MQTT con info completa
publish.single("dispositivos/estado", mqtt_payload, hostname="localhost")

# Esperar registro backend
time.sleep(3)

# Consultar dispositivos no reclamados
resp = requests.get(f"{base_url}/dispositivos/no-reclamados")
dispositivos = resp.json()

target = next((d for d in dispositivos if d["serial_number"] == serial), None)
if not target:
    print("Dispositivo no encontrado para reclamar.")
    exit(1)

# Reclamar dispositivo desde app móvil
reclamo_payload = {
    "serial_number": serial,
    "nombre": "Sensor de temperatura 1",
    "tipo": "sensor",
    "modelo": "ST-1000",
    "descripcion": "Sensor en sala 1",
    "configuracion": {
        "intervalo_medicion": 60,
        "modo": "manual"
    }
}
r = requests.post(f"{base_url}/dispositivos/reclamar", json=reclamo_payload)
print(r.json())

# Verificar que ya no aparezca como no reclamado
time.sleep(1)
verif_resp = requests.get(f"{base_url}/dispositivos/no-reclamados")
no_reclamados = verif_resp.json()

if any(d["serial_number"] == serial for d in no_reclamados):
    print("Fallo: dispositivo aún no reclamado.")
else:
    print("Éxito: dispositivo reclamado correctamente.")
```

---

## Notas Importantes

* Los **parámetros** (estado real, sensores) solo se actualizan vía MQTT y no pueden ser modificados desde la app móvil.
* La **configuración** puede ser cambiada por la app móvil a través de la API.
* El proceso de reclamo es para validar y confirmar que el dispositivo pertenece a un usuario o proyecto.
* Para pruebas locales, el script `run.py` reinicia la base de datos al iniciar la app.

---


