
# IoT Backend

## Descripción

Este backend en **Flask** permite gestionar dispositivos IoT que envían su estado y configuración mediante **MQTT** o que son **reclamados vía HTTP** (por ejemplo, desde QR generado en IoT Alchemy).  
De esta forma, soporta tanto dispositivos físicos como dispositivos simulados.

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
## Endpoints

* `GET /dispositivos`
  Lista todos los dispositivos.

* `GET /dispositivos/<id>`
  Obtiene detalles de un dispositivo con id.

* `PUT /dispositivos/<id>/estado`
  Actualiza datos y configuracion del dispositivo (Enviados por HTTP).
  
* `GET /dispositivos/no-reclamados`
  Lista dispositivos detectados vía MQTT pero aún no reclamados.

* `POST /dispositivos/reclamar`
  Reclama un dispositivo existente con la información enviada (nombre, tipo, configuración, etc).

* `GET /dispositivos/<id>/logs`
  Obtiene logs de estado del dispositivo.


## Funcionamiento General de Creacion + Reclamado de dispositivos IoT

Los datos de los dispositivos IoT siguen esta estructura:
 *	`id`
 * `serial`
 * `nombre`
 * `tipo`
 * `modelo`
 * `descripcion`
 * `estado`
 * `parametros {}` 
 * `configuracion {}` 
 * `reclamado`

Las cuales son enviados por:
* MQTT :
	*  `serial`
	*  `estado`
	* `parametros {}` 
* HTPP :
	 * `nombre`
	 * `tipo`
	 * `modelo`
	 * `descripcion`
	 * `configuracion {}` 
	 
Los asignados y modificados automaticamente por el backend son:
* Backend :
	 * `id` (asignado automaticamente)
 	 * `reclamado` (true cuando un dispositivo es reclamado)

### 🔹 1. Flujo con MQTT (automático)
1. **Dispositivos IoT** envían mensajes MQTT con:

   * `serial_number`
   * `estado`
   * `parametros {}` (temperatura, humedad, watts, etc..)

2. El backend crea o actualiza el dispositivo en la base de datos automáticamente al recibir el MQTT.

3. Los dispositivos aparecen en la lista de dispositivos `/dispositivos/no-reclamados`.

4. La **app móvil** consulta esta lista y decide si reclamar un dispositivo, enviando una petición a la API para confirmarlo y actualizar sus datos.

---

### 🔹 2. Flujo con HTTP (QR + Reclamo directo)

1. Una vez localizado el dipositivo a reclamar se procede con el proceso de reclamo del Dispositivo

1. IoT Alchemy genera un **QR** con los datos básicos del dispositivo:
   - `serial`
   - `nombre`
   - `tipo`
   - `modelo`
   - `descripcion`
   - `configuracion {}`

2. La aplicación móvil escanea el QR y envía esos datos directamente al endpoint `/dispositivos/reclamar`.

3. El backend modifica `reclamado` a True y completa la informacion faltante

👉 Esto permite que el reclamo sea inmediato desde la app móvil.

⚠️ **Nota:**
* Los datos: **serial**, **estado** y **parámetros**,  siempre provienen del MQTT, por lo que no se pueden modificar desde la app movil y son propios de los dispositivos simulados
* Los datos **nombre**, **tipo**, **modelo**, **descripcion** que son enviando por http si son modificables; **configuraciones{}** tambien es modificable pero siguiendo una estructura especifica.

---

## Ejemplo de prueba 

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