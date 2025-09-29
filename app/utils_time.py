# app/utils_time.py
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import current_app

def tz() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("BACKEND_TZ", "America/Caracas"))

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def now_local() -> datetime:
    return now_utc().astimezone(tz())

def to_local(dt: datetime) -> datetime:
    # Acepta naive o tz-aware; devuelve aware en BACKEND_TZ
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz())

def iso_local(dt: datetime) -> str:
    return to_local(dt).isoformat()