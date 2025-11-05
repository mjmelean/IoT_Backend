from __future__ import annotations
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import os, json, time, requests
from flask import current_app
from app.iotelligence.rules.base import Rule
from app.sse import publish as sse_publish
from app.models import Dispositivo
from app.db import db
from app.utils_time import now_utc, iso_local

# ===== Carga de estándar por prefijo =====
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_STD_PATH = os.path.join(_DATA_DIR, "estandar_meteo.json")

_STD: Dict[str, List[Dict[str, Any]]] = {}
_STD_LOADED = False

def _ensure_and_load_std():
    global _STD_LOADED
    if _STD_LOADED:
        return
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.isfile(_STD_PATH):
        with open(_STD_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    try:
        with open(_STD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    _STD[k] = v
    except Exception:
        _STD.clear()
    _STD_LOADED = True

def _rules_for_serial(serial: str) -> List[Dict[str, Any]]:
    _ensure_and_load_std()
    out: List[Dict[str, Any]] = []
    for pfx, arr in _STD.items():
        if serial.startswith(pfx):
            out.extend(arr or [])
    return out

# ===== Cooldown antirrebote por dispositivo y métrica =====
_COOLDOWN: Dict[tuple[int, str], float] = {}

def _hit_cooldown(disp_id: int, metric: str) -> bool:
    cd = int(current_app.config.get("WEATHER_COOLDOWN_S", 900))
    now = time.time()
    key = (disp_id, metric)
    last = _COOLDOWN.get(key, 0.0)
    if now - last < cd:
        return True
    _COOLDOWN[key] = now
    return False

# ===== Lectura del endpoint local /meteo =====
def _fetch_meteo_from_backend() -> Optional[Dict[str, Any]]:
    base = current_app.config.get("EXTERNAL_BASE_URL")  # si tienes
    try:
        # Llama a sí mismo: mejor construir URL absoluta desde request.url_root,
        # pero aquí usamos fallback a localhost
        url = (base.rstrip("/") + "/meteo") if base else "http://127.0.0.1:5000/meteo"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            js = r.json()
            return js.get("data")
    except Exception:
        pass
    return None

# ===== Helper: toma el "último valor" de una serie hourly =====
def _get_metric_current(data: dict, metric_name: str) -> Optional[float]:
    """
    Toma el valor actual desde el dict CANÓNICO servido por /meteo:
      data = {"temperature":..,"rain":..,"precipitation":..,"windspeed":..,"uv_index":..,"humidity":.., ...}
    Acepta nombres 'crudos' (p.ej. temperature_2m, wind_speed_10m) mapeándolos a canónicos.
    """
    if not isinstance(data, dict):
        return None

    # mapear originales -> canónicos (por compatibilidad con tu estándar existente)
    to_canon = {
        "temperature_2m": "temperature",
        "wind_speed_10m": "windspeed",
        "relative_humidity_2m": "humidity",
        "uv_index": "uv_index",
        "precipitation": "precipitation",
        "rain": "rain",
        "cloud_cover": "cloud_cover",
        "shortwave_radiation": "shortwave_radiation",
        # ya canónicos:
        "temperature": "temperature",
        "windspeed": "windspeed",
        "humidity": "humidity",
    }

    canon = to_canon.get(metric_name, metric_name)
    val = data.get(canon)
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except Exception:
        return None

def _cmp(op: str, a: float, b: float) -> bool:
    if op == ">":  return a >  b
    if op == ">=": return a >= b
    if op == "<":  return a <  b
    if op == "<=": return a <= b
    if op == "==": return a == b
    if op == "!=": return a != b
    return False

def _maybe_shutdown_device(disp: Dispositivo, reason: Dict[str, Any]) -> bool:
    """
    Fuerza modo=manual + encendido=False. Devuelve True si se guardó cambio.
    Respetamos WEATHER_ACTION_MODE (notify_only vs notify_and_shutdown).
    """
    mode = str(current_app.config.get("WEATHER_ACTION_MODE", "notify_and_shutdown")).lower()
    if mode != "notify_and_shutdown":
        return False

    cfg = dict(disp.configuracion or {})
    # si ya está manual+apagado, no hacemos nada
    if str(cfg.get("modo", "")).lower() == "manual" and not bool(cfg.get("encendido", True)):
        return False

    cfg["modo"] = "manual"
    cfg["encendido"] = False
    disp.configuracion = cfg
    disp.estado = "inactivo"

    # Log mínimo en DB; (opcional) podrías insertar EstadoLog si quieres
    db.session.add(disp)
    db.session.commit()
    return True

class Rule5Weather(Rule):
    name = "weather"

    def applies_realtime(self, disp, metric, value) -> bool:
        # Aplica a cualquiera reclamado (no depende de metric/value)
        return getattr(disp, "reclamado", False)

    def on_measure(self, dispositivo: Dispositivo, metric: str, value, ts: datetime) -> None:
        if not getattr(dispositivo, "reclamado", False):
            return

        # Filtrado opcional por prefijos
        allow = current_app.config.get("WEATHER_ONLY_FOR_PREFIXES", [])
        if allow:
            if not any(dispositivo.serial_number.startswith(p) for p in allow if isinstance(p, str)):
                return

        rules = _rules_for_serial(dispositivo.serial_number or "")
        if not rules:
            return

        meteo = _fetch_meteo_from_backend()
        if not meteo:
            return

        for rule in rules:
            metric_name = str(rule.get("metric", "")).strip()
            op = str(rule.get("op", ">")).strip()
            thr = rule.get("threshold", None)
            action = str(rule.get("action", "notify")).strip().lower()

            if metric_name == "" or thr is None:
                continue

            cur = _get_metric_current(meteo, metric_name)
            if cur is None:
                continue

            if not _cmp(op, cur, float(thr)):
                continue  # no cumple condición

            # cooldown por (device, metric)
            if _hit_cooldown(dispositivo.id, metric_name):
                continue

            # Notificar
            ts_utc = ts or now_utc()
            payload = {
                "event": "ai_weather",
                "rule": self.name,
                "dispositivo_id": dispositivo.id,
                "serial_number": dispositivo.serial_number,
                "metric": metric_name,
                "value": cur,
                "op": op,
                "threshold": float(thr),
                "action": action,
                "ts_local": iso_local(ts_utc),
                "ts_utc": ts_utc.isoformat()
            }
            sse_publish(payload)

            # Acción
            if action == "shutdown":
                changed = _maybe_shutdown_device(dispositivo, payload)
                if changed:
                    # opcional: emite un evento adicional
                    sse_publish({
                        "event": "ai_weather_action",
                        "rule": self.name,
                        "dispositivo_id": dispositivo.id,
                        "serial_number": dispositivo.serial_number,
                        "applied": "shutdown_manual_off",
                        "ts_local": iso_local(now_utc())
                    })