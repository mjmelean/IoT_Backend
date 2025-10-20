# app/iotelligence/dev_kinds.py
KIND_BY_SERIAL_PREFIX = {
    "LGT0": "luz", "RGD0": "riego", "SHD0": "persiana", "FAN0": "ventilador",
    "DRL0": "puerta", "TMP0": "termometro", "CAM0": "camara", "PLG0": "enchufe",
    "LUX0": "sensor_luz", "CO20": "sensor_co2", "SMK0": "sensor_humo",
    "MOV0": "sensor_mov", "SND0": "sensor_ruido",
}

CAPABILITY_BY_KIND = {
    "luz":"binary","enchufe":"binary","camara":"binary",
    "persiana":"position","ventilador":"speed","puerta":"lock",
    "riego":"duration","termometro":"setpoint","aire":"setpoint",
    "sensor_luz":"sensor","sensor_co2":"sensor","sensor_humo":"sensor",
    "sensor_mov":"sensor","sensor_ruido":"sensor",
}

def infer_kind(serial: str, cfg: dict) -> str:
    cfg = cfg or {}
    for key in ("kind","tipo","subtipo"):
        v = cfg.get(key)
        if v: return str(v).strip().lower()
    for pref, kind in KIND_BY_SERIAL_PREFIX.items():
        if str(serial or "").startswith(pref):
            return kind
    return "luz"

def infer_capability(kind: str, cfg: dict) -> str:
    cfg = cfg or {}
    if "capability" in cfg and cfg["capability"]:
        return str(cfg["capability"]).strip().lower()
    # tolera "capabilities": "binary" o ["position_percent"]
    if "capabilities" in cfg and cfg["capabilities"]:
        val = cfg["capabilities"]
        if isinstance(val, list): 
            return str(val[0]).strip().lower()
        return str(val).strip().lower()
    return CAPABILITY_BY_KIND.get(kind, "binary")