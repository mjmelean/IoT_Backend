from app import create_app, db
from config import Config
import os

# Crea la instancia de la aplicación
app = create_app()

# Verificia si existe certificado SSL
def get_ssl_context():
    """Verifica si existen los certificados SSL y devuelve la tupla (cert, key)"""
    if getattr(Config, "SSL_ENABLED", False):
        cert = Config.SSL_CERT_PATH
        key = Config.SSL_KEY_PATH
        if os.path.isfile(cert) and os.path.isfile(key):
            print(f"[HTTPS] Certificados encontrados en: {os.path.dirname(cert)}")
            return (cert, key)
        else:
            print(f"[WARN] SSL habilitado pero faltan archivos: {cert} o {key}. Iniciando sin HTTPS.")
    return None

if __name__ == "__main__":
    # Usamos el contexto de la aplicación para poder acceder a las configuraciones
    # y componentes de Flask/SQLAlchemy antes de ejecutar el servidor.
    with app.app_context():
        # Se han eliminado las líneas db.drop_all() y db.create_all().
        # La aplicación ahora se iniciará usando la base de datos existente.

        # Si necesitas crear las tablas por primera vez (solo una vez), puedes
        # descomentar temporalmente la línea de abajo:
        # db.create_all()

        ## Reiniciar la bd (para pruebas)
        db.drop_all()
        db.create_all()
        print("Base de datos reiniciada")

        # Obtener contexto SSL si está disponible
        ssl_ctx = get_ssl_context()

        # Mostrar modo activo
        mode = "HTTPS" if ssl_ctx else "HTTP"
        print(f"[{mode}] Servidor ejecutándose en {Config.BACKEND_HOST}:{Config.BACKEND_PORT}")

        app.run(
            host=Config.BACKEND_HOST,
            port=Config.BACKEND_PORT,
            debug=False,
            use_reloader=False,
            ssl_context=ssl_ctx
        )