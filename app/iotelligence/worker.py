# app/iotelligence/worker.py
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any
from flask import Flask

_executor: ThreadPoolExecutor | None = None
_app: Flask | None = None

def init(app: Flask, max_workers: int = 2) -> None:
    global _executor, _app
    _app = app
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AIWorker")
        print(f"[AI worker] started (max_workers={max_workers})")

def _run_with_app(fn: Callable[..., Any], *args, **kwargs) -> Any:
    if _app is None:
        return fn(*args, **kwargs)
    with _app.app_context():
        return fn(*args, **kwargs)

def submit(fn: Callable[..., Any], *args, **kwargs):
    if _executor is None:
        raise RuntimeError("AI worker no inicializado. Llama init(app) en create_app().")
    return _executor.submit(_run_with_app, fn, *args, **kwargs)