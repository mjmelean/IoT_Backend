from flask import Blueprint, request, jsonify
from flask import Response, stream_with_context, request
from app.models import Dispositivo, EstadoLog
from app.db import db
from app.sse import subscribe, unsubscribe

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

@bp.route('/dispositivos/<int:id>', methods=['PUT'])
def actualizar_dispositivo(id):
    """
    Actualiza un dispositivo respetando el modo:
      - manual: 'encendido' manda, deriva 'estado'
      - horario: 'estado' manda, deriva 'encendido'
      - otro: acepta lo que venga y mantiene consistencia
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Datos JSON inválidos o faltantes"}), 400

        dispositivo = Dispositivo.query.get_or_404(id)

        # Tomar configuracion actual y mezclar con payload
        cfg_actual = dispositivo.configuracion or {}
        cfg_payload = data.get("configuracion") or {}
        cfg = {**cfg_actual, **cfg_payload}

        # Detectar modo
        modo = (cfg.get("modo") or "").lower()

        # Normalizadores
        estado_in = str(data.get("estado", "")).lower()
        if estado_in in ("activo", "on", "true", "1"):
            estado_in = "activo"
        elif estado_in in ("inactivo", "off", "false", "0"):
            estado_in = "inactivo"
        else:
            estado_in = None

        encendido_in = data.get("encendido")
        if encendido_in is not None:
            encendido_in = bool(encendido_in)

        # --- Reglas según modo ---
        if modo == "manual":
            # encendido manda
            if encendido_in is not None:
                cfg["encendido"] = encendido_in
                dispositivo.estado = "activo" if encendido_in else "inactivo"
            elif estado_in:
                dispositivo.estado = estado_in
                cfg["encendido"] = (estado_in == "activo")

        elif modo == "horario":
            # estado manda
            if estado_in:
                dispositivo.estado = estado_in
                cfg["encendido"] = (estado_in == "activo")
            elif encendido_in is not None:
                cfg["encendido"] = encendido_in
                dispositivo.estado = "activo" if encendido_in else "inactivo"

        else:
            # sin modo definido → mantener consistencia
            if estado_in:
                dispositivo.estado = estado_in
                cfg["encendido"] = (estado_in == "activo")
            elif encendido_in is not None:
                cfg["encendido"] = encendido_in
                dispositivo.estado = "activo" if encendido_in else "inactivo"

        # Guardar configuracion final
        dispositivo.configuracion = cfg

        # Actualizar otros campos si vienen
        if "nombre" in data:
            dispositivo.nombre = data["nombre"]
        if "tipo" in data:
            dispositivo.tipo = data["tipo"]
        if "modelo" in data:
            dispositivo.modelo = data["modelo"]
        if "descripcion" in data:
            dispositivo.descripcion = data["descripcion"]
        if "parametros" in data:
            dispositivo.parametros = data["parametros"]

        # Registrar log si cambió estado o parámetros
        log = EstadoLog(
            dispositivo_id=dispositivo.id,
            estado=dispositivo.estado,
            parametros=dispositivo.parametros or {}
        )
        db.session.add(log)

        db.session.commit()

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

        return jsonify({
            "mensaje": "Dispositivo actualizado",
            "id": dispositivo.id,
            "estado": dispositivo.estado,
            "configuracion": dispositivo.configuracion
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Error al actualizar dispositivo", "detalle": str(e)}), 500


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
        page = int(request.args.get('page', 1))
        per_page = min(int(request.args.get('per_page', 50)), 200)

        q = EstadoLog.query.filter_by(dispositivo_id=id).order_by(EstadoLog.timestamp.desc())
        items = q.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": items.total,
            "pages": items.pages,
            "data": [
                {
                    "estado": log.estado,
                    "parametros": log.parametros,
                    "timestamp": log.timestamp.isoformat()
                } for log in items.items
            ]
        })
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

        # 🚫 Nuevo: impedir reclamos duplicados
        if dispositivo.reclamado:
            return jsonify({"error": "El dispositivo ya fue reclamado previamente"}), 409

        # ✅ Actualizar datos solo si vienen en el payload
        if "nombre" in data:       dispositivo.nombre = data["nombre"]
        if "tipo" in data:         dispositivo.tipo = data["tipo"]
        if "modelo" in data:       dispositivo.modelo = data["modelo"]
        if "descripcion" in data:  dispositivo.descripcion = data["descripcion"]
        if "configuracion" in data:
            dispositivo.configuracion = data["configuracion"]

        dispositivo.reclamado = True

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

@bp.route('/stream/dispositivos', methods=['GET'])
def stream_dispositivos():
    # Filtros opcionales para vista: ?reclamado=true&serial=ABC123
    serial = request.args.get('serial')
    recl   = request.args.get('reclamado')

    def gen():
        q = subscribe()
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                evt = q.get()  # bloquea hasta nuevo evento
                if serial and evt.get("serial_number") != serial: 
                    continue
                if recl in ('true','false') and str(evt.get("reclamado")).lower() != recl:
                    continue
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        finally:
            unsubscribe(q)

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # evita buffering en Nginx
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(gen()), headers=headers)