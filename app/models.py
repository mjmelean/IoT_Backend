from app.db import db
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime

class Dispositivo(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    modelo = db.Column(db.String(100), default='generico')
    descripcion = db.Column(db.String(255), default='')
    estado = db.Column(db.String(20), default='desconocido')
    parametros = db.Column(JSON, default=dict)       # 👈
    configuracion = db.Column(JSON, default=dict)    # 👈
    reclamado = db.Column(db.Boolean, default=False)

class EstadoLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivo.id'), nullable=False)
    estado = db.Column(db.String(20))
    parametros = db.Column(JSON, default=dict)       # 👈
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

