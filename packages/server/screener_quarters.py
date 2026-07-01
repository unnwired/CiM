"""
Fetch and persist Screener.in Quarterly Results (#quarters) for company pages.

Lazy persist: scrape only when explicitly requested (first expand or manual refresh).
Uses optional cookies from data/screener_session.json (see screener_login.py).
"""
from __future__ import annotations

import html as html_module
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.error

from bs4 import BeautifulSoup

from screener_sector_fallback import load_screener_cookie_header, _http_get
from screener_symbol_slug import (
    screener_company_page_url as _screener_page_url,
    screener_company_page_url_for_slug,
    screener_company_slug_candidates,
)

BASIS_STANDALONE = "standalone"
BASIS_CONSOLIDATED = "consolidated"
VALID_BASES = {BASIS_STANDALONE, BASIS_CONSOLIDATED}

SKIP_ROW_LABELS = frozenset({"raw pdf", "related party"})

SCREENER_SITE = "https://www.screener.in"


def _screener_absolute_url(href: str) -> Optional[str]:
    h = (href or "").strip()
    if not h:
        return None
    if h.startswith("//"):
        return f"https:{h}"
    if h.startswith("/"):
        return f"{SCREENER_SITE}{h}"
    return h


def _is_quarter_pdf_anchor(a) -> bool:
    href = (a.get("href") or "").strip().lower()
    aria = (a.get("aria-label") or "").strip().lower()
    if "pdf" in aria or "pdf" in href:
        return True
    if "/company/source/quarter/" in href:
        return True
    icon = a.find("i", class_=lambda c: c and "file-pdf" in str(c))
    return icon is not None


def ensure_screener_quarterly_table(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS screener_quarterly (
                symbol TEXT NOT NULL,
                basis TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source_url TEXT,
                PRIMARY KEY (symbol, basis)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_screener_quarterly_fetched "
            "ON screener_quarterly(fetched_at)"
        )
        conn.commit()
    finally:
        conn.close()


def screener_company_page_url(symbol: str, basis: str = BASIS_STANDALONE) -> str:
    b = _normalize_basis(basis)
    return _screener_page_url(symbol, b, consolidated=(b == BASIS_CONSOLIDATED))


def screener_company_url(symbol: str, basis: str = BASIS_STANDALONE) -> str:
    base = screener_company_page_url(symbol, basis)
    return f"{base}#quarters" if base else ""


def _normalize_basis(basis: Optional[str]) -> str:
    b = str(basis or BASIS_STANDALONE).strip().lower()
    return b if b in VALID_BASES else BASIS_STANDALONE


def _cell_label(td) -> str:
    if td is None:
        return ""
    btn = td.find("button")
    if btn:
        text = btn.get_text(" ", strip=True)
    else:
        text = td.get_text(" ", strip=True)
    text = re.sub(r"\s*\+\s*$", "", text).strip()
    return html_module.unescape(text)


def _cell_value(td) -> Optional[str]:
    if td is None:
        return None
    for a in td.find_all("a", href=True):
        if _is_quarter_pdf_anchor(a):
            return _screener_absolute_url(a.get("href", ""))
    text = td.get_text(" ", strip=True)
    if not text or text in {"-", "—"}:
        return None
    return html_module.unescape(text)


def parse_quarters_section(html: str) -> Dict[str, Any]:
    """Parse #quarters table into periods + row matrix matching Screener UI."""
    soup = BeautifulSoup(html, "html.parser")
    section = soup.find("section", id="quarters")
    if not section:
        raise ValueError("Quarterly Results section not found on page")

    unit_note = ""
    for p in section.find_all("p"):
        t = p.get_text(" ", strip=True)
        if "Crores" in t or "Cr." in t or "Rs." in t:
            unit_note = t
            break

    table = section.find("table", class_="data-table") or section.find("table")
    if not table:
        raise ValueError("Quarterly Results table not found")

    thead = table.find("thead")
    tbody = table.find("tbody")
    if not thead or not tbody:
        raise ValueError("Quarterly Results table is incomplete")

    header_row = thead.find("tr")
    if not header_row:
        raise ValueError("Quarterly Results header row missing")

    periods: List[Dict[str, str]] = []
    for th in header_row.find_all("th")[1:]:
        label = th.get_text(" ", strip=True)
        if not label:
            continue
        periods.append({
            "period": label,
            "date_key": th.get("data-date-key") or "",
        })

    if not periods:
        raise ValueError("No quarter columns found")

    rows_out: List[Dict[str, Any]] = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        label = _cell_label(cells[0])
        if not label:
            continue
        label_lower = label.lower()
        if any(skip in label_lower for skip in SKIP_ROW_LABELS):
            if "raw pdf" in label_lower:
                pdf_vals: List[Optional[str]] = []
                for col_idx, td in enumerate(cells[1:]):
                    if col_idx >= len(periods):
                        break
                    v = _cell_value(td)
                    pdf_vals.append(v)
                    if v:
                        periods[col_idx]["pdf_url"] = v
                if len(pdf_vals) < len(periods):
                    pdf_vals.extend([None] * (len(periods) - len(pdf_vals)))
                elif len(pdf_vals) > len(periods):
                    pdf_vals = pdf_vals[: len(periods)]
                rows_out.append({
                    "label": "Raw PDF",
                    "slug": "raw_pdf",
                    "values": pdf_vals,
                    "is_pdf": True,
                })
            continue

        slug = re.sub(r"[^a-z0-9]+", "_", label_lower).strip("_")
        values = [_cell_value(td) for td in cells[1:]]
        # Pad/trim to period count
        if len(values) < len(periods):
            values.extend([None] * (len(periods) - len(values)))
        elif len(values) > len(periods):
            values = values[: len(periods)]

        rows_out.append({
            "label": label,
            "slug": slug or label_lower,
            "values": values,
            "is_pdf": False,
        })

    if not rows_out:
        raise ValueError("No quarterly metric rows parsed")

    return {
        "unit_note": unit_note,
        "periods": periods,
        "rows": rows_out,
    }


_CITATION_REF_RE = re.compile(r"\[\d+\]")


def _clean_profile_text(text: str) -> str:
    t = _CITATION_REF_RE.sub("", str(text or ""))
    t = re.sub(r"\s*Read More\s*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _analysis_column_items(col) -> Tuple[str, List[str]]:
    """Return ('pros'|'cons'|'', bullet lines) for one analysis flex column."""
    if col is None:
        return "", []
    lines = [ln.strip() for ln in col.get_text("\n", strip=True).split("\n") if ln.strip()]
    if not lines:
        return "", []
    header = lines[0].lower()
    kind = ""
    if header.startswith("pros"):
        kind = "pros"
    elif header.startswith("cons"):
        kind = "cons"
    items = [li.get_text(" ", strip=True) for li in col.find_all("li")]
    if not items:
        items = [
            ln for ln in lines[1:]
            if ln and not ln.startswith("*") and "machine generated" not in ln.lower()
        ]
    items = [_clean_profile_text(x) for x in items if _clean_profile_text(x)]
    return kind, items


def parse_company_profile(html: str) -> Dict[str, Any]:
    """
    About (.about), Key Points / business overview (.commentary),
    Pros & Cons (#analysis). Non-fatal: missing blocks return empty values.
    """
    soup = BeautifulSoup(html, "html.parser")
    about = ""
    about_el = soup.find(class_="about")
    if about_el:
        about = _clean_profile_text(about_el.get_text(" ", strip=True))

    key_points = ""
    commentary = soup.find(class_="commentary")
    if commentary:
        key_points = _clean_profile_text(commentary.get_text(" ", strip=True))
        key_points = re.sub(r"^Business Overview:\s*", "", key_points, flags=re.I)

    pros: List[str] = []
    cons: List[str] = []
    analysis = soup.find("section", id="analysis")
    if analysis:
        flex = analysis.find(
            "div",
            class_=lambda c: c and "flex-column-mobile" in c,
        )
        if flex:
            for col in flex.find_all("div", recursive=False):
                kind, items = _analysis_column_items(col)
                if kind == "pros":
                    pros = items
                elif kind == "cons":
                    cons = items

    return {
        "about": about,
        "key_points": key_points,
        "pros": pros,
        "cons": cons,
    }


def fetch_quarters_from_screener(symbol: str, basis: str, data_dir: Path) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("Symbol is required")
    b = _normalize_basis(basis)
    cookies = load_screener_cookie_header(data_dir)
    html = None
    url = ""
    tried: List[str] = []
    consolidated = b == BASIS_CONSOLIDATED
    for slug in screener_company_slug_candidates(sym):
        url = screener_company_page_url_for_slug(slug, consolidated=consolidated)
        tried.append(url)
        try:
            html = _http_get(url, cookies)
            break
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                continue
            raise
        except Exception:
            continue
    if html is None:
        detail = "; ".join(tried) if tried else "no URL"
        raise ValueError(f"Screener company page not found (HTTP 404). Tried: {detail}")
    parsed = parse_quarters_section(html)
    profile = parse_company_profile(html)
    parsed.update(profile)
    parsed["symbol"] = sym
    parsed["basis"] = b
    parsed["source_url"] = url
    parsed["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return parsed


def save_quarters(conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
    sym = str(payload.get("symbol") or "").strip().upper()
    basis = _normalize_basis(payload.get("basis"))
    if not sym:
        raise ValueError("Symbol is required")
    fetched_at = payload.get("fetched_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO screener_quarterly (symbol, basis, payload_json, fetched_at, source_url)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, basis) DO UPDATE SET
            payload_json = excluded.payload_json,
            fetched_at = excluded.fetched_at,
            source_url = excluded.source_url
        """,
        (
            sym,
            basis,
            json.dumps(payload, ensure_ascii=False),
            fetched_at,
            payload.get("source_url"),
        ),
    )
    conn.commit()


def load_quarters(conn: sqlite3.Connection, symbol: str, basis: str) -> Optional[Dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    b = _normalize_basis(basis)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT payload_json, fetched_at, source_url
        FROM screener_quarterly
        WHERE symbol = ? AND basis = ?
        """,
        (sym, b),
    )
    row = cur.fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[0])
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    payload["symbol"] = sym
    payload["basis"] = b
    payload["fetched_at"] = row[1]
    payload["source_url"] = row[2] or payload.get("source_url")
    return payload


def get_quarters(
    db_path: Path,
    data_dir: Path,
    symbol: str,
    basis: str,
    *,
    fetch_if_missing: bool = False,
    force_refresh: bool = False,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Returns (payload, status) where status is one of:
    cache | fetched | missing | error
    """
    sym = str(symbol or "").strip().upper()
    b = _normalize_basis(basis)
    if not sym:
        return None, "error"

    conn = sqlite3.connect(str(db_path))
    try:
        cached = load_quarters(conn, sym, b)
        if cached and not force_refresh:
            return cached, "cache"

        if not fetch_if_missing and not force_refresh:
            return None, "missing"

        try:
            fresh = fetch_quarters_from_screener(sym, b, data_dir)
            save_quarters(conn, fresh)
            return fresh, "fetched"
        except Exception as e:
            if cached:
                cached["refresh_error"] = str(e)
                return cached, "cache_stale"
            return {"symbol": sym, "basis": b, "error": str(e)}, "error"
    finally:
        conn.close()
