from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import os, time, pickle
from flask import current_app

from app.iotelligence.rules.base import Rule
from app.sse import publish as sse_publish
from app.models import Dispositivo
from app.utils_time import now_utc, iso_local, to_local

# ---- River (IA online) ----
from river import linear_model, optim, compose, preprocessing

# ===== Persistencia de modelos por dispositivo (PICKLE) =====
def _model_dir() -> str:
    base = current_app.config.get("AI_R3_MODEL_DIR", "app/iotelligence/data/river_models")
    os.makedirs(base, exist_ok=True)
    return base

def _model_path(serial: str) -> str:
    safe = "".join(ch for ch in (serial or "unknown") if ch.isalnum() or ch in ("-","_"))
    return os.path.join(_model_dir(), f"{safe}.river.pkl")

def _new_model():
    return compose.Pipeline(
        ("scale", preprocessing.StandardScaler()),
        ("lr", linear_model.LogisticRegression(optimizer=optim.SGD(0.05)))
    )

def _load_model(serial: str):
    path = _model_path(serial)
    warm = bool(current_app.config.get("AI_R3_WARM_START", True))
    if warm and os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return _new_model()

def _save_model(serial: str, model):
    try:
        with open(_model_path(serial), "wb") as f:
            pickle.dump(model, f)
    except Exception:
        pass

# ===== Features de tiempo =====
def _time_features(ts_utc: datetime) -> Dict[str, Any]:
    loc = to_local(ts_utc)
    return {
        "hora": loc.hour,
        "minuto": loc.minute,
        "dia_semana": loc.weekday(),        # 0=Lunes .. 6=Domingo
        "es_fin_semana": 1 if loc.weekday() >= 5 else 0
    }

def _features_for_bin(bin_idx: int, weekday: int) -> Dict[str, Any]:
    step = int(current_app.config.get("AI_R3_BIN_MINUTES", 15))
    start_min = bin_idx * step
    mid_min = start_min + step//2
    h = mid_min // 60
    m = mid_min % 60
    return {
        "hora": h,
        "minuto": m,
        "dia_semana": weekday,
        "es_fin_semana": 1 if weekday >= 5 else 0
    }

# ===== Construcción de ventanas desde máscaras =====
def _bin_edges(step_min: int) -> List[Tuple[int, int]]:
    edges = []
    total = 24*60
    for start in range(0, total, step_min):
        edges.append((start, min(start+step_min, total)))
    return edges

def _merge_on_windows(mask: List[bool], step_min: int, min_bins: int) -> List[Tuple[str, str]]:
    def mm_to_hhmm(mm: int) -> str:
        mm = max(0, min(1440, mm))
        return f"{mm//60:02d}:{mm%60:02d}"

    edges = _bin_edges(step_min)
    windows = []
    i = 0
    n = len(mask)
    while i < n:
        if not mask[i]:
            i += 1; continue
        j = i
        while j < n and mask[j]:
            j += 1
        length = j - i
        if length >= min_bins:
            start_min = edges[i][0]
            end_min   = edges[j-1][1]
            windows.append((mm_to_hhmm(start_min), mm_to_hhmm(end_min)))
        i = j
    return windows

def _hhmm_to_mm(s: str) -> Optional[int]:
    try:
        h, m = s.split(":")
        h = int(h); m = int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h*60 + m
    except Exception:
        pass
    return None

def _round_down(mm: int, step: int) -> int:
    return max(0, (mm // step) * step)

def _round_up(mm: int, step: int) -> int:
    return min(1440, ((mm + step - 1) // step) * step)

def _windows_postprocess(
    wins: List[Tuple[str, str]],
    *,
    step_min: int,
    min_gap_bins: int = 0,
    round_to_min: int = 0,
    max_windows_per_day: int = 0
) -> List[Dict[str, str]]:
    if not wins:
        return []

    # a minutos y ordenado
    segs = []
    for a, b in wins:
        aa = _hhmm_to_mm(a); bb = _hhmm_to_mm(b)
        if aa is None or bb is None or bb <= aa: 
            continue
        segs.append([aa, bb])
    if not segs: 
        return []
    segs.sort(key=lambda t: t[0])

    # fusiona huecos pequeños
    merged = []
    gap_min = max(0, min_gap_bins) * step_min
    for aa, bb in segs:
        if not merged:
            merged.append([aa, bb]); continue
        pa, pb = merged[-1]
        if aa - pb <= gap_min:
            merged[-1][1] = max(pb, bb)
        else:
            merged.append([aa, bb])

    # redondeo
    round_to_min = int(round_to_min or 0)
    if round_to_min > 1:
        rounded = []
        for aa, bb in merged:
            ra = _round_down(aa, round_to_min)
            rb = _round_up(bb, round_to_min)
            if rb > ra: rounded.append([ra, rb])
    else:
        rounded = merged

    # re-fusiona solapadas
    rounded.sort(key=lambda t: t[0])
    fused = []
    for aa, bb in rounded:
        if not fused: fused.append([aa, bb]); continue
        pa, pb = fused[-1]
        if aa <= pb: fused[-1][1] = max(pb, bb)
        else:        fused.append([aa, bb])

    # limita por duración (top ventanas)
    if max_windows_per_day and max_windows_per_day > 0:
        fused.sort(key=lambda t: (t[1]-t[0]), reverse=True)
        fused = fused[:max_windows_per_day]
        fused.sort(key=lambda t: t[0])

    return [{"inicio": f"{a//60:02d}:{a%60:02d}", "fin": f"{b//60:02d}:{b%60:02d}"} for a, b in fused if b > a]

# ===== Horario actual -> máscara =====
_DIAS = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]

def _parse_hhmm(s: str) -> Optional[int]:
    try:
        h, m = s.strip().split(":")
        h = int(h); m = int(m)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h*60 + m
    except Exception:
        pass
    return None

def _current_schedule_masks(cfg: Dict[str, Any], step_min: int) -> Dict[int, List[bool]]:
    horarios = cfg.get("horarios")
    if not isinstance(horarios, list) or not horarios:
        return {}
    bins = 24*60 // step_min
    masks: Dict[int, List[bool]] = {wd: [False]*bins for wd in range(7)}
    for item in horarios:
        if not isinstance(item, dict): continue
        dias = item.get("dias")
        ini = _parse_hhmm(str(item.get("inicio", "")))
        fin = _parse_hhmm(str(item.get("fin", "")))
        if not isinstance(dias, list) or ini is None or fin is None:
            continue
        ranges = []
        if fin >= ini:
            ranges.append((ini, fin))
        else:
            ranges.append((ini, 1440))
            ranges.append((0, fin))
        for dname in dias:
            dname_l = str(dname).lower()
            if dname_l not in _DIAS: continue
            wd = _DIAS.index(dname_l)
            for a, b in ranges:
                start_bin = a // step_min
                end_bin_excl = min((b + step_min - 1) // step_min, bins)
                for bi in range(start_bin, end_bin_excl):
                    masks[wd][bi] = True
    return {wd: m for wd, m in masks.items() if any(m)}

# ===== Máscaras “aprendidas” =====
def _learned_masks(model, step_min: int, thresh: float) -> Dict[int, List[bool]]:
    bins = 24*60 // step_min
    out: Dict[int, List[bool]] = {}
    for wd in range(7):
        mask = []
        for b in range(bins):
            xf = _features_for_bin(b, wd)
            try:
                p_on = float(model.predict_proba_one(xf).get(True, 0.0))
            except Exception:
                p_on = 0.0
            mask.append(p_on > thresh)  # '>' evita “todo ON” cuando p≈umbral
        if any(mask):
            out[wd] = mask
    return out

def _diff_ratio(m1: Dict[int, List[bool]], m2: Dict[int, List[bool]]) -> float:
    union = xor = 0
    for wd in range(7):
        a = m1.get(wd, []); b = m2.get(wd, [])
        n = max(len(a), len(b))
        if n == 0: continue
        aa = a + [False]*(n - len(a))
        bb = b + [False]*(n - len(b))
        for i in range(n):
            u = aa[i] or bb[i]
            x = (aa[i] != bb[i])
            if u: union += 1
            if x: xor += 1
    return 0.0 if union == 0 else (xor / float(union))

def _masks_equalish(a: Dict[int, List[bool]], b: Dict[int, List[bool]], min_diff: float) -> bool:
    return _diff_ratio(a or {}, b or {}) < float(min_diff or 0.0)

def _masks_to_windows_per_day(masks: Dict[int, List[bool]], step_min: int, min_bins: int) -> Dict[str, List[Dict[str,str]]]:
    min_gap_bins = int(current_app.config.get("AI_R3_MIN_GAP_BINS", 0))
    round_to_min = int(current_app.config.get("AI_R3_ROUND_TO_MIN", 0))
    max_per_day  = int(current_app.config.get("AI_R3_MAX_WINDOWS_PER_DAY", 0))
    out: Dict[str, List[Dict[str,str]]] = {}
    for wd, mask in masks.items():
        raw_wins = _merge_on_windows(mask, step_min, min_bins)
        if raw_wins:
            out[_DIAS[wd]] = _windows_postprocess(
                raw_wins,
                step_min=step_min,
                min_gap_bins=min_gap_bins,
                round_to_min=round_to_min,
                max_windows_per_day=max_per_day
            )
    return out

# ===== DEMO helpers =====
def _csv_path_for_demo(serial: str) -> Optional[str]:
    base = str(current_app.config.get("AI_R3_DEMO_CSV_DIR", "prepared_models"))
    for ext in (".csv", ".csvs"):
        p = os.path.join(base, f"{serial}{ext}")
        if os.path.isfile(p):
            return p
    return None

def _hist_masks_from_csv(csv_path: str, step_min: int, thresh: float, topk: int = 0) -> Dict[int, List[bool]]:
    import csv
    from datetime import datetime
    bins = 24*60 // step_min
    on_counts  = {wd: [0]*bins for wd in range(7)}
    tot_counts = {wd: [0]*bins for wd in range(7)}

    def parse_ts(s: str) -> Optional[datetime]:
        s = (s or "").strip()
        if not s: return None
        try: return datetime.fromisoformat(s.replace("Z",""))
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try: return datetime.strptime(s, fmt)
                except Exception: continue
        return None

    def parse_y(row) -> Optional[int]:
        for k in ("encendido","estado"):
            if k in row and row[k] != "":
                v = str(row[k]).strip().lower()
                if v in ("1","true","on","activo","yes","y"):  return 1
                if v in ("0","false","off","inactivo","no","n"): return 0
        return None

    with open(csv_path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            dt = parse_ts(r.get("timestamp",""))
            y  = parse_y(r)
            if dt is None or y is None: continue
            wd = dt.weekday()
            mm = dt.hour*60 + dt.minute
            b  = min(bins-1, max(0, (mm // step_min)))
            on_counts[wd][b]  += (1 if y else 0)
            tot_counts[wd][b] += 1

    masks: Dict[int, List[bool]] = {}
    for wd in range(7):
        frac = [(on_counts[wd][b] / tot_counts[wd][b]) if tot_counts[wd][b] > 0 else 0.0 for b in range(bins)]
        if topk and topk > 0:
            idx = sorted(range(bins), key=lambda i: frac[i], reverse=True)[:topk]
            mask = [False]*bins
            for i in idx:
                if frac[i] > 0: mask[i] = True
        else:
            mask = [f > thresh for f in frac]
        if any(mask): masks[wd] = mask
    return masks

def _hist_masks_from_model(model, step_min: int, thresh: float, topk: int = 0) -> Dict[int, List[bool]]:
    bins = 24*60 // step_min
    masks: Dict[int, List[bool]] = {}
    for wd in range(7):
        scores = []
        for b in range(bins):
            xf = _features_for_bin(b, wd)
            try:
                p = float(model.predict_proba_one(xf).get(True, 0.0))
            except Exception:
                p = 0.0
            scores.append(p)
        if topk and topk > 0:
            idx = sorted(range(bins), key=lambda i: scores[i], reverse=True)[:topk]
            mask = [False]*bins
            for i in idx:
                if scores[i] > 0: mask[i] = True
        else:
            mask = [p > thresh for p in scores]
        if any(mask): masks[wd] = mask
    return masks

# ===== Estado en memoria =====
_UPDATE_COUNT: Dict[int, int] = {}
_TOTAL_EVENTS: Dict[int, int] = {}
_LAST_SUGGEST_TS: Dict[int, float] = {}
_RESET_DONE: Dict[str, bool] = {}
_LAST_MASKS: Dict[int, Dict[int, List[bool]]] = {}   # hysteresis

def _maybe_reset_model_once(serial: str):
    if not bool(current_app.config.get("AI_R3_RESET_ON_START", False)):
        return
    if _RESET_DONE.get(serial):
        return
    path = _model_path(serial)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
    _RESET_DONE[serial] = True

def _should_emit_suggest(disp_id: int) -> bool:
    cd = int(current_app.config.get("AI_R3_COOLDOWN_S", 3600))
    min_events = int(current_app.config.get("AI_R3_MIN_EVENTS", 100))
    last = _LAST_SUGGEST_TS.get(disp_id, 0.0)
    now = time.time()
    if _TOTAL_EVENTS.get(disp_id, 0) < min_events:
        return False
    if now - last < cd:
        return False
    return True

def _maybe_save_model(serial: str, disp_id: int, model):
    n = int(current_app.config.get("AI_R3_SAVE_EVERY_N", 50))
    cnt = _UPDATE_COUNT.get(disp_id, 0)
    if cnt >= n:
        _save_model(serial, model)
        _UPDATE_COUNT[disp_id] = 0

def _emit_suggestion(
    dispositivo: Dispositivo,
    model,
    *,
    current_masks: Optional[Dict[int, List[bool]]] = None,
    diff_ratio_val: Optional[float] = None,
    rule_name: str = "learn",
    learned_masks_override: Optional[Dict[int, List[bool]]] = None
):
    step = int(current_app.config.get("AI_R3_BIN_MINUTES", 15))
    thresh = float(current_app.config.get("AI_R3_PROB_THRESH", 0.60))
    min_bins = int(current_app.config.get("AI_R3_MIN_SPAN_BINS", 2))

    learned_masks = learned_masks_override if learned_masks_override is not None else _learned_masks(model, step, thresh)
    suggested_horarios = _masks_to_windows_per_day(learned_masks, step, min_bins)

    payload = {
        "event": "ai_suggest",
        "rule": rule_name,
        "dispositivo_id": dispositivo.id,
        "serial_number": dispositivo.serial_number,
        "suggested_horarios": suggested_horarios,
        "bin_minutes": step,
        "threshold": thresh,
        "ts_local": iso_local(now_utc()),
    }
    if current_masks is not None:
        payload["current_horarios"] = _masks_to_windows_per_day(current_masks, step, min_bins)
    if diff_ratio_val is not None:
        payload["diff_ratio"] = diff_ratio_val

    sse_publish(payload)
    _LAST_SUGGEST_TS[dispositivo.id] = time.time()

# ===== Regla =====
class Rule3LearnSchedule(Rule):
    name = "learn"

    def applies_realtime(self, disp, metric, value) -> bool:
        return True

    def _target_from_dispositivo(self, dispositivo: Dispositivo) -> Optional[int]:
        cfg = dispositivo.configuracion or {}
        if isinstance(cfg.get("encendido"), bool):
            return 1 if cfg["encendido"] else 0
        st = str(dispositivo.estado or "").lower()
        if st in ("activo", "on", "true", "1"):     return 1
        if st in ("inactivo", "off", "false", "0"): return 0
        return None

    def on_measure(self, dispositivo: Dispositivo, metric: str, value, ts: datetime) -> None:
        if not getattr(dispositivo, "reclamado", False):
            return

        serial = dispositivo.serial_number or ""
        _maybe_reset_model_once(serial)

        cfg   = dispositivo.configuracion or {}
        modo  = str(cfg.get("modo", "")).lower()

        # Cargamos/creamos modelo (sirve en demo y en real)
        model = _load_model(serial)

        # ===================== MODO DEMO =====================
        if bool(current_app.config.get("AI_R3_DEMO_MODE", False)):
            # --- DEMO GUARD: limitar a tipos/serials y exigir archivo si se pide ---
            demo_tipos   = [str(t).lower() for t in (current_app.config.get("AI_R3_DEMO_TIPOS", []) or [])]
            demo_serials = set(current_app.config.get("AI_R3_DEMO_SERIALS", []) or [])
            require_file = bool(current_app.config.get("AI_R3_DEMO_REQUIRE_FILE", False))
            demo_cd      = current_app.config.get("AI_R3_DEMO_COOLDOWN_S", None)

            # 1) filtro por tipo
            if demo_tipos:
                if (dispositivo.tipo or "").lower() not in demo_tipos:
                    return
            # 2) filtro por serial
            if demo_serials:
                if (dispositivo.serial_number or "") not in demo_serials:
                    return
            # 3) exigir .csv o .pkl preparado
            if require_file:
                base = current_app.config.get("AI_R3_MODEL_DIR", "app/iotelligence/data/river_models")
                safe = "".join(ch for ch in (serial or "unknown") if ch.isalnum() or ch in ("-","_"))
                has_csv = os.path.isfile(os.path.join(base, f"{safe}.csv"))
                has_pkl = os.path.isfile(os.path.join(base, f"{safe}.river.pkl"))
                if not (has_csv or has_pkl):
                    return

            # 4) cooldown: si hay demo_cd, úsalo; si no, el estándar
            if isinstance(demo_cd, (int, float)) and demo_cd is not None:
                last = _LAST_SUGGEST_TS.get(dispositivo.id, 0.0)
                if time.time() - last < float(demo_cd):
                    return
            else:
                if not _should_emit_suggest(dispositivo.id):
                    return

            # --- Construcción de máscaras DEMO (csv -> modelo como respaldo) ---
            step   = int(current_app.config.get("AI_R3_BIN_MINUTES", 15))
            thresh = float(current_app.config.get("AI_R3_PROB_THRESH", 0.60))
            topk   = int(current_app.config.get("AI_R3_DEMO_TOPK_PER_DAY", 0))

            src = str(current_app.config.get("AI_R3_DEMO_SOURCE", "csv")).lower()
            masks: Dict[int, List[bool]] = {}
            if src == "csv":
                csvp = _csv_path_for_demo(serial)
                if csvp:
                    masks = _hist_masks_from_csv(csvp, step, thresh, topk=topk)
                if not masks:
                    masks = _hist_masks_from_model(model, step, thresh, topk=topk)
            else:
                masks = _hist_masks_from_model(model, step, thresh, topk=topk)

            # Auditoría vs horario (opcional)
            if bool(current_app.config.get("AI_R3_AUDIT_WHEN_HORARIO", True)) and modo == "horario":
                current_masks = _current_schedule_masks(cfg, step)
                diff_thresh = float(current_app.config.get("AI_R3_DIFF_THRESH",
                                current_app.config.get("AI_R3_DIFF_TRESH", 0.30)))
                diff = _diff_ratio(current_masks, masks)
                if diff >= diff_thresh:
                    _emit_suggestion(dispositivo, model,
                                    current_masks=current_masks,
                                    diff_ratio_val=diff,
                                    learned_masks_override=masks)
            else:
                _emit_suggestion(dispositivo, model, learned_masks_override=masks)
            return
        # =================== FIN MODO DEMO ===================

        # ======= MODO REAL (aprendizaje online) =======
        target = self._target_from_dispositivo(dispositivo)
        if target is None:
            return

        ts_utc = ts or now_utc()
        x = _time_features(ts_utc)
        try:
            model.learn_one(x, bool(target))
        except Exception:
            return

        disp_id = dispositivo.id
        _TOTAL_EVENTS[disp_id] = _TOTAL_EVENTS.get(disp_id, 0) + 1
        _UPDATE_COUNT[disp_id] = _UPDATE_COUNT.get(disp_id, 0) + 1
        _maybe_save_model(serial, disp_id, model)

        if not _should_emit_suggest(disp_id):
            return

        # cálculo único
        step     = int(current_app.config.get("AI_R3_BIN_MINUTES", 15))
        thresh   = float(current_app.config.get("AI_R3_PROB_THRESH", 0.60))
        min_diff = float(current_app.config.get("AI_R3_SUGGEST_MIN_DIFF", 0.05))
        learned_masks = _learned_masks(model, step, thresh)

        # Hysteresis vs última sugerencia
        last_masks = _LAST_MASKS.get(disp_id)
        if last_masks is not None and _masks_equalish(last_masks, learned_masks, min_diff):
            return

        # Auditoría cuando está en horario
        if bool(current_app.config.get("AI_R3_AUDIT_WHEN_HORARIO", True)) and modo == "horario":
            diff_thresh = float(current_app.config.get("AI_R3_DIFF_THRESH",
                               current_app.config.get("AI_R3_DIFF_TRESH", 0.30)))
            current_masks = _current_schedule_masks(cfg, step)
            diff = _diff_ratio(current_masks, learned_masks)
            if diff >= diff_thresh:
                _save_model(serial, model)
                _emit_suggestion(dispositivo, model, current_masks=current_masks, diff_ratio_val=diff)
                _LAST_MASKS[disp_id] = learned_masks
        else:
            _save_model(serial, model)
            _emit_suggestion(dispositivo, model)
            _LAST_MASKS[disp_id] = learned_masks