# config.py
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)  # crea la carpeta si no existe

# Ruta base del proyecto (un nivel arriba de app/)
CA_DIR = os.path.join(BASE_DIR, "ca")  # carpeta donde se guarda server.crt.pem y server.key.pem

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
    BACKEND_HOST = "0.0.0.0"   # escucha en todas las interfaces
    BACKEND_PORT = 5000
    BACKEND_URL  = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    # --- MQTT ---
    MQTT_BROKER_URL = "localhost"
    MQTT_BROKER_PORT = 1883
    MQTT_KEEPALIVE = 60
    MQTT_TLS_ENABLED = False


    # --- App Movil ---
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret")   # cámbialo en producción
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", str(60 * 60 * 24)))  # 1 día (segundos)

    # --- SMTP / Email (para envío de códigos de seguridad) ---

    # Configurado para Gmail con App Password (recomendado).
    # IMPORTANTE: usa SSL directo en 465 (NO STARTTLS). Si prefieres STARTTLS, cambia:
    #   SMTP_PORT=587, SMTP_USE_SSL=0, SMTP_USE_TLS=1
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # 465 = SSL directo
    SMTP_USER = os.getenv("SMTP_USER", "smarthomeappiot2025@gmail.com")
    # App Password proporcionada:
    SMTP_PASS = os.getenv("SMTP_PASS", "cvkexbmjisiikxum")
    # Nombre que aparecerá en el remitente
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Smarthome")
    # Flags de seguridad (coherentes con el puerto 465 por defecto)
    SMTP_USE_SSL = bool(int(os.getenv("SMTP_USE_SSL", "1")))  # SSL directo
    SMTP_USE_TLS = bool(int(os.getenv("SMTP_USE_TLS", "0")))  # STARTTLS

    # --- Certificado y DNS -----
    SSL_ENABLED = False
    SSL_CERT_PATH = os.path.join(CA_DIR, "server.crt.pem")
    SSL_KEY_PATH  = os.path.join(CA_DIR, "server.key.pem")
    
    # URL base dinámica 
    if SSL_ENABLED:
        BACKEND_URL = f"https://{BACKEND_HOST}:{BACKEND_PORT}"
    else:
        BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

    # mDNS / Bonjour ---
    MDNS_ENABLED = False  # Cambia a False si no quieres anunciar el servicio
    MDNS_NAME = "smarthome.local"  # Nombre mDNS del backend (sin el punto final)


    # --- IOTELLIGENCE ---

    # Notificaciones Rule1 (ai anomaly) ------------------------------------------------------------
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

    # Notificaciones Rule2 (misconfig) ------------------------------------------------------------
    AI_MISCONFIG_DETECT_COOLDOWN_S = 5   # antirrebote para la 1ª alerta al caer en misconfig
    AI_MISCONFIG_REMIND = True            # si sigue en misconfig, enviar recordatorios
    AI_MISCONFIG_REMIND_COOLDOWN_S = 20  # cada cuánto recordar (p. ej. 15 min)
        
    # Notificaciones Rule3 (River)     ------------------------------------------------------------
    AI_R3_BIN_MINUTES = 30
    AI_R3_PROB_THRESH = 0.55
    AI_R3_MIN_SPAN_BINS = 1
    AI_R3_MODEL_DIR = "app/iotelligence/data/river_models"

    AI_R3_SAVE_EVERY_N = 50
    AI_R3_COOLDOWN_S = 200
    AI_R3_MIN_EVENTS = 0

    AI_R3_WARM_START = True
    AI_R3_RESET_ON_START = False
    AI_R3_AUDIT_WHEN_HORARIO = True
    AI_R3_DIFF_THRESH = 0.30

    # Post-procesado de ventanas
    AI_R3_MIN_GAP_BINS = 1      # fusiona huecos pequeños
    AI_R3_ROUND_TO_MIN = 30     # redondea inicios (down) y fines (up)
    AI_R3_MAX_WINDOWS_PER_DAY = 2

    # Hysteresis de sugerencias (evita spam si casi no cambió)
    AI_R3_SUGGEST_MIN_DIFF = 0.05  # 5%

    # DEMO: Para demostracion
    # Activar Modo demo
    AI_R3_DEMO_MODE = True
    # Tipo de archivo csv/pkl
    AI_R3_DEMO_SOURCE = "csv" #pkl or csv
    # Ubicacion de archivo
    AI_R3_DEMO_CSV_DIR = "app/iotelligence/data/river_models"
    AI_R3_DEMO_TOPK_PER_DAY = 0
    # Seriales permitidos para aplicar modo demo
    AI_R3_DEMO_SERIALS = ["RGD0ABC123"]
    # Requerido archivos
    AI_R3_DEMO_REQUIRE_FILES = True

    # Notificaciones Rule4 (offline watchdog) ------------------------------------------------------------
    # Tiempo sin recibir medidas para considerar OFFLINE
    AI_R4_OFFLINE_SECS = 60          # p.ej. 60s (ajústalo a tu caso)
    # Cada cuánto revisa el watchdog en segundo plano
    AI_R4_WATCHDOG_TICK_SECS = 10    # p.ej. cada 10s
    # Recordatorios mientras siga offline (0 = sin recordatorios)
    AI_R4_REMIND_SECS = 60         # p.ej. cada 5 min
    # Periodo de gracia al arrancar el backend para evitar falsos positivos
    AI_R4_STARTUP_GRACE_SECS = 30    # p.ej. 30s

    # Notificaciones Rule5 (open meteor) ------------------------------------------------------------
    # === Open-Meteo / Rule5 (SOLO 'current') ===============================
    OPENMETEO_LAT = 10.6544
    OPENMETEO_LON = -71.6533
    OPENMETEO_TIMEZONE = "America/Caracas"  # (no es estrictamente necesario para 'current')

    # Qué variables queremos del bloque 'current' de Open-Meteo.
    # Usa nombres CANÓNICOS internos: temperature, rain, precipitation, windspeed, uv_index, humidity, cloud_cover, shortwave_radiation
    # (Se mapearán a los nombres reales de Open-Meteo; si alguna no existe en 'current', quedará None.)
    OPENMETEO_CURRENT_FIELDS = [
        "temperature", "rain", "precipitation", "windspeed", "uv_index", "humidity", "cloud_cover", "shortwave_radiation"
    ]

    OPENMETEO_CACHE_TTL_S = 180   # cache corto (3 min) para 'current'
    OPENMETEO_CONNECT_TIMEOUT_S = 3
    OPENMETEO_READ_TIMEOUT_S = 5

    # Comportamiento Rule5
    WEATHER_ACTION_MODE = "notify_and_shutdown"  # "notify_only" | "notify_and_shutdown"
    WEATHER_COOLDOWN_S = 900
    WEATHER_ONLY_FOR_PREFIXES = []  # p.ej.: ["RGD0","LGT0"]