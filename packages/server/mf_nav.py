"""AMFI open-ended mutual fund NAV ingest + SQLite store (daily only, no live)."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import requests

IST = ZoneInfo("Asia/Kolkata")
NAV_OPEN_URL = "https://www.amfiindia.com/spages/NAVOpen.txt"
# Scheme-code NAV history (AMFI codes); used for on-demand ~90d backfill.
MFAPI_HISTORY_URL = "https://api.mfapi.in/mf/{code}"
HISTORY_THIN_ROWS = 60
HISTORY_BACKFILL_DAYS = 90
USER_AGENT = "CiM-MF-Nav/1.0 (+https://amfiindia.com)"
# Bulk NAV refresh must not run during the equity session (live Update path is separate).
MF_NAV_REFRESH_AFTER_HOUR = 15
MF_NAV_REFRESH_AFTER_MINUTE = 30


def mf_nav_refresh_allowed(now: Optional[datetime] = None) -> tuple[bool, str]:
    """True only after equity market close (15:30 IST) on weekdays; always on weekends.

    Live / intraday OHLCV Update never refreshes funds — this gate also blocks
    scheduled/manual MF jobs that fire too early on a trading day.
    """
    ts = now or datetime.now(IST)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=IST)
    else:
        ts = ts.astimezone(IST)
    if ts.weekday() >= 5:
        return True, ""
    close = ts.replace(
        hour=MF_NAV_REFRESH_AFTER_HOUR,
        minute=MF_NAV_REFRESH_AFTER_MINUTE,
        second=0,
        microsecond=0,
    )
    if ts >= close:
        return True, ""
    return (
        False,
        "Mutual fund NAVs update only after 15:30 IST (after market close). "
        "Intraday Update does not refresh funds.",
    )

_CATEGORY_ALIASES = (
    (re.compile(r"^Equity Schemes\s*-\s*", re.I), "Equity Scheme - "),
    (re.compile(r"^Hybrid Schemes\s*-\s*", re.I), "Hybrid Scheme - "),
    (re.compile(r"^Income/Debt Oriented Schemes\s*-\s*", re.I), "Debt Scheme - "),
    (re.compile(r"^Fund of Funds Scheme \(Domestic\)\s*-\s*", re.I), "Other Scheme - FoF Domestic"),
    (re.compile(r"^Overseas Fund of Funds\s*-\s*", re.I), "Other Scheme - FoF Overseas"),
    (re.compile(r"^Exchange Traded Funds \(ETFs\)\s*-\s*", re.I), "Other Scheme - "),
    (re.compile(r"^Index Funds\s*-\s*", re.I), "Other Scheme - Index Funds / "),
    (re.compile(r"^Balanced Advantage Fund/\s*Dynamic Asset Allocation", re.I), "Dynamic Asset Allocation or Balanced Advantage"),
)


def normalize_category(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "Uncategorized"
    for pat, repl in _CATEGORY_ALIASES:
        s = pat.sub(repl, s)
    s = re.sub(r"\s+", " ", s).strip()
    # Collapse "Other Scheme - Index Funds / Equity Funds" style
    s = s.replace("Index Funds / Equity Funds", "Index Funds")
    s = s.replace("Index Funds / Debt Funds", "Index Funds")
    return s or "Uncategorized"


def detect_plan_kind(scheme_name: str) -> str:
    n = (scheme_name or "").lower()
    has_direct = "direct" in n
    has_growth = "growth" in n
    # Exclude IDCW-only / dividend rows that also say growth incorrectly is rare;
    # require both Direct and Growth.
    if has_direct and has_growth and "idcw" not in n and "dividend" not in n:
        return "direct_growth"
    return "other"


def _parse_nav_date(raw: str) -> Optional[str]:
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_nav_open_text(text: str) -> list[dict[str, Any]]:
    """Parse NAVOpen.txt into scheme row dicts (open-ended only)."""
    lines = text.splitlines()
    category = "Uncategorized"
    amc = ""
    rows: list[dict[str, Any]] = []
    header_re = re.compile(
        r"^(Open Ended Schemes|Close Ended Schemes|Interval Fund Schemes)\((.+)\)$",
        re.I,
    )

    for line in lines:
        s = line.strip()
        if not s or s.startswith("Scheme Code"):
            continue
        m = header_re.match(s)
        if m:
            # Open-ended file should only have Open Ended; skip others if present.
            if not m.group(1).lower().startswith("open"):
                category = ""
                continue
            category = normalize_category(m.group(2))
            continue
        if ";" not in s:
            if s.lower().endswith("mutual fund") or "mutual fund" in s.lower():
                amc = s
            continue
        if not category:
            continue
        parts = s.split(";")
        if len(parts) < 6:
            continue
        code = parts[0].strip()
        if not code.isdigit():
            continue
        isin_g = (parts[1] or "").strip()
        isin_r = (parts[2] or "").strip()
        name = (parts[3] or "").strip()
        nav_raw = (parts[4] or "").strip()
        date_s = _parse_nav_date(parts[5])
        try:
            nav = float(nav_raw)
        except (TypeError, ValueError):
            continue
        if not name or not date_s or nav <= 0:
            continue
        isin = isin_g if isin_g and isin_g != "-" else (isin_r if isin_r and isin_r != "-" else "")
        rows.append(
            {
                "scheme_code": code,
                "scheme_name": name,
                "amc": amc,
                "category": category,
                "isin": isin,
                "plan_kind": detect_plan_kind(name),
                "last_nav": round(nav, 4),
                "nav_date": date_s,
            }
        )
    return rows


def setup_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mf_schemes (
            scheme_code TEXT PRIMARY KEY,
            scheme_name TEXT NOT NULL,
            amc TEXT,
            category TEXT,
            isin TEXT,
            plan_kind TEXT,
            last_nav REAL,
            nav_date TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mf_nav_history (
            scheme_code TEXT NOT NULL,
            Date TEXT NOT NULL,
            Open REAL,
            High REAL,
            Low REAL,
            Close REAL,
            Volume REAL DEFAULT 0,
            PRIMARY KEY (scheme_code, Date)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mf_schemes_category ON mf_schemes(category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mf_schemes_plan ON mf_schemes(plan_kind)"
    )
    conn.commit()


def upsert_schemes_and_history(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    now_iso: Optional[str] = None,
) -> dict[str, int]:
    setup_db(conn)
    now_iso = now_iso or datetime.now(IST).isoformat(timespec="seconds")
    schemes = 0
    hist = 0
    for r in rows:
        code = str(r["scheme_code"])
        nav = float(r["last_nav"])
        day = str(r["nav_date"])[:10]
        conn.execute(
            """
            INSERT OR REPLACE INTO mf_schemes
            (scheme_code, scheme_name, amc, category, isin, plan_kind, last_nav, nav_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                r["scheme_name"],
                r.get("amc") or "",
                r.get("category") or "Uncategorized",
                r.get("isin") or "",
                r.get("plan_kind") or "other",
                nav,
                day,
                now_iso,
            ),
        )
        schemes += 1
        conn.execute(
            """
            INSERT OR REPLACE INTO mf_nav_history
            (scheme_code, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (code, day, nav, nav, nav, nav),
        )
        hist += 1
    conn.commit()
    return {"schemes": schemes, "history_rows": hist}


def download_nav_open(timeout: int = 90) -> str:
    r = requests.get(
        NAV_OPEN_URL,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain,*/*"},
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def run(
    db_path: Path,
    *,
    log_fn: Optional[Callable[[str], None]] = None,
    text: Optional[str] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda m: print(m))
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        log("[mf] downloading AMFI NAVOpen.txt …")
        text = download_nav_open()
    rows = parse_nav_open_text(text)
    log(f"[mf] parsed {len(rows)} open-ended scheme rows")
    conn = sqlite3.connect(str(db_path), timeout=60.0)
    try:
        stats = upsert_schemes_and_history(conn, rows)
    finally:
        conn.close()
    direct = sum(1 for r in rows if r.get("plan_kind") == "direct_growth")
    out = {
        **stats,
        "direct_growth": direct,
        "categories": len({r["category"] for r in rows}),
    }
    log(f"[mf] upsert complete: {out}")
    return out


def history_row_count(conn: sqlite3.Connection, scheme_code: str) -> int:
    cur = conn.execute(
        "SELECT COUNT(*) FROM mf_nav_history WHERE scheme_code = ?",
        (str(scheme_code),),
    )
    return int(cur.fetchone()[0] or 0)


def upsert_nav_points(
    conn: sqlite3.Connection,
    scheme_code: str,
    points: list[tuple[str, float]],
) -> int:
    """points: list of (YYYY-MM-DD, nav)."""
    setup_db(conn)
    n = 0
    code = str(scheme_code)
    for day, nav in points:
        if nav is None or float(nav) <= 0:
            continue
        v = float(nav)
        d = str(day)[:10]
        conn.execute(
            """
            INSERT OR REPLACE INTO mf_nav_history
            (scheme_code, Date, Open, High, Low, Close, Volume)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (code, d, v, v, v, v),
        )
        n += 1
    conn.commit()
    return n


def fetch_history_backfill(
    scheme_code: str,
    *,
    days: int = HISTORY_BACKFILL_DAYS,
    timeout: int = 45,
) -> list[tuple[str, float]]:
    """Fetch recent NAV history for one scheme (AMFI scheme code via mfapi)."""
    url = MFAPI_HISTORY_URL.format(code=str(scheme_code).strip())
    r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    cutoff = (datetime.now(IST).date() - timedelta(days=max(1, int(days)))).isoformat()
    out: list[tuple[str, float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        day = _parse_nav_date(str(item.get("date") or ""))
        if not day or day < cutoff:
            continue
        try:
            nav = float(item.get("nav"))
        except (TypeError, ValueError):
            continue
        if nav > 0:
            out.append((day, nav))
    return out


def ensure_history(
    conn: sqlite3.Connection,
    scheme_code: str,
    *,
    thin_below: int = HISTORY_THIN_ROWS,
    log_fn: Optional[Callable[[str], None]] = None,
) -> int:
    """If history is thin, backfill up to ~90 days. Returns rows written."""
    setup_db(conn)
    code = str(scheme_code).strip()
    if history_row_count(conn, code) >= thin_below:
        return 0
    log = log_fn or (lambda _m: None)
    try:
        points = fetch_history_backfill(code)
    except Exception as exc:
        log(f"[mf] backfill failed for {code}: {exc}")
        return 0
    written = upsert_nav_points(conn, code, points)
    if written:
        log(f"[mf] backfilled {written} NAV rows for {code}")
    return written
