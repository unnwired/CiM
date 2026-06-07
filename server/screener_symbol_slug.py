"""
Map NSE / TradingView symbols to Screener.in company URL path slugs.

Screener uses hyphenated folder names (e.g. BAJAJ-AUTO). TradingView/NSE often use
BAJAJAUTO or BAJAJ_AUTO for the same issuer.
"""
from __future__ import annotations

from urllib.parse import quote

# NSE / TV symbol -> Screener.in /company/{slug}/ folder name
SCREENER_COMPANY_SLUG_ALIASES: dict[str, str] = {
    "BAJAJ_AUTO": "BAJAJ-AUTO",
    "BAJAJAUTO": "BAJAJ-AUTO",
    "M_M": "M&M",
}


def screener_company_slug_candidates(symbol: str) -> list[str]:
    """Ordered slugs to try when fetching HTML (most likely Screener match first)."""
    s = str(symbol or "").strip().upper()
    if not s:
        return []

    out: list[str] = []

    def add(slug: str) -> None:
        if slug and slug not in out:
            out.append(slug)

    alias = SCREENER_COMPANY_SLUG_ALIASES.get(s)
    if alias:
        add(alias)

    # TradingView: BAJAJAUTO -> Screener: BAJAJ-AUTO
    if (
        s.endswith("AUTO")
        and len(s) > 4
        and "-" not in s
        and "_" not in s
        and f"{s[:-4]}-AUTO" not in out
    ):
        add(f"{s[:-4]}-AUTO")

    if "_" in s:
        add(s.replace("_", "-"))

    add(s)
    return out


def screener_company_slug(symbol: str) -> str:
    candidates = screener_company_slug_candidates(symbol)
    return candidates[0] if candidates else ""


def screener_company_path(symbol: str, basis: str, *, consolidated: bool) -> str:
    slug = screener_company_slug(symbol)
    if not slug:
        return ""
    encoded = quote(slug, safe="")
    if consolidated:
        return f"/company/{encoded}/consolidated/"
    return f"/company/{encoded}/"


def screener_company_page_url(symbol: str, basis: str, *, consolidated: bool = False) -> str:
    path = screener_company_path(symbol, basis, consolidated=consolidated)
    return f"https://www.screener.in{path}" if path else ""


def screener_company_page_url_for_slug(slug: str, *, consolidated: bool = False) -> str:
    s = str(slug or "").strip()
    if not s:
        return ""
    encoded = quote(s, safe="")
    if consolidated:
        return f"https://www.screener.in/company/{encoded}/consolidated/"
    return f"https://www.screener.in/company/{encoded}/"
