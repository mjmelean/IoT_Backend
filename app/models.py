# app/models.py
from app.db import db
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

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

    habitacion_id = db.Column(db.Integer, db.ForeignKey('habitacion.id'), nullable=True)

    # Relaciones útiles para el informe:
    # - estado_logs: mediciones/estados históricos (se llenan desde MQTT/PUT)
    # - accion_logs: auditoría de acciones del usuario/sistema (reclamar, asignar/quitar, renombrar, cambios de config, etc.)
    estado_logs = db.relationship(
        "EstadoLog",
        backref="dispositivo",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="EstadoLog.timestamp.asc()"
    )
    accion_logs = db.relationship(
        "AccionLog",
        backref="dispositivo",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="AccionLog.timestamp.asc()"
    )


class EstadoLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivo.id'), nullable=False, index=True)
    estado = db.Column(db.String(20))
    parametros = db.Column(JSON, default=dict)       # 👈
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ------------------------------------------------------------
# NUEVO: Auditoría de acciones para informes (Excel por equipo)
# ------------------------------------------------------------
class AccionLog(db.Model):
    """
    Log de acciones/eventos de negocio sobre un dispositivo.
    Ejemplos de `evento`:
      - "claimed"                -> Dispositivo reclamado por el usuario
      - "assigned_to_room"       -> Añadido a habitación (detalle: {"habitacion_id": X, "habitacion": "Sala"})
      - "removed_from_room"      -> Quitado de habitación (detalle: {...})
      - "renamed"                -> Cambió el nombre (detalle: {"old": "...", "new": "..."})
      - "config_changed"         -> Se actualizó configuración/parametros (detalle: payload o diff)
      - "action_performed"       -> Acciones tipo "apagarTodo", "blind_open", etc. (detalle: {"action": "...", ...})
    `actor`: "user" | "system" | "mqtt" | etc.
    """
    id = db.Column(db.Integer, primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivo.id'), nullable=False, index=True)
    evento = db.Column(db.String(50), nullable=False, index=True)
    detalle = db.Column(JSON, default=dict)  # se guarda payload/diff contextual
    actor = db.Column(db.String(50), default="user", nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# -------------------------
# Usuarios
# -------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), default="")
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    habitaciones = db.relationship("Habitacion", backref="owner", lazy=True)

    def set_password(self, raw: str):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)


class UserProfileExtra(db.Model):
    __tablename__ = "user_profile_extra"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False, index=True)

    # Guardamos la ruta relativa o URL absoluta del avatar. Recomendación: ruta relativa dentro de /static/avatars
    avatar_path = db.Column(db.String(255), default="", nullable=False)

    # Preferencia de tema del usuario: 'dark' (predeterminado) o 'light'
    theme = db.Column(db.String(12), default="dark", nullable=False)

    # relación opcional (no imprescindible para este caso)
    user = db.relationship("User", backref=db.backref("profile_extra", uselist=False))


class Habitacion(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(80), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    dispositivos = db.relationship("Dispositivo", backref="habitacion", lazy=True)


class SecurityCode(db.Model):
    __tablename__ = "security_code"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True, nullable=False)
    purpose = db.Column(db.String(50), nullable=False)  # ej: "change_password" o "forgot_password"
    code = db.Column(db.String(12), nullable=False)     # p.ej. 6 dígitos
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref=db.backref("security_codes", lazy=True))