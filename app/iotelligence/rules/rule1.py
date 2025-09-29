# app/iotelligence/rules/rule1.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta, timezone
import os, json, math, threading, time
from flask import current_app
from app.sse import publish as sse_publish
from app.models import Dispositivo, EstadoLog
from app.iotelligence.rules.base import Rule
from app.utils_time import now_utc, iso_local

# ======== DATA (solo limites.json) ========
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_LIM_PATH = os.path.join(_DATA_DIR, "limites.json")

_LIMITS: Dict[str, Dict[str, Any]] = {}
_LIM_LOADED = False

def _default_limits() -> Dict[str, Dict[str, Dict[str, float]]]:
    return {
        "TMP0": {"temperatura": {"min":18.0,"max":32.0}, "humedad":{"min":20.0,"max":80.0}},
        "CO20": {"co2_ppm": {"min":350,"max":1200}},
        "LUX0": {"luz_lux": {"min":0.0,"max":500.0}},
        "SND0": {"db": {"min":30.0,"max":85.0}},
        "PLG0": {"consumo_w": {"min":0.0,"max":1500.0}},
        "FAN0": {"velocidad": {"min":0,"max":3}}
    }

def _ensure_and_load_limits():
    global _LIM_LOADED
    if _LIM_LOADED: return
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.isfile(_LIM_PATH):
        with open(_LIM_PATH, "w", encoding="utf-8") as f:
            json.dump(_default_limits(), f, ensure_ascii=False, indent=2)
    try:
        with open(_LIM_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _LIMITS.update(data)
        else:
            _LIMITS.update(_default_limits())
    except Exception:
        _LIMITS.update(_default_limits())
    _LIM_LOADED = True

def _limits_for(serial: str) -> Dict[str, Any]:
    for pfx, rules in _LIMITS.items():
        if serial.startswith(pfx): 
            return rules
    return {}

def _bounds_limits(disp: Dispositivo, metric: str) -> Dict[str, Any]:
    mm = _limits_for(disp.serial_number or "").get(metric) or {}
    out: Dict[str, Any] = {}
    if isinstance(mm.get("min"), (int,float)): out["min"] = float(mm["min"])
    if isinstance(mm.get("max"), (int,float)): out["max"] = float(mm["max"])
    if out: out["source"] = "limits"
    return out

# =========================
# Series y percentiles hist
# =========================
def _fetch_series(disp_id: int, metric: str, since, until, limit=5000) -> List[Tuple[datetime, float]]:
    q = EstadoLog.query.filter_by(dispositivo_id=disp_id)
    q = q.filter(EstadoLog.timestamp >= since).filter(EstadoLog.timestamp <= until)
    q = q.order_by(EstadoLog.timestamp.asc())
    out: List[Tuple[datetime, float]] = []
    for log in q.limit(limit).all():
        v = (log.parametros or {}).get(metric)
        if isinstance(v,(int,float)):
            out.append((log.timestamp, float(v)))
    return out

def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals: return math.nan
    k = (len(sorted_vals)-1) * (p/100.0)
    f = math.floor(k); c = math.ceil(k)
    if f == c: return sorted_vals[int(k)]
    return sorted_vals[f]*(c-k) + sorted_vals[c]*(k-f)

def _hist_bounds(series: List[Tuple[datetime,float]]) -> Dict[str, Any]:
    if not series: return {}
    vals = sorted(v for _, v in series)
    pmin = float(current_app.config.get("AI_HIST_PMIN", 1.0))
    pmax = float(current_app.config.get("AI_HIST_PMAX", 99.0))
    lo = _percentile(vals, pmin); hi = _percentile(vals, pmax)
    if math.isnan(lo) or math.isnan(hi) or lo >= hi: return {}
    pad_frac = float(current_app.config.get("AI_HIST_PAD_FRAC", 0.05))
    pad_abs  = float(current_app.config.get("AI_HIST_PAD_ABS", 0.0))
    span = hi - lo
    pad = max(pad_abs, span*pad_frac) if span>0 else pad_abs
    return {"min": lo - pad, "max": hi + pad, "source": "hist"}

# ===============
# Fusión de bounds
# ===============
def _fuse(*bounds_list: Dict[str, Any]) -> Dict[str, Any]:
    mins, maxs, srcs = [], [], []
    for b in bounds_list:
        if not b: continue
        if "min" in b: mins.append(b["min"])
        if "max" in b: maxs.append(b["max"])
        if b.get("source"): srcs.append(b["source"])
    if not mins and not maxs: return {}
    out: Dict[str, Any] = {}
    if mins: out["min"] = max(mins)
    if maxs: out["max"] = min(maxs)
    if srcs: out["source"] = "+".join(srcs)
    return out

# ===============
# Cooldown (antispam)
# ===============
_LOCK = threading.Lock()
_LAST: Dict[tuple[int,str], float] = {}

def _throttle(disp_id: int, metric: str) -> bool:
    cd = int(current_app.config.get("AI_ALERT_COOLDOWN_S", 60))
    now = time.time()
    key = (disp_id, metric)
    with _LOCK:
        last = _LAST.get(key)
        if last and (now - last) < cd:
            return True
        _LAST[key] = now
        return False

# ===============
# Regla 1
# ===============
class Rule1Extremos(Rule):
    name = "extremos"

    def on_measure(self, dispositivo, metric: str, value, ts: datetime) -> None:
        # Solo dispositivos reclamados y métricas numéricas
        if not getattr(dispositivo, "reclamado", False):
            return
        if not isinstance(value, (int,float)):
            return

        _ensure_and_load_limits()
        if _throttle(dispositivo.id, metric):
            return

        # Bounds: limites.json + histórico (si hay suficientes puntos)
        b_lim = _bounds_limits(dispositivo, metric)

        days = int(current_app.config.get("AI_HIST_WINDOW_DAYS", 30))
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=days)
        series = _fetch_series(dispositivo.id, metric, since, until)
        b_hist = {}
        if len(series) >= int(current_app.config.get("AI_HIST_MIN_POINTS", 500)):
            b_hist = _hist_bounds(series)

        bounds = _fuse(b_lim, b_hist) or b_lim or b_hist
        if not bounds:
            return

        mn = bounds.get("min"); mx = bounds.get("max")
        if mn is None and mx is None:
            return

        span = (mx - mn) if (mn is not None and mx is not None and mx>mn) else 0.0
        tol = max(
            float(current_app.config.get("AI_ALERT_TOL_ABS", 0.5)),
            span * float(current_app.config.get("AI_ALERT_TOL_FRAC", 0.02))
        )
        low  = (mn is not None) and (value < (mn - tol))
        high = (mx is not None) and (value > (mx + tol))
        if not (low or high):
            return

        ts_utc = ts or now_utc()
        sse_publish({
            "event":"ai_anomaly","rule":self.name,
            "dispositivo_id":dispositivo.id,
            "serial_number":dispositivo.serial_number,
            "metric":metric,"value":value,"bounds":bounds,
            "ts_local": iso_local(ts_utc), # hora local
            "ts_utc": ts_utc.isoformat()    # hora UTC
        })

    def run_batch(self, dispositivo, metric: str, days: int = 7):
        """
        Recorre el histórico de 'days' días, calcula bounds fusionados y
        emite ai_anomaly por cada valor fuera de rango. Al final emite ai_done.
        """
        if not getattr(dispositivo, "reclamado", False):
            sse_publish({
                "event": "ai_done",
                "rule": self.name,
                "result": {"metric": metric, "window_days": days, "found": 0, "skipped": "unclaimed"}
            })
            return {"found": 0, "skipped": "unclaimed"}

        _ensure_and_load_limits()

        b_lim = _bounds_limits(dispositivo, metric)

        until = datetime.now(timezone.utc)
        since = until - timedelta(days=int(days))
        series = _fetch_series(dispositivo.id, metric, since, until)

        b_hist = {}
        if len(series) >= int(current_app.config.get("AI_HIST_MIN_POINTS", 500)):
            b_hist = _hist_bounds(series)

        bounds = _fuse(b_lim, b_hist) or b_lim or b_hist
        if not bounds:
            sse_publish({
                "event": "ai_done",
                "rule": self.name,
                "result": {"metric": metric, "window_days": days, "found": 0, "reason": "no_bounds"}
            })
            return {"found": 0, "reason": "no_bounds"}

        mn = bounds.get("min"); mx = bounds.get("max")
        span = (mx - mn) if (mn is not None and mx is not None and mx > mn) else 0.0
        tol = max(
            float(current_app.config.get("AI_ALERT_TOL_ABS", 0.5)),
            span * float(current_app.config.get("AI_ALERT_TOL_FRAC", 0.02))
        )

        found = 0
        for ts, val in series:
            if not isinstance(val, (int, float)):
                continue
            low  = (mn is not None) and (val < (mn - tol))
            high = (mx is not None) and (val > (mx + tol))
            if not (low or high):
                continue
            found += 1

            ts_utc = ts or now_utc()

            sse_publish({
                "event": "ai_anomaly",
                "rule": self.name,
                "dispositivo_id": dispositivo.id,
                "serial_number": dispositivo.serial_number,
                "metric": metric,
                "value": val,
                "bounds": bounds,
                "ts_local": iso_local(ts_utc), # hora local
                "ts_utc": ts_utc.isoformat()    # hora UTC
            })

        sse_publish({
            "event": "ai_done",
            "rule": self.name,
            "result": {"metric": metric, "window_days": days, "found": found}
        })
        return {"found": found, "metric": metric, "window_days": days}