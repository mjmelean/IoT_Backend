# app/iotelligence/rules/base.py
from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime

class Rule:
    name: str = "rule"

    def on_measure(self, dispositivo, metric: str, value, ts: datetime) -> None:
        """Procesa una sola medición (tiempo real)."""
        return

    def run_batch(self, **kwargs) -> Optional[Dict[str, Any]]:
        """Procesa en modo histórico/batch."""
        return None