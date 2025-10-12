# app/sse.py
import json
from queue import Queue, Full
from threading import Lock
from typing import Dict, Any

_SUB_CAPACITY = 200  # un poco más holgado que 100
_subs = set()
_lock = Lock()

def subscribe() -> Queue:
    q = Queue(maxsize=_SUB_CAPACITY)
    with _lock:
        _subs.add(q)
        try:
            print(f"[SSE] +subscribe -> subs={len(_subs)}")
        except Exception:
            pass
    return q

def unsubscribe(q: Queue) -> None:
    with _lock:
        _subs.discard(q)
        try:
            print(f"[SSE] -unsubscribe -> subs={len(_subs)}")
        except Exception:
            pass

def _safe_payload(evt: Dict[str, Any]) -> Dict[str, Any]:
    """
    Devuelve una copia 'segura' para logging / SSE:
    - Convierte objetos no-serializables a str
    - Limita tamaño de campos muy grandes
    """
    out: Dict[str, Any] = {}
    for k, v in (evt or {}).items():
        try:
            json.dumps({k: v})
            out[k] = v
        except Exception:
            out[k] = str(v)
        # recorte opcional de mensajes enormes
        if isinstance(out[k], str) and len(out[k]) > 2000:
            out[k] = out[k][:2000] + "…"
    return out

def publish(event: Dict[str, Any]) -> None:
    if not isinstance(event, dict):
        try:
            print(f"[SSE] WARN publish non-dict: {type(event)} -> {event}")
        except Exception:
            pass
        return

    evt = _safe_payload(event)
    name = str(evt.get("event", "unknown"))
    dead = []

    with _lock:
        # Log básico de publicación (una vez por publish)
        try:
            print(f"[SSE] publish event={name} to {len(_subs)} subs | keys={list(evt.keys())}")
        except Exception:
            pass

        for q in list(_subs):
            try:
                q.put_nowait(evt)
            except Full:
                dead.append(q)

        for q in dead:
            _subs.discard(q)
        if dead:
            try:
                print(f"[SSE] dropped {len(dead)} slow subscriber(s); subs={len(_subs)}")
            except Exception:
                pass