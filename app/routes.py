from flask import Blueprint, request, jsonify
from app.models import Dispositivo, EstadoLog
from app.db import db

bp = Blueprint('routes', __name__)

@bp.route('/dispositivos', methods=['POST'])
def agregar_dispositivo():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Datos JSON inválidos o faltantes"}), 400

        nuevo = Dispositivo(
            serial_number=data.get('serial_number'),
            nombre=data.get('nombre'),
            tipo=data.get('tipo'),
            modelo=data.get('modelo', ''),
            descripcion=data.get('descripcion', ''),
            estado=data.get('estado', 'desconocido'),
            parametros={},
            configuracion=data.get('configuracion', {}),
            reclamado=data.get('reclamado', False)  # <-- Nuevo campo opcional
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({"mensaje": "Dispositivo agregado", "id": nuevo.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al agregar dispositivo", "detalle": str(e)}), 500

@bp.route('/dispositivos/<int:id>/estado', methods=['PUT'])
def cambiar_estado(id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Datos JSON inválidos o faltantes"}), 400

        dispositivo = Dispositivo.query.get_or_404(id)

        # ✅ Actualizamos con helper
        update_dispositivo_from_payload(dispositivo, data)

        log = EstadoLog(
            dispositivo_id=id,
            estado=dispositivo.estado,
            parametros=dispositivo.parametros
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({"mensaje": "Estado actualizado", "id": dispositivo.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar estado", "detalle": str(e)}), 500


@bp.route('/dispositivos/<int:id>', methods=['GET'])
def obtener_dispositivo(id):
    try:
        dispositivo = Dispositivo.query.get_or_404(id)
        return jsonify({
            "id": dispositivo.id,
            "serial_number": dispositivo.serial_number,
            "nombre": dispositivo.nombre,
            "tipo": dispositivo.tipo,
            "modelo": dispositivo.modelo,
            "descripcion": dispositivo.descripcion,
            "estado": dispositivo.estado,
            "parametros": dispositivo.parametros,
            "configuracion": dispositivo.configuracion,
            "reclamado": dispositivo.reclamado  # <-- Nuevo campo en respuesta
        })
    except Exception as e:
        return jsonify({"error": "Error al obtener dispositivo", "detalle": str(e)}), 500

@bp.route('/dispositivos', methods=['GET'])
def obtener_todos():
    try:
        dispositivos = Dispositivo.query.all()
        return jsonify([
            {
                "id": d.id,
                "serial_number": d.serial_number,
                "nombre": d.nombre,
                "tipo": d.tipo,
                "modelo": d.modelo,
                "descripcion": d.descripcion,
                "estado": d.estado,
                "parametros": d.parametros,
                "configuracion": d.configuracion,
                "reclamado": d.reclamado  # <-- Nuevo campo en respuesta
            } for d in dispositivos
        ])
    except Exception as e:
        return jsonify({"error": "Error al obtener dispositivos", "detalle": str(e)}), 500

@bp.route('/dispositivos/<int:id>/logs', methods=['GET'])
def obtener_logs(id):
    try:
        logs = EstadoLog.query.filter_by(dispositivo_id=id).order_by(EstadoLog.timestamp.desc()).all()
        return jsonify([
            {
                "estado": log.estado,
                "parametros": log.parametros,
                "timestamp": log.timestamp.isoformat()
            } for log in logs
        ])
    except Exception as e:
        return jsonify({"error": "Error al obtener logs", "detalle": str(e)}), 500

@bp.route('/dispositivos/reclamar', methods=['POST'])
def reclamar_dispositivo():
    try:
        data = request.get_json()
        if not data or 'serial_number' not in data:
            return jsonify({"error": "Debe proporcionar serial_number"}), 400

        serial = data['serial_number']
        dispositivo = Dispositivo.query.filter_by(serial_number=serial).first()

        if not dispositivo:
            return jsonify({"error": "Dispositivo no encontrado. Asegúrese de que haya sido detectado por MQTT"}), 404

        # ✅ Usamos helper con reclamar=True
        update_dispositivo_from_payload(dispositivo, data, reclamar=True)

        db.session.commit()
        return jsonify({
            "mensaje": "Dispositivo reclamado correctamente",
            "id": dispositivo.id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al reclamar dispositivo", "detalle": str(e)}), 500

# Nuevo endpoint para obtener dispositivos no reclamados
@bp.route('/dispositivos/no-reclamados', methods=['GET'])
def obtener_no_reclamados():
    try:
        dispositivos = Dispositivo.query.filter_by(reclamado=False).all()
        return jsonify([
            {
                "id": d.id,
                "serial_number": d.serial_number,
                "estado": d.estado,
                "parametros": d.parametros,
                "configuracion": d.configuracion,
                "reclamado": d.reclamado
            } for d in dispositivos
        ])
    except Exception as e:
        return jsonify({"error": "Error al obtener dispositivos no reclamados", "detalle": str(e)}), 500

## Helper
def update_dispositivo_from_payload(dispositivo, data, reclamar=False):
    """
    Actualiza un dispositivo desde un payload recibido.
    - Si reclamar=True, también marca el dispositivo como reclamado.
    """
    if "nombre" in data:
        dispositivo.nombre = data["nombre"]
    if "tipo" in data:
        dispositivo.tipo = data["tipo"]
    if "modelo" in data:
        dispositivo.modelo = data["modelo"]
    if "descripcion" in data:
        dispositivo.descripcion = data["descripcion"]
    if "estado" in data:
        dispositivo.estado = data["estado"]
    if "parametros" in data:
        dispositivo.parametros = data["parametros"]
    if "configuracion" in data:
        dispositivo.configuracion = data["configuracion"]

    if reclamar:
        dispositivo.reclamado = True

    return dispositivo
