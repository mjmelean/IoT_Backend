from app import create_app, db
from config import Config

# Crea la instancia de la aplicación
app = create_app()

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

    app.run(
        host=Config.BACKEND_HOST,
        port=Config.BACKEND_PORT,
        debug=False,
        use_reloader=False
    )