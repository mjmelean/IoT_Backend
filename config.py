import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)  # crea la carpeta si no existe

class Config:

    # --- Hora del Backend ---
    try:
        import tzlocal
        BACKEND_TZ = str(tzlocal.get_localzone())  # e.g. "America/Caracas"
    except Exception:
        BACKEND_TZ = "America/Caracas"

    # --- Flask ---
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(INSTANCE_DIR, 'iot.db')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False, "timeout": 30},
        "pool_pre_ping": True,
        }
    SQLALCHEMY_SESSION_OPTIONS = {
        "expire_on_commit": False,   # <- clave para no “expirar” instancias al commit
        }
    BACKEND_TZ = "America/Caracas"
    
    # --- Dirección del backend (hardcodeada) ---
    BACKEND_HOST = "localhost"   # escucha en todas las interfaces
    BACKEND_PORT = 5000
    BACKEND_URL  = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    # --- MQTT ---
    MQTT_BROKER_URL = "localhost"
    MQTT_BROKER_PORT = 1883
    MQTT_KEEPALIVE = 60
    MQTT_TLS_ENABLED = False

    # --- IOTELLIGENCE ---

    # Notificaciones Rule1 (ai anomaly)
    AI_HIST_MIN_POINTS = 150     # lecturas mínimas para usar histórico puro
    AI_HIST_WINDOW_DAYS = 30    # ventana histórica
    AI_HIST_PMIN = 1.0          # percentil inferior
    AI_HIST_PMAX = 99.0         # percentil superior
    AI_HIST_PAD_FRAC = 0.05     # padding = 5% del rango histórico
    AI_HIST_PAD_ABS  = 0.0      # padding absoluto extra (en unidades de la métrica)
    # Tolerancia al comparar valor vs límites
    AI_ALERT_COOLDOWN_S = 60  # segundos (antirebote)
    AI_ALERT_TOL_FRAC = 0.02    # 2% del rango final
    AI_ALERT_TOL_ABS  = 0.5     # o 0.5 unidades (lo que sea mayor)

    # Notificaciones Rule2 (misconfig)
    AI_MISCONFIG_COOLDOWN_S = 60  # Tiempo de espera hasta volver a revisar una config
    

    

