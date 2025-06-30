from app import create_app, db

app = create_app()

with app.app_context():
    ## Reiniciar la bd (para pruebas)
    db.drop_all()
    db.create_all()
    print("Base de datos reiniciada")
    ################################

    app.run(debug=True)
