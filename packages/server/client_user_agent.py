"""Parse browser User-Agent strings for web showcase license tracking."""
from __future__ import annotations

import re
from typing import Any, Optional

_CLIENT_ENV_KEYS = (
    "client_platform",
    "client_os",
    "client_os_version",
    "client_browser",
    "client_browser_version",
    "client_device_type",
)


def parse_user_agent(ua: str) -> dict[str, Optional[str]]:
    if not ua or not str(ua).strip():
        return {}
    text = str(ua).strip()[:512]

    device_type = "desktop"
    if re.search(r"iPhone|iPod|Mobile", text, re.I) and "iPad" not in text:
        device_type = "mobile"
    elif re.search(r"iPad|Tablet", text, re.I):
        device_type = "tablet"
    elif re.search(r"Android", text, re.I) and re.search(r"Mobile", text, re.I):
        device_type = "mobile"
    elif re.search(r"Android", text, re.I):
        device_type = "tablet"

    os_name: Optional[str] = None
    os_version: Optional[str] = None

    win = re.search(r"Windows NT ([\d.]+)", text)
    if win:
        os_name = "Windows"
        nt_map = {"10.0": "10/11", "6.3": "8.1", "6.2": "8", "6.1": "7"}
        os_version = nt_map.get(win.group(1), win.group(1))
    elif (android := re.search(r"Android ([\d.]+)", text, re.I)):
        os_name = "Android"
        os_version = android.group(1)
    elif (ios := re.search(r"(?:iPhone OS|CPU (?:iPhone )?OS) ([\d_]+)", text)):
        os_name = "iOS"
        os_version = ios.group(1).replace("_", ".")
    elif (mac := re.search(r"Mac OS X ([\d_]+)", text)):
        os_name = "macOS"
        os_version = mac.group(1).replace("_", ".")
    elif "Linux" in text:
        os_name = "Linux"
        ubuntu = re.search(r"Ubuntu/([\d.]+)", text)
        os_version = ubuntu.group(1) if ubuntu else None
    elif "CrOS" in text:
        os_name = "ChromeOS"

    browser: Optional[str] = None
    browser_version: Optional[str] = None

    edge = re.search(r"Edg(?:e|A|iOS)?/([\d.]+)", text)
    firefox = re.search(r"Firefox/([\d.]+)", text)
    chrome = re.search(r"Chrome/([\d.]+)", text)
    safari_ver = re.search(r"Version/([\d.]+)", text)

    if edge:
        browser = "Edge"
        browser_version = edge.group(1).split(".")[0]
    elif firefox:
        browser = "Firefox"
        browser_version = firefox.group(1).split(".")[0]
    elif chrome and not edge:
        browser = "Chrome"
        browser_version = chrome.group(1).split(".")[0]
    elif "Safari" in text and safari_ver:
        browser = "Safari"
        browser_version = safari_ver.group(1).split(".")[0]
    elif "Safari" in text and "Chrome" not in text:
        browser = "Safari"

    return {
        "client_platform": "web",
        "client_os": os_name,
        "client_os_version": os_version,
        "client_browser": browser,
        "client_browser_version": browser_version,
        "client_device_type": device_type,
    }


def web_client_env_from_user_agent(ua: Optional[str]) -> Optional[dict[str, str]]:
    parsed = parse_user_agent(ua or "")
    if not parsed.get("client_os") and not parsed.get("client_browser"):
        return None
    out: dict[str, str] = {}
    for key in _CLIENT_ENV_KEYS:
        val = parsed.get(key)
        if val:
            out[key] = str(val)[:80] if key != "client_platform" else str(val)[:16]
    if out.get("client_platform") != "web":
        out["client_platform"] = "web"
    return out or None


def merge_client_env_body(body: dict[str, Any], client_env: Optional[dict[str, str]]) -> dict[str, Any]:
    if not client_env:
        return body
    for key in _CLIENT_ENV_KEYS:
        if client_env.get(key):
            body[key] = client_env[key]
    return body
