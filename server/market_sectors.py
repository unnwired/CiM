"""
Market sector taxonomy: 12 NSE-style macro sectors + Unclassified.
Raw nse_sector / nse_industry (exchange, Screener, etc.) are remapped via keyword rules.
symbol_overrides / rules in data/sector_mapping.json still apply first; outputs are always macro labels.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

UNCLASSIFIED = "Unclassified"

# Twelve macro-economic sectors (NSE index style). Order is fixed for UI / docs.
MACRO_ECONOMIC_SECTORS: List[str] = [
    "Commodities",
    "Consumer Discretionary",
    "Energy",
    "Fast Moving Consumer Goods (FMCG)",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Information Technology",
    "Services",
    "Telecommunication",
    "Utilities",
    "Diversified",
]

# Persisted schema bump remaps canonical_sectors in sector_mapping.json on load.
MACRO_SECTOR_SCHEMA_VERSION = 2

# Backward-compatible alias (server / callers).
CANONICAL_MARKET_SECTORS = MACRO_ECONOMIC_SECTORS

_FMCG = "Fast Moving Consumer Goods (FMCG)"

# First matching rule wins (list is ordered: more specific before broader).
_MACRO_KEYWORD_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Diversified", (" diversified ", " conglomerate ", " multi-sector ")),
    (
        "Telecommunication",
        (
            " telecommunication ",
            " telecom ",
            " wireless ",
            " communication services ",
        ),
    ),
    (
        "Information Technology",
        (
            " information technology ",
            " it enabled ",
            " software & consulting ",
            " software and consulting ",
            " it services ",
            " it consulting ",
            " computers - software ",
            " computers-software ",
            " technology services ",
            " electronic technology ",
            " cyber security ",
            " cloud ",
            " analytics ",
            " digital ",
        ),
    ),
    (
        "Financial Services",
        (
            " financial services ",
            " financial service ",
            " finance ",
            " banking ",
            " bank ",
            " banks ",
            " insurance ",
            " nbfc ",
            " asset management ",
            " capital markets ",
            " stock broking ",
            " fintech ",
            " housing finance ",
            " mutual fund ",
            " lending ",
        ),
    ),
    (
        "Healthcare",
        (
            " healthcare ",
            " pharmaceutical ",
            " pharma ",
            " hospital ",
            " diagnostic ",
            " biotechnology ",
            " health services ",
            " health technology ",
            " drugs ",
            " drug ",
        ),
    ),
    (
        "Energy",
        (
            " oil, gas ",
            " oil gas ",
            " oil & gas ",
            " petroleum ",
            " refineries ",
            " refining ",
            " energy mineral ",
            " exploration & production ",
            " exploration and production ",
            " lng ",
            " cng ",
            " coal ",
            " oil gas & consumable fuels ",
        ),
    ),
    (
        "Utilities",
        (
            " utilities ",
            " utility ",
            " electric ",
            " power distribution ",
            " power transmission ",
            " integrated power ",
            " gas distribution ",
            " water supply ",
            " renewable energy ",
            " nuclear power ",
            " hydro ",
            " power ",
        ),
    ),
    (
        "Fast Moving Consumer Goods (FMCG)",
        (
            " fmcg ",
            " consumer non-durables ",
            " food products ",
            " beverages ",
            " tobacco ",
            " personal care ",
            " household products ",
            " packaged foods ",
            " staples ",
            " fast moving consumer ",
        ),
    ),
    (
        "Consumer Discretionary",
        (
            " consumer durables ",
            " consumer discretionary ",
            " automobile ",
            " auto components ",
            " retail trade ",
            " retail ",
            " textiles ",
            " apparel ",
            " leisure ",
            " hotels ",
            " media & ",
            " media and ",
            " entertainment ",
            " realty ",
            " construction materials ",
            " consumer services ",
            " wholesale ",
        ),
    ),
    (
        "Commodities",
        (
            " commodities ",
            " metals & mining ",
            " metals and mining ",
            " steel ",
            " aluminium ",
            " aluminum ",
            " zinc ",
            " copper ",
            " non-energy mineral ",
            " agro commodities ",
            " agricultural ",
            " fertilizers ",
            " pesticides ",
            " mining ",
            " petrochemical ",
        ),
    ),
    (
        "Industrials",
        (
            " capital goods ",
            " industrials ",
            " machinery ",
            " electrical equipment ",
            " building products ",
            " aerospace ",
            " defence ",
            " defense ",
            " cement ",
            " chemicals ",
            " process industries ",
            " industrial services ",
            " producer manufacturing ",
            " engineering ",
            " shipbuilding ",
        ),
    ),
    (
        "Services",
        (
            " commercial services ",
            " distribution services ",
            " transportation ",
            " logistics ",
            " courier ",
            " education services ",
            " professional services ",
            " business services ",
            " outsourcing ",
            " administrative ",
            " consulting ",
        ),
    ),
]


def mapping_path(data_dir: Path) -> Path:
    return data_dir / "sector_mapping.json"


def default_mapping_dict() -> Dict[str, Any]:
    return {
        "version": 1,
        "rules": [],
        "symbol_overrides": {},
        "use_exchange_labels": True,
        "macro_sector_schema_version": MACRO_SECTOR_SCHEMA_VERSION,
    }


def _canonical_sectors_default() -> List[str]:
    return list(MACRO_ECONOMIC_SECTORS) + [UNCLASSIFIED]


def ensure_default_mapping_file(data_dir: Path) -> None:
    p = mapping_path(data_dir)
    if p.exists():
        return
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(
            {
                **default_mapping_dict(),
                "canonical_sectors": _canonical_sectors_default(),
                "use_exchange_labels": True,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def load_mapping(data_dir: Path) -> Dict[str, Any]:
    ensure_default_mapping_file(data_dir)
    p = mapping_path(data_dir)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = default_mapping_dict()
    if "symbol_overrides" not in data or not isinstance(data["symbol_overrides"], dict):
        data["symbol_overrides"] = {}
    if "rules" not in data or not isinstance(data["rules"], list):
        data["rules"] = []
    if int(data.get("macro_sector_schema_version", 0)) < MACRO_SECTOR_SCHEMA_VERSION:
        data["canonical_sectors"] = _canonical_sectors_default()
        data["macro_sector_schema_version"] = MACRO_SECTOR_SCHEMA_VERSION
        save_mapping(data_dir, data)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("canonical_sectors", _canonical_sectors_default())
    if "use_exchange_labels" not in data:
        data["use_exchange_labels"] = True
    return data


def save_mapping(data_dir: Path, data: Dict[str, Any]) -> None:
    cs = data.get("canonical_sectors")
    if not isinstance(cs, list) or len(cs) == 0:
        cs = _canonical_sectors_default()
    out: Dict[str, Any] = {
        "version": int(data.get("version", 1)),
        "canonical_sectors": cs,
        "use_exchange_labels": bool(data.get("use_exchange_labels", True)),
        "macro_sector_schema_version": int(data.get("macro_sector_schema_version", MACRO_SECTOR_SCHEMA_VERSION)),
        "rules": data.get("rules") or [],
        "symbol_overrides": data.get("symbol_overrides") or {},
    }
    if not isinstance(out["rules"], list):
        out["rules"] = []
    if not isinstance(out["symbol_overrides"], dict):
        out["symbol_overrides"] = {}
    sym_ov = {}
    for k, v in out["symbol_overrides"].items():
        if not k or v is None:
            continue
        ku = str(k).strip().upper()
        vs = str(v).strip()
        if ku and vs:
            sym_ov[ku] = vs
    out["symbol_overrides"] = sym_ov
    p = mapping_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def ensure_screener_sector_columns(db_path: Path) -> None:
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(screener)")
        cols = {r[1] for r in cur.fetchall()}
        if "nse_sector" not in cols:
            cur.execute("ALTER TABLE screener ADD COLUMN nse_sector TEXT")
        if "nse_industry" not in cols:
            cur.execute("ALTER TABLE screener ADD COLUMN nse_industry TEXT")
        conn.commit()
    finally:
        conn.close()


def ensure_screener_isin_column(db_path: Path) -> None:
    """ISIN links screener rows to BSE / cross-exchange industry tables."""
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(screener)")
        cols = {r[1] for r in cur.fetchall()}
        if "isin" not in cols:
            cur.execute("ALTER TABLE screener ADD COLUMN isin TEXT")
        conn.commit()
    finally:
        conn.close()


def _field_value(field: str, nse_sector: Optional[str], nse_industry: Optional[str]) -> str:
    f = (field or "industry").lower().strip()
    raw = nse_industry if f == "industry" else nse_sector
    if raw is None:
        return ""
    return str(raw).strip()


def remap_to_macro_sector(label: str) -> str:
    """
    Map any industry / sector / breadcrumb string to one of MACRO_ECONOMIC_SECTORS or Unclassified.
    """
    if not label or not str(label).strip():
        return UNCLASSIFIED
    t = " ".join(str(label).split())
    tl = t.lower()
    if tl == UNCLASSIFIED.lower():
        return UNCLASSIFIED
    for canon in MACRO_ECONOMIC_SECTORS:
        if tl == canon.lower():
            return canon
    if "fmcg" in tl or "fast moving consumer" in tl:
        return _FMCG
    if tl in ("it", "information technology"):
        return "Information Technology"
    low = f" {tl} "
    if not low.strip():
        return UNCLASSIFIED
    for macro, keywords in _MACRO_KEYWORD_RULES:
        for kw in keywords:
            if kw in low:
                return macro
    return UNCLASSIFIED


def resolve_market_sector(
    symbol: str,
    nse_sector: Optional[str],
    nse_industry: Optional[str],
    mapping: Dict[str, Any],
) -> str:
    sym_u = str(symbol or "").strip().upper()
    overrides = mapping.get("symbol_overrides") or {}
    if sym_u and sym_u in overrides:
        v = str(overrides[sym_u]).strip()
        return remap_to_macro_sector(v) if v else UNCLASSIFIED

    ns = (nse_sector or "").strip() if nse_sector else ""
    ni = (nse_industry or "").strip() if nse_industry else ""

    for rule in mapping.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        field = rule.get("field", "industry")
        rtype = (rule.get("type") or "contains").lower().strip()
        pattern = rule.get("pattern")
        target = rule.get("sector")
        if pattern is None or target is None:
            continue
        pattern_s = str(pattern).strip()
        target_s = str(target).strip()
        if not pattern_s or not target_s:
            continue
        hay = _field_value(field, ns or None, ni or None)
        if rtype == "equals":
            if hay.lower() == pattern_s.lower():
                return remap_to_macro_sector(target_s)
        elif rtype == "regex":
            try:
                if re.search(pattern_s, hay, flags=re.IGNORECASE):
                    return remap_to_macro_sector(target_s)
            except re.error:
                continue
        else:  # contains
            if pattern_s.lower() in hay.lower():
                return remap_to_macro_sector(target_s)

    if mapping.get("use_exchange_labels", True):
        blob = " ".join(x for x in (ni, ns) if x).strip()
        if blob:
            return remap_to_macro_sector(blob)

    return UNCLASSIFIED


def symbol_set_for_market_sectors(
    data_dir: Path,
    db_path: Path,
    sector_names: List[str],
) -> Optional[Set[str]]:
    want = {str(s).strip() for s in (sector_names or []) if str(s).strip()}
    if not want:
        return None
    if not db_path.exists():
        return set()
    mapping = load_mapping(data_dir)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol, nse_sector, nse_industry FROM screener")
        rows = cur.fetchall()
    finally:
        conn.close()
    out: Set[str] = set()
    for row in rows:
        sym, se, ind = row[0], row[1], row[2]
        ms = resolve_market_sector(sym, se, ind, mapping)
        if ms in want:
            out.add(str(sym).strip().upper())
    return out
