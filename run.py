from app import create_app, db
from config import Config

app = create_app()

with app.app_context():
    ## Reiniciar la bd (para pruebas)
    db.drop_all()
    db.create_all()
    print("Base de datos reiniciada")
    ################################

    app.run(
            host=Config.BACKEND_HOST,
            port=Config.BACKEND_PORT,
            debug=False,
            use_reloader=False
        )

