"""Temporary E2E web auth probe against running showcase."""
from __future__ import annotations

import random
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
TS_HEADERS = {"Host": "charts-in-motion.tail22251c.ts.net"}


def run_flow(label: str, headers: dict | None = None) -> bool:
    session = requests.Session()
    email = f"py-e2e-{random.randint(1, 999999)}@example.com"
    password = "CiM-E2E-Password-123!"

    session.post(f"{BASE}/api/auth/signup", json={"email": email, "password": password}, headers=headers)
    login = session.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        headers=headers,
    )
    print(f"\n=== {label} ===")
    print("login", login.status_code, login.headers.get("Set-Cookie", "")[:160])
    print("jar cim_sid", session.cookies.get("cim_sid"))

    status_after_login = session.get(f"{BASE}/api/license/status", headers=headers)
    print("status after login", status_after_login.json())

    complete = session.post(f"{BASE}/api/auth/complete", json={}, headers=headers)
    print("complete", complete.status_code, complete.text[:240])

    root = session.get(f"{BASE}/", headers=headers)
    ok = complete.ok and 'id="root"' in root.text
    print("root app", ok)
    return ok


def main() -> int:
    plain_ok = run_flow("plain http (no Host override)", None)
    ts_ok = run_flow("ts.net Host on http", TS_HEADERS)
    return 0 if plain_ok and ts_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
