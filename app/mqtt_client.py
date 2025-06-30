import json
from flask import current_app
from flask_mqtt import Mqtt
from app.models import Dispositivo, EstadoLog
from app.db import db

mqtt = Mqtt()

def init_mqtt(app):
    app.config['MQTT_BROKER'] = 'localhost'
    app.config['MQTT_PORT'] = 1883
    mqtt.init_app(app)

    @mqtt.on_connect()
    def handle_connect(client, userdata, flags, rc):
        print("MQTT conectado")
        mqtt.subscribe("dispositivos/estado")

    @mqtt.on_message()
    def handle_message(client, userdata, message):
        with app.app_context():
            try:
                data = json.loads(message.payload.decode())
                serial = data.get("serial_number")
                estado = data.get("estado")
                parametros = data.get("parametros", {})

                if not serial:
                    print("[ERROR] MQTT: serial_number no proporcionado")
                    return

                dispositivo = Dispositivo.query.filter_by(serial_number=serial).first()

                if not dispositivo:
                    dispositivo = Dispositivo(
                        serial_number=serial,
                        nombre="No definido",
                        tipo="generico",
                        modelo="desconocido",
                        estado=estado or 'desconocido',
                        parametros=parametros,
                        reclamado=False
                    )
                    db.session.add(dispositivo)
                    db.session.commit()
                    print(f"[MQTT] Nuevo dispositivo creado: {serial}")
                else:
                    if estado:
                        dispositivo.estado = estado
                    if parametros:
                        dispositivo.parametros = parametros
                    db.session.commit()

                if dispositivo.id:
                    log = EstadoLog(
                        dispositivo_id=dispositivo.id,
                        estado=dispositivo.estado,
                        parametros=parametros
                    )
                    db.session.add(log)
                    db.session.commit()
                    print(f"[MQTT] Estado actualizado: {serial} -> {estado} | Parámetros: {parametros}")
            except Exception as e:
                print("[MQTT ERROR]", e)
                db.session.rollback()
