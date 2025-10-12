# app/mqtt_client.py
import json
from datetime import datetime, timezone               # <<< IoTelligence
from flask import current_app
from flask_mqtt import Mqtt
from app.models import Dispositivo, EstadoLog
from app.db import db
from sqlalchemy.exc import IntegrityError
from app.sse import publish as sse_publish
from app.iotelligence.core import dispatch_measure            # <<< IoTelligence

mqtt = Mqtt()

def init_mqtt(app):
    mqtt.init_app(app)

    @mqtt.on_connect()
    def handle_connect(client, userdata, flags, rc):
        print("✅ MQTT conectado")
        mqtt.subscribe("dispositivos/estado")

    @mqtt.on_message()
    def handle_message(client, userdata, message):
        with app.app_context():
            try:
                data = json.loads(message.payload.decode())
                serial = data.get("serial_number")
                estado = data.get("estado")
                parametros = data.get("parametros", {})
                configuracion = data.get("configuracion", {})

                if not serial:
                    print("[ERROR] MQTT: serial_number no proporcionado")
                    return

                # Buscar si ya existe el dispositivo
                dispositivo = Dispositivo.query.filter_by(serial_number=serial).first()

                if not dispositivo:
                    # Crear nuevo
                    dispositivo = Dispositivo(
                        serial_number=serial,
                        nombre="No definido",
                        tipo="generico",
                        modelo="desconocido",
                        descripcion="",
                        estado=estado or 'desconocido',
                        parametros=parametros,
                        configuracion=configuracion,
                        reclamado=False
                    )
                    db.session.add(dispositivo)

                # 🔄 Actualizar siempre (nuevo o existente)
                if estado:
                    dispositivo.estado = estado
                if parametros:
                    dispositivo.parametros = parametros
                if configuracion:
                    dispositivo.configuracion = configuracion

                try:
                    db.session.commit()
                    print(f"[MQTT] 🔄 Dispositivo creado/actualizado: {serial}")
                except IntegrityError:
                    db.session.rollback()
                    # Otro thread/mensaje ya creó el dispositivo → recuperarlo y actualizar
                    dispositivo = Dispositivo.query.filter_by(serial_number=serial).first()
                    if dispositivo:
                        if estado:
                            dispositivo.estado = estado
                        if parametros:
                            dispositivo.parametros = parametros
                        if configuracion:
                            dispositivo.configuracion = configuracion
                        db.session.commit()
                        print(f"[MQTT] ⚠ Dispositivo ya existía, actualizado: {serial}")

                # Registrar log de estado
                if dispositivo.id:
                    log = EstadoLog(
                        dispositivo_id=dispositivo.id,
                        estado=dispositivo.estado,
                        parametros=parametros
                    )
                    db.session.add(log)
                    db.session.commit()

                    # Notificar a la vista normal
                    sse_publish({
                        "id": dispositivo.id,
                        "serial_number": dispositivo.serial_number,
                        "nombre": dispositivo.nombre,
                        "tipo": dispositivo.tipo,
                        "modelo": dispositivo.modelo,
                        "descripcion": dispositivo.descripcion,
                        "estado": dispositivo.estado,
                        "parametros": dispositivo.parametros,
                        "configuracion": dispositivo.configuracion,
                        "reclamado": dispositivo.reclamado,
                        "event": "device_update"
                    })
                    print(f"[MQTT] 📒 Estado log registrado: {serial} -> {estado} | Parámetros: {parametros}")

                    # ...
                    # ===============================
                    # IoTelligence: Reglas (ONLINE)
                    # ===============================
                    now = datetime.now(timezone.utc)

                    # 1) Reglas de métricas (Rule1…) — SI HAY métricas numéricas
                    for metric, val in (dispositivo.parametros or {}).items():
                        dispatch_measure(dispositivo, metric, val, ts=now)

                    # 1.b) Heartbeat SIEMPRE (garantiza “visto” para Rule4)
                    dispatch_measure(dispositivo, "heartbeat", 1, ts=now)

                    # 2) Reglas de configuración (Rule2: Misconfigs)
                    dispatch_measure(dispositivo, None, None, ts=now)

                    # 3) Reglas de aprendizaje/estado (Rule3, etc.)
                    dispatch_measure(dispositivo, "__state__", None, ts=now)

            except Exception as e:
                print("[MQTT ERROR]", e)
                db.session.rollback()