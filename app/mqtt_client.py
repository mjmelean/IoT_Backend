import json
from flask import current_app
from flask_mqtt import Mqtt
from app.models import Dispositivo, EstadoLog
from app.db import db
from sqlalchemy.exc import IntegrityError

mqtt = Mqtt()

def init_mqtt(app):
    app.config['MQTT_BROKER'] = 'localhost'
    app.config['MQTT_PORT'] = 1883
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
                    print(f"[MQTT] 📒 Estado log registrado: {serial} -> {estado} | Parámetros: {parametros}")

            except Exception as e:
                print("[MQTT ERROR]", e)
                db.session.rollback()
