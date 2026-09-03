"""Telegram Bot API helper — per-user credentials preferred; host .env as fallback."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

_DOTENV_LOADED = False


def _candidate_env_files() -> list[Path]:
    paths: list[Path] = []
    install = os.getenv("CIM_INSTALL_ROOT", "").strip()
    if install:
        paths.append(Path(install) / ".env")
    here = Path(__file__).resolve()
    for parent in here.parents:
        paths.append(parent / ".env")
        if len(paths) > 8:
            break
    paths.append(Path.cwd() / ".env")
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _ensure_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    for path in _candidate_env_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key.startswith("TELEGRAM_") and key not in os.environ:
                os.environ[key] = val
            if key == "CIM_TELEGRAM_KEK" and key not in os.environ:
                os.environ[key] = val
        break


def host_telegram_configured() -> bool:
    _ensure_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return bool(token and chat_id)


def telegram_configured() -> bool:
    """Backward-compat alias: host .env present."""
    return host_telegram_configured()


def telegram_status(
    *,
    user_status: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Combined status for the Alerts UI.

    Prefer per-user encrypted credentials; host .env is a legacy operator fallback.
    """
    _ensure_dotenv()
    host_token = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    host_chat = bool(os.getenv("TELEGRAM_CHAT_ID", "").strip())
    user = user_status if isinstance(user_status, dict) else {}
    if user.get("configured"):
        return {
            "configured": True,
            "connected": True,
            "source": "user",
            "has_token": True,
            "has_chat_id": True,
            "chat_id_hint": user.get("chat_id_hint"),
            "bot_username": user.get("bot_username"),
            "bot_name": user.get("bot_name"),
            "host_fallback_available": bool(host_token and host_chat),
            "updated_at": user.get("updated_at"),
        }
    if host_token and host_chat:
        return {
            "configured": True,
            "connected": True,
            "source": "host",
            "has_token": True,
            "has_chat_id": True,
            "chat_id_hint": None,
            "bot_username": None,
            "bot_name": None,
            "host_fallback_available": True,
            "updated_at": None,
        }
    return {
        "configured": False,
        "connected": False,
        "source": "none",
        "has_token": bool(user.get("has_token") or host_token),
        "has_chat_id": bool(user.get("has_chat_id") or host_chat),
        "chat_id_hint": None,
        "bot_username": None,
        "bot_name": None,
        "host_fallback_available": False,
        "updated_at": None,
    }


def get_me(bot_token: str, *, timeout: float = 12.0) -> dict[str, Any]:
    """
    Call Telegram getMe. Returns {ok, username?, name?, error?}.
    Username is safe to show in the UI (not a secret).
    """
    token = str(bot_token or "").strip()
    if not token:
        return {"ok": False, "error": "bot token required"}
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": False, "error": "invalid Telegram response"}
            if not data.get("ok"):
                return {"ok": False, "error": str(data.get("description") or "Telegram API error")}
            result = data.get("result") if isinstance(data.get("result"), dict) else {}
            username = str(result.get("username") or "").strip()
            name = str(result.get("first_name") or result.get("name") or "").strip()
            return {
                "ok": True,
                "username": f"@{username}" if username and not username.startswith("@") else (username or None),
                "name": name or None,
            }
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {"ok": False, "error": f"HTTP {e.code}: {detail[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(
    text: str,
    *,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """
    Send a Telegram message. Returns {ok, error?}.

    When bot_token/chat_id are omitted, falls back to host TELEGRAM_* env
    (legacy single-operator setup). Prefer passing per-user decrypted credentials.
    """
    _ensure_dotenv()
    token = str(bot_token or "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    dest = str(chat_id or "").strip() or os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not dest:
        return {"ok": False, "error": "Telegram bot token / chat id not configured for this account"}
    body = json.dumps({
        "chat_id": dest,
        "text": str(text or "")[:3500],
        "disable_web_page_preview": True,
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": False, "error": "invalid Telegram response"}
            if not data.get("ok"):
                return {"ok": False, "error": str(data.get("description") or "Telegram API error")}
            return {"ok": True}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {"ok": False, "error": f"HTTP {e.code}: {detail[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_for_user(
    base_dir: Path,
    session: Optional[dict[str, Any]],
    text: str,
    *,
    allow_host_fallback: bool = True,
) -> dict[str, Any]:
    """Decrypt per-user creds (if any) and send; optional host .env fallback."""
    from server import user_alerts_store as alerts_store

    creds = alerts_store.resolve_telegram_credentials(base_dir, session=session)
    if creds.get("ok"):
        return send_message(
            text,
            bot_token=str(creds.get("bot_token") or ""),
            chat_id=str(creds.get("chat_id") or ""),
        )
    if allow_host_fallback and host_telegram_configured():
        return send_message(text)
    return {
        "ok": False,
        "error": str(creds.get("error") or "Telegram not configured for this account"),
    }
