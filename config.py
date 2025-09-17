import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)  # crea la carpeta si no existe

class Config:
    # --- Flask ---
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(INSTANCE_DIR, 'iot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Dirección del backend (hardcodeada) ---
    BACKEND_HOST = "0.0.0.0"   # escucha en todas las interfaces
    BACKEND_PORT = 5000
    BACKEND_URL  = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    # --- MQTT ---
    MQTT_BROKER_URL = "localhost"
    MQTT_BROKER_PORT = 1883
    MQTT_KEEPALIVE = 60
    MQTT_TLS_ENABLED = False

