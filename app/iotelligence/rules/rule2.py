# app/iotelligence/rules/rule2.py
from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime
import os, json, threading, time
from flask import current_app
from app.sse import publish as sse_publish
from app.models import Dispositivo
from app.iotelligence.rules.base import Rule
from app.utils_time import now_utc, iso_local

# ========= CARGA DE estandar.json (solo modo + intervalo + cooldown) =========
_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
_STD_PATH = os.path.join(_DATA_DIR, "estandar.json")

# Simplificado: expected_modo, límites de intervalo_envio y cooldown por prefijo
_DEFAULT_STD: Dict[str, Dict[str, Any]] = {
    "LGT0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600},
    "RGD0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600},
    "SHD0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600},
    "FAN0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600},
    "PLG0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600},
    "MOV0": {"expected_modo": "horario", "intervalo_min_s": 1, "intervalo_max_s": 3600, "misconfig_cooldown_s": 3600}
}

_STD: Dict[str, Dict[str, Any]] = {}
_STD_LOADED = False

def _ensure_and_load_std():
    global _STD_LOADED
    if _STD_LOADED:
        return
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.isfile(_STD_PATH):
        with open(_STD_PATH, "w", encoding="utf-8") as f:
            json.dump(_DEFAULT_STD, f, ensure_ascii=False, indent=2)
    try:
        with open(_STD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _STD.update(data)
        else:
            _STD.update(_DEFAULT_STD)
    except Exception:
        _STD.update(_DEFAULT_STD)
    _STD_LOADED = True

def _std_for(serial: str) -> Optional[Dict[str, Any]]:
    for pfx, rules in _STD.items():
        if serial.startswith(pfx):
            return rules
    return None

# ========= ESTADO EN MEMORIA + COOLDOWN =========
_STATE_LOCK = threading.Lock()
_MISCONFIG_STATE: Dict[int, bool] = {}   # True si está en misconfig; False/None si OK
_LAST_NOTIFY_TS: Dict[int, float] = {}   # última notificación por dispositivo (epoch)

def _cooldown_seconds_default() -> int:
    """Cooldown global por config; fallback 3600s."""
    try:
        return int(current_app.config.get("AI_MISCONFIG_COOLDOWN_S", 3600))
    except Exception:
        return 3600

def _cooldown_seconds_for(disp: Dispositivo) -> int:
    """
    Si el estandar del prefijo define 'misconfig_cooldown_s', lo usa.
    Si no, usa el global AI_MISCONFIG_COOLDOWN_S.
    """
    try:
        std = _std_for(disp.serial_number or "")
        if std and isinstance(std.get("misconfig_cooldown_s"), (int, float)):
            return int(std["misconfig_cooldown_s"])
    except Exception:
        pass
    return _cooldown_seconds_default()

def _should_notify(disp_id: int, new_state_is_misconfig: bool, cooldown_s: int) -> bool:
    """
    Notifica SOLO en transición OK -> MISCONFIG y respetando cooldown_s.
    Si permanece en MISCONFIG, no repite hasta que pase el cooldown.
    Al volver a OK, se resetea y podrá volver a notificar.
    """
    now = time.time()
    cd = int(cooldown_s)
    with _STATE_LOCK:
        prev_state = _MISCONFIG_STATE.get(disp_id, False)
        last_ts = _LAST_NOTIFY_TS.get(disp_id, 0.0)

        if new_state_is_misconfig and not prev_state:
            if now - last_ts >= cd:
                _MISCONFIG_STATE[disp_id] = True
                _LAST_NOTIFY_TS[disp_id] = now
                return True
            _MISCONFIG_STATE[disp_id] = True
            return False
        elif not new_state_is_misconfig and prev_state:
            _MISCONFIG_STATE[disp_id] = False
            return False
        else:
            return False

# ========= LÓGICA DE EVALUACIÓN (solo modo + intervalo_envio) =========
def _evaluate(dispositivo: Dispositivo) -> Dict[str, Any]:
    """
    Devuelve {"issues":[...], "patch":{...}, "severity":"low"} o {} si OK.
    - Solo dispositivos RECLAMADOS (el caller ya filtra).
    - Solo evalúa configuracion: 'modo' y 'intervalo_envio'.
    """
    _ensure_and_load_std()

    cfg = dispositivo.configuracion or {}
    std = _std_for(dispositivo.serial_number or "")
    if not std:
        return {}

    issues = []
    patch_cfg: Dict[str, Any] = {}

    # 1) modo esperado = "horario"
    expected_modo = str(std.get("expected_modo", "")).lower()
    modo = str(cfg.get("modo", "")).lower()
    if expected_modo and modo != expected_modo:
        issues.append(f"config.modo = '{modo or 'N/A'}' → se recomienda '{expected_modo}'")
        patch_cfg["modo"] = expected_modo

    # 2) intervalo_envio dentro de [min,max]
    try:
        intervalo = int(cfg.get("intervalo_envio", 0))
    except Exception:
        intervalo = 0  # fuerza a entrar al ajuste

    min_s = int(std.get("intervalo_min_s", 1))
    max_s = int(std.get("intervalo_max_s", 3600))
    if intervalo < min_s or intervalo > max_s:
        issues.append(f"config.intervalo_envio fuera de rango [{min_s},{max_s}]")
        # sugerimos ajustar al rango sin inventar un valor fijo externo
        patch_cfg["intervalo_envio"] = max(min(intervalo or min_s, max_s), min_s)

    if not issues:
        return {}

    return {
        "issues": issues,
        "patch": {"configuracion": patch_cfg} if patch_cfg else {},
        "severity": "low"
    }

# ========= RULE 2 =========
class Rule2Misconfig(Rule):
    name = "misconfig"

    def applies_realtime(self, disp, metric, value) -> bool:
        # Aplica a dispositivos reclamados; no depende de métricas.
        return getattr(disp, "reclamado", False)

    def on_measure(self, dispositivo: Dispositivo, metric: str, value, ts: datetime) -> None:
        if not getattr(dispositivo, "reclamado", False):
            return

        res = _evaluate(dispositivo)
        is_misconfig = bool(res)
        cd = _cooldown_seconds_for(dispositivo)

        if _should_notify(dispositivo.id, is_misconfig, cd) and is_misconfig:
            ts_utc = ts or now_utc()
            sse_publish({
                "event": "ai_misconfig",
                "rule": self.name,
                "dispositivo_id": dispositivo.id,
                "serial_number": dispositivo.serial_number,
                "issues": res.get("issues", []),
                "suggested_patch": res.get("patch", {}),
                "severity": res.get("severity", "low"),
                "ts_local": iso_local(ts_utc),
                "ts_utc": ts_utc.isoformat()
            })

    def run_batch(self, dispositivo: Dispositivo, **kwargs):
        if not getattr(dispositivo, "reclamado", False):
            return {"skipped": "unclaimed"}

        res = _evaluate(dispositivo)
        is_misconfig = bool(res)
        cd = _cooldown_seconds_for(dispositivo)

        if _should_notify(dispositivo.id, is_misconfig, cd) and is_misconfig:
            ts_utc = now_utc()
            sse_publish({
                "event": "ai_misconfig",
                "rule": self.name,
                "dispositivo_id": dispositivo.id,
                "serial_number": dispositivo.serial_number,
                "issues": res.get("issues", []),
                "suggested_patch": res.get("patch", {}),
                "severity": res.get("severity", "low"),
                "ts_local": iso_local(ts_utc),
                "ts_utc": ts_utc.isoformat()
            })
        return {"misconfig": is_misconfig}