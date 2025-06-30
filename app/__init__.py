from flask import Flask, jsonify
from app.db import db
from app.routes import bp
from app.mqtt_client import init_mqtt
from config import Config  

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)  

    db.init_app(app)
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()

    init_mqtt(app)

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
