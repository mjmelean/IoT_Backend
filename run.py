from app import create_app, db
from config import Config
from zeroconf import ServiceInfo, Zeroconf
import os, socket

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

# Anunciar el servicio mDNS (Bonjour)   
def announce_mdns():
    """Publica el backend como smarthome.local en la red local"""
    zeroconf = Zeroconf()
    try:
        # Define el tipo de servicio (HTTP o HTTPS)
        service_type = "_https._tcp.local." if getattr(Config, "SSL_ENABLED", False) else "_http._tcp.local."
        # Nombre de servicio visible en red
        service_name = "SmartHome Backend._https._tcp.local." if Config.SSL_ENABLED else "SmartHome Backend._http._tcp.local."
        # Dirección local (usa la IP actual de la máquina)
        local_ip = socket.gethostbyname(socket.gethostname())
        # Descripción básica (opcional)
        desc = {'path': '/'}

        info = ServiceInfo(
            type_=service_type,
            name=service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=Config.BACKEND_PORT,
            properties=desc,
            server="smarthome.local."
        )

        zeroconf.register_service(info)
        print(f"[mDNS] Servicio publicado como smarthome.local ({local_ip}:{Config.BACKEND_PORT})")
        return zeroconf
    except Exception as e:
        print(f"[WARN] No se pudo anunciar mDNS: {e}")
        zeroconf.close()
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

        # Publicar el servicio mDNS
        # Solo anunciar si está habilitado
        zeroconf = None
        if getattr(Config, "MDNS_ENABLED", False):
            zeroconf = announce_mdns()
        else:
            print("[mDNS] Desactivado en configuración")

        try:
            app.run(
                host=Config.BACKEND_HOST,
                port=Config.BACKEND_PORT,
                debug=False,
                use_reloader=False,
                ssl_context=ssl_ctx
            )
            
        finally:
            if zeroconf:
                zeroconf.unregister_all_services()
                zeroconf.close()
                print("[mDNS] Servicio cerrado")