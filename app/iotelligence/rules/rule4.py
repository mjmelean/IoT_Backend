from __future__ import annotations
from typing import Dict, Optional
import time, threading
from datetime import datetime, timezone          # <-- añade timezone
from flask import current_app

from app.iotelligence.rules.base import Rule
from app.sse import publish as sse_publish
from app.models import Dispositivo
from app.utils_time import now_utc, iso_local

_LAST_SEEN: Dict[int, float]     = {}
_OFFLINE_SINCE: Dict[int, float] = {}
_LAST_ALERT: Dict[int, float]    = {}
_WATCHDOG_STARTED = False
_WATCHDOG_LOCK = threading.Lock()

def _publish_offline(d: Dispositivo, *, since_epoch: float, now_epoch: float):
    payload = {
        "event": "ai_offline",
        "rule": "offline",
        "dispositivo_id": d.id,
        "serial_number": d.serial_number,
        "seconds_offline": int(now_epoch - since_epoch),
        # usa UTC explícito para iso_local
        "since_ts_local": iso_local(datetime.fromtimestamp(since_epoch, tz=timezone.utc)),
        "ts_local": iso_local(now_utc()),
        "severity": "medium"
    }
    sse_publish(payload)

def _publish_back_online(d: Dispositivo, *, was_offline_secs: int):
    payload = {
        "event": "ai_back_online",
        "rule": "offline",
        "dispositivo_id": d.id,
        "serial_number": d.serial_number,
        "was_offline_secs": was_offline_secs,
        "ts_local": iso_local(now_utc()),
        "severity": "info"
    }
    sse_publish(payload)

def _watchdog_loop(app):
    """Hilo de fondo: requiere app context para consultas a la DB."""
    with app.app_context():
        tick = int(current_app.config.get("AI_R4_WATCHDOG_TICK_SECS", 10))
        offline_secs = int(current_app.config.get("AI_R4_OFFLINE_SECS", 60))
        remind_secs  = int(current_app.config.get("AI_R4_REMIND_SECS", 900))
        startup_grace = int(current_app.config.get("AI_R4_STARTUP_GRACE_SECS", 30))

        start_epoch = time.time()
        while True:
            try:
                now = time.time()

                if now - start_epoch < startup_grace:
                    time.sleep(tick)
                    continue

                for disp_id, last in list(_LAST_SEEN.items()):
                    d = Dispositivo.query.get(disp_id)
                    if not d or not getattr(d, "reclamado", False):
                        continue

                    elapsed = now - last
                    if elapsed >= offline_secs:
                        if disp_id not in _OFFLINE_SINCE:
                            _OFFLINE_SINCE[disp_id] = last
                            _publish_offline(d, since_epoch=last, now_epoch=now)
                            _LAST_ALERT[disp_id] = now
                        elif remind_secs > 0 and (now - _LAST_ALERT.get(disp_id, 0.0)) >= remind_secs:
                            _publish_offline(d, since_epoch=_OFFLINE_SINCE[disp_id], now_epoch=now)
                            _LAST_ALERT[disp_id] = now
                    else:
                        if disp_id in _OFFLINE_SINCE:
                            was_offline = int(now - _OFFLINE_SINCE.get(disp_id, now))
                            _publish_back_online(d, was_offline_secs=was_offline)
                            _OFFLINE_SINCE.pop(disp_id, None)
                            _LAST_ALERT.pop(disp_id, None)

            except Exception:
                # no romper el loop si algo falla
                pass
            time.sleep(tick)

def _ensure_watchdog_started():
    global _WATCHDOG_STARTED
    if _WATCHDOG_STARTED:
        return
    with _WATCHDOG_LOCK:
        if _WATCHDOG_STARTED:
            return
        # toma el objeto app real y pásalo al hilo
        app_obj = current_app._get_current_object()
        t = threading.Thread(target=_watchdog_loop, args=(app_obj,), name="rule4_watchdog", daemon=True)
        t.start()
        _WATCHDOG_STARTED = True

class Rule4OfflineWatchdog(Rule):
    name = "offline"

    def applies_realtime(self, disp, metric, value) -> bool:
        return getattr(disp, "reclamado", False)

    def on_measure(self, dispositivo: Dispositivo, metric: str, value, ts: datetime) -> None:
        if not getattr(dispositivo, "reclamado", False):
            return
        _ensure_watchdog_started()
        _LAST_SEEN[dispositivo.id] = time.time()