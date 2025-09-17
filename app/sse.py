# app/sse.py
import json
from queue import Queue, Full
from threading import Lock

_subs = set()
_lock = Lock()

def subscribe():
    q = Queue(maxsize=100)
    with _lock: _subs.add(q)
    return q

def unsubscribe(q):
    with _lock: _subs.discard(q)

def publish(event: dict):
    dead = []
    with _lock:
        for q in list(_subs):
            try: q.put_nowait(event)
            except Full: dead.append(q)
        for q in dead: _subs.discard(q)
