# app/iotelligence/routes.py
from __future__ import annotations
from flask import Blueprint, request, jsonify, Response, stream_with_context
from queue import Empty
import json, time

from app.models import Dispositivo
from app.iotelligence.core import run_rule_batch      # <<< runner de reglas (concurrencia)
from app.sse import publish as sse_publish, subscribe, unsubscribe
from app.utils_time import now_utc, iso_local         # <<< AÑADIR

bp_ai = Blueprint("iotelligence", __name__)

@bp_ai.route("/ai/anomaly", methods=["POST"])
def ai_anomaly():
    """
    Lanza un análisis batch de Regla 1 (valores extremos) sobre una métrica histórica.
    Body:
      { "dispositivo_id": 1, "metric": "temperatura", "days": 7 }
    Respuesta inmediata: {"status":"queued"}
    Los hallazgos se publican por SSE en /stream/ai (eventos: ai_anomaly, ai_done).
    """
    data = request.get_json() or {}
    dispositivo_id = int(data.get("dispositivo_id", 0))
    metric = data.get("metric", "temperatura")
    days = int(data.get("days", 7))

    disp = Dispositivo.query.get(dispositivo_id)
    if not disp:
        return jsonify({"error": "dispositivo no existe"}), 404

    # Aviso de que se encoló el job (con timestamps local/UTC)
    ts_utc = now_utc()                                   # <<< NUEVO
    sse_publish({
        "event": "ai_progress",
        "status": "queued",
        "rule": "extremos",
        "dispositivo_id": dispositivo_id,
        "metric": metric,
        "window_days": days,
        "ts_local": iso_local(ts_utc),                   # <<< NUEVO
        "ts_utc": ts_utc.isoformat()                     # <<< NUEVO
    })

    # Ejecuta la Regla 1 en batch (histórico) en background
    run_rule_batch("extremos", dispositivo=disp, metric=metric, days=days)

    return jsonify({"status": "queued"}), 202


@bp_ai.route("/stream/ai", methods=["GET"])
def stream_ai():
    """
    SSE para eventos de IA:
      - ai_anomaly     (hallazgos)
      - ai_misconfig   (regla 2)
      - ai_fix_applied (si aplicas parches)
      - ai_done        (fin de job batch)
      - ai_progress    (progreso encolado)
    """
    def gen():
        q = subscribe()
        try:
            yield "event: hello\ndata: {}\n\n"
            last = time.time()
            while True:
                try:
                    evt = q.get(timeout=5)
                    # Solo eventos IA
                    if isinstance(evt, dict) and str(evt.get("event", "")).startswith("ai_"):
                        payload = json.dumps(evt, ensure_ascii=False, separators=(',', ':'))
                        yield f"data: {payload}\n\n"
                except Empty:
                    # keep-alive
                    if time.time() - last > 25:
                        yield "event: ping\ndata: {}\n\n"
                        last = time.time()
        finally:
            unsubscribe(q)

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(gen()), headers=headers)