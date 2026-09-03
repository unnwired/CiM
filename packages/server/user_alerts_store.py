"""Per-account alert inbox + settings (watchlist / earnings notifications)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from server import app_code_crypto as _crypto
from server.user_data_paths import email_safe, user_lock

ALERTS_FILENAME = "user_alerts.json"
SETTINGS_FILENAME = "alert_settings.json"
# Ciphertext only — never store plaintext bot tokens / chat IDs on disk.
TELEGRAM_SECRETS_FILENAME = "telegram_secrets.json"
MAX_ALERTS = 500
IST = ZoneInfo("Asia/Kolkata")

DEFAULT_SETTINGS: dict[str, Any] = {
    "telegram_enabled": True,
    "browser_enabled": True,
    "earnings_notifications_enabled": False,
    "day_move_pct": 3.0,
    "portfolio_notifications_enabled": False,
    "portfolio_day_move_pct": 3.0,
    "earnings_filter_snapshot": None,
    # Per-symbol upcoming earnings bells: [{symbol, release_date, enabled}]
    "upcoming_earnings_watches": [],
    # Absolute price targets (watchlist notifications gate in evaluator):
    # [{id, symbol, direction, level, armed, generation, triggered_at}]
    "price_targets": [],
}

MAX_UPCOMING_WATCHES = 200
MAX_PRICE_TARGETS = 200


def resolve_user_alerts_namespace(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    email = str((session or {}).get("email") or "").strip()
    machine = _crypto.current_machine_code().strip().upper()
    segment = email_safe(email) if email else "_local"
    ns = base_dir / "data" / "users" / segment / machine
    ns.mkdir(parents=True, exist_ok=True)
    return ns


def _alerts_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_alerts_namespace(base_dir, session) / ALERTS_FILENAME


def _settings_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_alerts_namespace(base_dir, session) / SETTINGS_FILENAME


def _telegram_secrets_path(base_dir: Path, session: Optional[dict[str, Any]] = None) -> Path:
    return resolve_user_alerts_namespace(base_dir, session) / TELEGRAM_SECRETS_FILENAME


def ist_today_key(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(IST)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%Y-%m-%d")


def dedup_key(symbol: str, kind: str, day_key: Optional[str] = None) -> str:
    sym = str(symbol or "").strip().upper()
    k = str(kind or "").strip().lower()
    day = day_key or ist_today_key()
    return f"{sym}|{k}|{day}"


def _normalize_alert(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    symbol = str(raw.get("symbol") or "").strip().upper()
    kind = str(raw.get("kind") or "").strip().lower()
    if not symbol or not kind:
        return None
    aid = str(raw.get("id") or "").strip() or str(uuid.uuid4())
    source = str(raw.get("source") or "watchlist").strip().lower()
    if source not in ("watchlist", "earnings", "portfolio", "system"):
        source = "watchlist"
    return {
        "id": aid,
        "created_at": str(raw.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "source": source,
        "kind": kind,
        "symbol": symbol,
        "title": str(raw.get("title") or symbol)[:200],
        "body": str(raw.get("body") or "")[:2000],
        "watchlist_name": (str(raw.get("watchlist_name") or "").strip() or None),
        "read": bool(raw.get("read")),
        "dedup_key": str(raw.get("dedup_key") or dedup_key(symbol, kind)),
        "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        "delivered_telegram": bool(raw.get("delivered_telegram")),
        "delivered_browser_pending": bool(raw.get("delivered_browser_pending", True)),
    }


def normalize_alerts_doc(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    alerts_raw = raw.get("alerts")
    if not isinstance(alerts_raw, list):
        alerts_raw = []
    alerts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in alerts_raw:
        a = _normalize_alert(item)
        if a is None:
            continue
        if a["id"] in seen_ids:
            a["id"] = str(uuid.uuid4())
        seen_ids.add(a["id"])
        alerts.append(a)
    # newest first
    alerts.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    if len(alerts) > MAX_ALERTS:
        alerts = alerts[:MAX_ALERTS]
    return {"alerts": alerts}


def load_alerts(base_dir: Path, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _alerts_path(base_dir, session)
        if not path.is_file():
            return {"alerts": []}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"alerts": []}
        return normalize_alerts_doc(raw)


def save_alerts(base_dir: Path, doc: Any, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    normalized = normalize_alerts_doc(doc)
    with user_lock(base_dir, session):
        path = _alerts_path(base_dir, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return normalized


def normalize_upcoming_watch(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    symbol = str(raw.get("symbol") or "").strip().upper()
    release = str(raw.get("release_date") or raw.get("earnings_release_next_date") or "").strip()[:10]
    if not symbol or len(release) < 10:
        return None
    try:
        datetime.strptime(release, "%Y-%m-%d")
    except ValueError:
        return None
    return {
        "symbol": symbol,
        "release_date": release,
        "enabled": bool(raw.get("enabled", True)),
    }


def normalize_upcoming_watches(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        w = normalize_upcoming_watch(item)
        if w is None:
            continue
        if w["symbol"] in seen:
            # Latest entry wins (overwrite earlier)
            out = [x for x in out if x["symbol"] != w["symbol"]]
        seen.add(w["symbol"])
        out.append(w)
        if len(out) >= MAX_UPCOMING_WATCHES:
            break
    return out


def set_upcoming_earnings_watch(
    base_dir: Path,
    *,
    symbol: str,
    release_date: str,
    enabled: bool,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Arm or disarm a per-symbol upcoming-earnings bell (one watch per symbol)."""
    settings = load_settings(base_dir, session=session)
    watches = normalize_upcoming_watches(settings.get("upcoming_earnings_watches"))
    sym = str(symbol or "").strip().upper()
    rel = str(release_date or "").strip()[:10]
    if not sym:
        raise ValueError("symbol is required")
    watches = [w for w in watches if w["symbol"] != sym]
    if enabled:
        entry = normalize_upcoming_watch({
            "symbol": sym,
            "release_date": rel,
            "enabled": True,
        })
        if entry is None:
            raise ValueError("release_date must be YYYY-MM-DD")
        watches.append(entry)
    settings["upcoming_earnings_watches"] = watches
    return save_settings(base_dir, settings, session=session)


def normalize_price_target(raw: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    sym = str(raw.get("symbol") or "").strip().upper()
    direction = str(raw.get("direction") or "").strip().lower()
    if direction in ("up", "above_eq", ">="):
        direction = "above"
    if direction in ("down", "below_eq", "<="):
        direction = "below"
    if not sym or direction not in ("above", "below"):
        return None
    try:
        level = float(raw.get("level"))
    except (TypeError, ValueError):
        return None
    if not (level > 0) or level != level:
        return None
    try:
        generation = max(0, int(raw.get("generation") or 0))
    except (TypeError, ValueError):
        generation = 0
    tid = str(raw.get("id") or "").strip() or str(uuid.uuid4())
    return {
        "id": tid,
        "symbol": sym,
        "direction": direction,
        "level": round(level, 4),
        "armed": bool(raw.get("armed", True)),
        "generation": generation,
        "triggered_at": str(raw.get("triggered_at") or "") or None,
        "created_at": str(raw.get("created_at") or "") or None,
    }


def normalize_price_targets(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        entry = normalize_price_target(item)
        if entry is None or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        out.append(entry)
        if len(out) >= MAX_PRICE_TARGETS:
            break
    return out


def upsert_price_target(
    base_dir: Path,
    *,
    symbol: str,
    direction: str,
    level: float,
    target_id: Optional[str] = None,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create or replace an armed absolute price target."""
    settings = load_settings(base_dir, session=session)
    targets = normalize_price_targets(settings.get("price_targets"))
    now = datetime.now(timezone.utc).isoformat()
    entry = normalize_price_target({
        "id": target_id,
        "symbol": symbol,
        "direction": direction,
        "level": level,
        "armed": True,
        "generation": 0,
        "triggered_at": None,
        "created_at": now,
    })
    if entry is None:
        raise ValueError("symbol, direction (above|below), and positive level are required")
    if target_id:
        prev = next((t for t in targets if t["id"] == target_id), None)
        if prev:
            entry["generation"] = int(prev.get("generation") or 0)
            entry["created_at"] = prev.get("created_at") or now
            targets = [t for t in targets if t["id"] != target_id]
    # One armed target per symbol+direction — replace older same pair.
    targets = [
        t for t in targets
        if not (t["symbol"] == entry["symbol"] and t["direction"] == entry["direction"] and t["id"] != entry["id"])
    ]
    targets.append(entry)
    settings["price_targets"] = targets
    return save_settings(base_dir, settings, session=session)


def set_price_target_armed(
    base_dir: Path,
    *,
    target_id: str,
    armed: bool,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    settings = load_settings(base_dir, session=session)
    targets = normalize_price_targets(settings.get("price_targets"))
    tid = str(target_id or "").strip()
    found = False
    for t in targets:
        if t["id"] != tid:
            continue
        found = True
        if armed and not t.get("armed"):
            t["generation"] = int(t.get("generation") or 0) + 1
            t["triggered_at"] = None
        t["armed"] = bool(armed)
        break
    if not found:
        raise ValueError("price target not found")
    settings["price_targets"] = targets
    return save_settings(base_dir, settings, session=session)


def delete_price_target(
    base_dir: Path,
    *,
    target_id: str,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    settings = load_settings(base_dir, session=session)
    tid = str(target_id or "").strip()
    targets = normalize_price_targets(settings.get("price_targets"))
    nxt = [t for t in targets if t["id"] != tid]
    if len(nxt) == len(targets):
        raise ValueError("price target not found")
    settings["price_targets"] = nxt
    return save_settings(base_dir, settings, session=session)


def mark_price_target_triggered(
    base_dir: Path,
    *,
    target_id: str,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    settings = load_settings(base_dir, session=session)
    targets = normalize_price_targets(settings.get("price_targets"))
    tid = str(target_id or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    for t in targets:
        if t["id"] == tid:
            t["armed"] = False
            t["triggered_at"] = now
            break
    settings["price_targets"] = targets
    return save_settings(base_dir, settings, session=session)


def prune_expired_upcoming_watches(
    base_dir: Path,
    session: Optional[dict[str, Any]] = None,
    *,
    today: Optional[str] = None,
) -> dict[str, Any]:
    """Drop watches whose release_date is before today (IST)."""
    settings = load_settings(base_dir, session=session)
    day = str(today or ist_today_key())[:10]
    watches = normalize_upcoming_watches(settings.get("upcoming_earnings_watches"))
    kept = [w for w in watches if w["release_date"] >= day]
    if len(kept) == len(watches):
        return settings
    settings["upcoming_earnings_watches"] = kept
    return save_settings(base_dir, settings, session=session)


def normalize_settings(raw: Any) -> dict[str, Any]:
    base = dict(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return base
    if "telegram_enabled" in raw:
        base["telegram_enabled"] = bool(raw.get("telegram_enabled"))
    if "browser_enabled" in raw:
        base["browser_enabled"] = bool(raw.get("browser_enabled"))
    if "earnings_notifications_enabled" in raw:
        base["earnings_notifications_enabled"] = bool(raw.get("earnings_notifications_enabled"))
    if "portfolio_notifications_enabled" in raw:
        base["portfolio_notifications_enabled"] = bool(raw.get("portfolio_notifications_enabled"))
    try:
        pct = float(raw.get("day_move_pct", base["day_move_pct"]))
        base["day_move_pct"] = max(0.5, min(50.0, pct))
    except (TypeError, ValueError):
        pass
    try:
        ppct = float(raw.get("portfolio_day_move_pct", base["portfolio_day_move_pct"]))
        base["portfolio_day_move_pct"] = max(0.5, min(50.0, ppct))
    except (TypeError, ValueError):
        pass
    snap = raw.get("earnings_filter_snapshot")
    if snap is None or isinstance(snap, dict):
        base["earnings_filter_snapshot"] = snap
    if "upcoming_earnings_watches" in raw:
        base["upcoming_earnings_watches"] = normalize_upcoming_watches(
            raw.get("upcoming_earnings_watches")
        )
    else:
        base["upcoming_earnings_watches"] = []
    if "price_targets" in raw:
        base["price_targets"] = normalize_price_targets(raw.get("price_targets"))
    else:
        base["price_targets"] = []
    return base


def load_settings(base_dir: Path, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _settings_path(base_dir, session)
        if not path.is_file():
            return dict(DEFAULT_SETTINGS)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_SETTINGS)
        return normalize_settings(raw)


def save_settings(base_dir: Path, settings: Any, session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    normalized = normalize_settings(settings)
    with user_lock(base_dir, session):
        path = _settings_path(base_dir, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return normalized


def _mask_chat_id(chat_id: str) -> Optional[str]:
    s = str(chat_id or "").strip()
    if not s:
        return None
    if len(s) <= 4:
        return "****"
    return f"…{s[-4:]}"


def load_telegram_secrets_doc(
    base_dir: Path, session: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _telegram_secrets_path(base_dir, session)
        if not path.is_file():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}


def save_telegram_credentials(
    base_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Encrypt and persist this account's Telegram bot token + chat id.
    Returns a public status dict (never plaintext secrets).
    """
    from server import telegram_notify
    from server import user_secret_crypto as _usc

    token = str(bot_token or "").strip()
    chat = str(chat_id or "").strip()
    if not token or not chat:
        raise ValueError("bot_token and chat_id are required")
    if ":" not in token or len(token) < 20:
        raise ValueError("bot_token looks invalid")

    profile = telegram_notify.get_me(token)
    if not profile.get("ok"):
        raise ValueError(
            str(profile.get("error") or "Telegram rejected this bot token — check it and try again")
        )

    doc = {
        "v": 1,
        "bot_token_enc": _usc.encrypt_secret(token, session=session, base_dir=base_dir),
        "chat_id_enc": _usc.encrypt_secret(chat, session=session, base_dir=base_dir),
        "chat_id_hint": _mask_chat_id(chat),
        "bot_username": profile.get("username"),
        "bot_name": profile.get("name"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with user_lock(base_dir, session):
        path = _telegram_secrets_path(base_dir, session)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return telegram_credentials_status(base_dir, session=session)


def clear_telegram_credentials(
    base_dir: Path, session: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _telegram_secrets_path(base_dir, session)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    return telegram_credentials_status(base_dir, session=session)


def resolve_telegram_credentials(
    base_dir: Path, session: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    Decrypt this user's Telegram credentials for send-time use only.
    Returns {ok, bot_token?, chat_id?, error?}. Never log the return value.
    """
    from server import user_secret_crypto as _usc

    doc = load_telegram_secrets_doc(base_dir, session=session)
    enc_token = str(doc.get("bot_token_enc") or "").strip()
    enc_chat = str(doc.get("chat_id_enc") or "").strip()
    if not enc_token or not enc_chat:
        return {"ok": False, "error": "no per-user Telegram credentials"}
    try:
        token = _usc.decrypt_secret(enc_token, session=session, base_dir=base_dir)
        chat = _usc.decrypt_secret(enc_chat, session=session, base_dir=base_dir)
    except Exception:
        return {"ok": False, "error": "could not decrypt Telegram credentials"}
    if not token or not chat:
        return {"ok": False, "error": "empty Telegram credentials"}
    return {"ok": True, "bot_token": token, "chat_id": chat}


def refresh_telegram_bot_profile(
    base_dir: Path, session: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    If credentials exist but bot_username is missing (legacy saves), call getMe
    and persist the public profile fields. Never returns secrets.
    """
    from server import telegram_notify

    doc = load_telegram_secrets_doc(base_dir, session=session)
    if not str(doc.get("bot_token_enc") or "").strip():
        return telegram_credentials_status(base_dir, session=session)
    if str(doc.get("bot_username") or "").strip():
        return telegram_credentials_status(base_dir, session=session)

    creds = resolve_telegram_credentials(base_dir, session=session)
    if not creds.get("ok"):
        return telegram_credentials_status(base_dir, session=session)

    profile = telegram_notify.get_me(str(creds.get("bot_token") or ""))
    if not profile.get("ok"):
        return telegram_credentials_status(base_dir, session=session)

    with user_lock(base_dir, session):
        path = _telegram_secrets_path(base_dir, session)
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return telegram_credentials_status(base_dir, session=session)
        if not isinstance(raw, dict):
            return telegram_credentials_status(base_dir, session=session)
        raw["bot_username"] = profile.get("username")
        raw["bot_name"] = profile.get("name")
        raw["updated_at"] = datetime.now(timezone.utc).isoformat()
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return telegram_credentials_status(base_dir, session=session)


def telegram_credentials_status(
    base_dir: Path, session: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Public status for the Alerts UI — never includes plaintext secrets."""
    doc = load_telegram_secrets_doc(base_dir, session=session)
    has_token = bool(str(doc.get("bot_token_enc") or "").strip())
    has_chat = bool(str(doc.get("chat_id_enc") or "").strip())
    configured = has_token and has_chat
    hint = doc.get("chat_id_hint")
    if hint is not None:
        hint = str(hint)
    username = str(doc.get("bot_username") or "").strip() or None
    name = str(doc.get("bot_name") or "").strip() or None
    return {
        "configured": configured,
        "connected": configured,
        "has_token": has_token,
        "has_chat_id": has_chat,
        "chat_id_hint": hint if configured else None,
        "bot_username": username if configured else None,
        "bot_name": name if configured else None,
        "source": "user" if configured else "none",
        "updated_at": str(doc.get("updated_at") or "") or None,
    }


def has_dedup(alerts: list[dict[str, Any]], key: str) -> bool:
    k = str(key or "")
    return any(str(a.get("dedup_key") or "") == k for a in alerts)


def surprise_ready(val: Any) -> bool:
    """True when EPS/revenue surprise is a real numeric value (not blank/missing)."""
    if val is None:
        return False
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return True
    s = str(val).strip()
    if not s or s in ("—", "-", "n/a", "N/A", "null", "None"):
        return False
    try:
        float(s.replace("%", "").replace(",", ""))
        return True
    except ValueError:
        return False


def earnings_completeness(meta: Optional[dict[str, Any]]) -> tuple[int, int]:
    """
    (eps_ready, revenue_ready) bits for a prior or incoming earnings alert.

    Prefer explicit flags when present; otherwise derive from surprise fields.
    """
    m = meta if isinstance(meta, dict) else {}
    if "eps_ready" in m or "revenue_ready" in m:
        return (1 if m.get("eps_ready") else 0, 1 if m.get("revenue_ready") else 0)
    return (
        1 if surprise_ready(m.get("eps_surprise_pct")) else 0,
        1 if surprise_ready(m.get("revenue_surprise_pct")) else 0,
    )


def earnings_dedup_day(release_date: str, eps_ready: bool, revenue_ready: bool) -> str:
    """Stable day key: release date + which surprise fields were present."""
    rel = str(release_date or "").strip()[:10]
    return f"{rel}|e{1 if eps_ready else 0}r{1 if revenue_ready else 0}"


def _alert_release_date(meta: dict[str, Any]) -> str:
    for field in ("date", "earnings_release_date", "earnings_release_next_date"):
        rel = str(meta.get(field) or "").strip()[:10]
        if rel:
            return rel
    return ""


def has_release_dedup(
    alerts: list[dict[str, Any]],
    *,
    symbol: str,
    kind: str,
    release_date: str,
    eps_ready: Optional[bool] = None,
    revenue_ready: Optional[bool] = None,
) -> bool:
    """
    True if this symbol+kind was already alerted for the same earnings release
    at equal or better data completeness.

    Same release with incomplete EPS/revenue may alert again when the missing
    field(s) fill in. Unchanged completeness (daily re-scan) stays blocked.
    """
    sym = str(symbol or "").strip().upper()
    k = str(kind or "").strip().lower()
    rel = str(release_date or "").strip()[:10]
    if not sym or not k or not rel:
        return False

    if eps_ready is None and revenue_ready is None:
        new_eps, new_rev = (0, 0)
    else:
        new_eps = 1 if eps_ready else 0
        new_rev = 1 if revenue_ready else 0

    # Exact key match (release + completeness fingerprint).
    if has_dedup(alerts, dedup_key(sym, k, earnings_dedup_day(rel, bool(new_eps), bool(new_rev)))):
        return True
    # Legacy: release-date-only key (pre-completeness format).
    if new_eps == 0 and new_rev == 0 and has_dedup(alerts, dedup_key(sym, k, rel)):
        return True

    for a in alerts:
        if str(a.get("symbol") or "").strip().upper() != sym:
            continue
        if str(a.get("kind") or "").strip().lower() != k:
            continue
        meta = a.get("meta") if isinstance(a.get("meta"), dict) else {}
        if _alert_release_date(meta) != rel:
            # Also accept legacy keys that embed the release as the day segment.
            key = str(a.get("dedup_key") or "")
            if not (key.endswith(f"|{rel}") or f"|{rel}|" in key):
                continue
        old_eps, old_rev = earnings_completeness(meta)
        if old_eps >= new_eps and old_rev >= new_rev:
            return True
    return False


def append_alert(
    base_dir: Path,
    alert: dict[str, Any],
    session: Optional[dict[str, Any]] = None,
) -> tuple[Optional[dict[str, Any]], bool]:
    """
    Append if dedup_key is new. Returns (alert_or_None, inserted).
    """
    normalized = _normalize_alert(alert)
    if normalized is None:
        return None, False
    with user_lock(base_dir, session):
        path = _alerts_path(base_dir, session)
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, json.JSONDecodeError):
                raw = {"alerts": []}
        else:
            raw = {"alerts": []}
        doc = normalize_alerts_doc(raw)
        kind = str(normalized.get("kind") or "")
        meta = normalized.get("meta") if isinstance(normalized.get("meta"), dict) else {}
        release = str(
            meta.get("date")
            or meta.get("earnings_release_date")
            or meta.get("earnings_release_next_date")
            or ""
        ).strip()[:10]
        if kind.startswith("earnings") and release:
            eps_bit, rev_bit = earnings_completeness(meta)
            if has_release_dedup(
                doc["alerts"],
                symbol=str(normalized.get("symbol") or ""),
                kind=kind,
                release_date=release,
                eps_ready=bool(eps_bit),
                revenue_ready=bool(rev_bit),
            ):
                return None, False
        elif has_dedup(doc["alerts"], normalized["dedup_key"]):
            return None, False
        doc["alerts"].insert(0, normalized)
        if len(doc["alerts"]) > MAX_ALERTS:
            doc["alerts"] = doc["alerts"][:MAX_ALERTS]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return normalized, True


def mark_alerts(
    base_dir: Path,
    *,
    ids: Optional[list[str]] = None,
    mark_all_read: bool = False,
    clear_browser_pending: bool = False,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    with user_lock(base_dir, session):
        path = _alerts_path(base_dir, session)
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, json.JSONDecodeError):
                raw = {"alerts": []}
        else:
            raw = {"alerts": []}
        doc = normalize_alerts_doc(raw)
        id_set = {str(x) for x in (ids or []) if x}
        for a in doc["alerts"]:
            if mark_all_read or a["id"] in id_set:
                a["read"] = True
            if clear_browser_pending and (mark_all_read or a["id"] in id_set or not id_set):
                if clear_browser_pending and (not id_set or a["id"] in id_set):
                    a["delivered_browser_pending"] = False
        if clear_browser_pending and not id_set and not mark_all_read:
            for a in doc["alerts"]:
                a["delivered_browser_pending"] = False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return doc


def delete_alerts(
    base_dir: Path,
    *,
    ids: Optional[list[str]] = None,
    clear_all: bool = False,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Delete alerts by id, or wipe the inbox when clear_all=True."""
    with user_lock(base_dir, session):
        path = _alerts_path(base_dir, session)
        if path.is_file():
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
            except (OSError, json.JSONDecodeError):
                raw = {"alerts": []}
        else:
            raw = {"alerts": []}
        doc = normalize_alerts_doc(raw)
        if clear_all:
            doc["alerts"] = []
        else:
            id_set = {str(x) for x in (ids or []) if x}
            if not id_set:
                return doc
            doc["alerts"] = [a for a in doc["alerts"] if a.get("id") not in id_set]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        tmp.replace(path)
    return doc


def unread_count(doc: dict[str, Any]) -> int:
    return sum(1 for a in (doc.get("alerts") or []) if not a.get("read"))


def browser_pending_alerts(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        a for a in (doc.get("alerts") or [])
        if a.get("delivered_browser_pending") and not a.get("read")
    ]
