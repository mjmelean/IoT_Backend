# app/__init__.py
from flask import Flask, jsonify
from app.db import db
from app.routes import bp
from app.mqtt_client import init_mqtt
from config import Config
from app.iotelligence.routes import bp_ai
from app.iotelligence.worker import init as init_ai_worker
from sqlalchemy import text   # <<< importante para ejecutar SQL nativo
from flask_jwt_extended import JWTManager

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # (Opcional) ver la zona horaria detectada
    print(f"[TZ] Usando zona horaria: {app.config.get('BACKEND_TZ', 'America/Caracas')}")

    db.init_app(app)
    JWTManager(app)
    app.register_blueprint(bp)
    app.register_blueprint(bp_ai)  # IoTelligence comparte la misma URL

    with app.app_context():
        db.create_all()

        # ⚡ Activar WAL y mejorar concurrencia en SQLite
        try:
            db.session.execute(text("PRAGMA journal_mode=WAL;"))
            db.session.execute(text("PRAGMA synchronous=NORMAL;"))
            db.session.commit()
            print("[DB] WAL activado (journal_mode=WAL, synchronous=NORMAL)")
        except Exception as e:
            print(f"[DB] No se pudo activar WAL: {e}")

    # Inicializa MQTT
    init_mqtt(app)

    # <<< INICIALIZA EL WORKER DE IA (para jobs batch con app_context)
    init_ai_worker(app, max_workers=2)

    # Manejadores globales de errores
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"error": "Recurso no encontrado"}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({"error": "Error interno del servidor"}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        db.session.rollback()
        return jsonify({"error": "Error inesperado", "detalle": str(e)}), 500

    return app