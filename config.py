import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

#Config del backend
class Config:
    MQTT_BROKER = 'localhost'
    MQTT_PORT = 1883
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'iot.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
