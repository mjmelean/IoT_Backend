# app/iotelligence/core.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from app.iotelligence.worker import submit           # 👈 solo submit (NO init aquí)
from app.iotelligence.rules import REGISTRY
from app.models import Dispositivo

def dispatch_measure(dispositivo: Dispositivo, metric: str | None, value, ts: Optional[datetime] = None):
    """
    Router para eventos en tiempo real (MQTT/PUT).
    - metric puede ser None para reglas de configuración (Rule 2).
    """
    ts = ts or datetime.now(timezone.utc)
    for rule in REGISTRY.values():
        submit(rule.on_measure, dispositivo, metric, value, ts)

def run_rule_batch(rule_name: str, **kwargs):
    """
    Encola la ejecución batch de una regla (histórico / auditorías).
    El worker ya fue inicializado en app/__init__.py.
    """
    rule = REGISTRY.get(rule_name)
    if not rule:
        raise ValueError(f"Regla no registrada: {rule_name}")
    return submit(rule.run_batch, **kwargs)