"""
Market sector taxonomy: Nifty index ∪ industry tags (multi-tag).

Canonical labels come from index_industry_sectors.sector tag specs.
symbol_overrides / rules in data/sector_mapping.json still apply.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    from server import index_industry_sectors as iis
except ImportError:  # packages\server on sys.path (unit tests)
    import index_industry_sectors as iis

UNCLASSIFIED = iis.UNCLASSIFIED

# Backward-compatible aliases used by older tests / Admin copy.
AUTO_AND_AUTO_COMPONENTS = "Automobile and Auto Components"
AUTOMOBILES = "Automobiles"
CONSUMER_DISCRETIONARY = "Consumer Discretionary"

# New primary taxonomy (index ∪ industry).
MACRO_ECONOMIC_SECTORS: List[str] = list(iis.SECTOR_TAG_ORDER)
CANONICAL_MARKET_SECTORS = MACRO_ECONOMIC_SECTORS

# Persisted schema bump remaps canonical_sectors in sector_mapping.json on load.
MACRO_SECTOR_SCHEMA_VERSION = 5

# No dropdown nesting in the new taxonomy.
SECTOR_DROPDOWN_GROUPS: List[Dict[str, Any]] = []


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
    return canonical_sectors_for_ui()


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
        # Remap legacy override labels to new tags where possible.
        remapped = {}
        for k, v in (data.get("symbol_overrides") or {}).items():
            ku = str(k).strip().upper()
            norm = iis.normalize_tag_label(str(v)) if v is not None else None
            if ku and norm and norm != UNCLASSIFIED:
                remapped[ku] = norm
            elif ku and v is not None and str(v).strip():
                remapped[ku] = str(v).strip()
        data["symbol_overrides"] = remapped
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
        "macro_sector_schema_version": int(
            data.get("macro_sector_schema_version", MACRO_SECTOR_SCHEMA_VERSION)
        ),
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
            norm = iis.normalize_tag_label(vs)
            sym_ov[ku] = norm if norm else vs
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


def remap_to_macro_sector(label: str) -> str:
    """Normalize any label to a canonical tag (or Unclassified)."""
    norm = iis.normalize_tag_label(label)
    return norm if norm else UNCLASSIFIED


def canonical_sectors_for_ui() -> List[str]:
    return iis.canonical_sector_tags()


def sector_dropdown_groups_for_ui() -> List[Dict[str, Any]]:
    return [dict(g) for g in SECTOR_DROPDOWN_GROUPS]


def resolve_market_sectors(
    symbol: str,
    nse_sector: Optional[str],
    nse_industry: Optional[str],
    mapping: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> List[str]:
    return iis.resolve_market_sectors(
        symbol, nse_sector, nse_industry, mapping, data_dir=data_dir,
    )


def resolve_market_sector(
    symbol: str,
    nse_sector: Optional[str],
    nse_industry: Optional[str],
    mapping: Dict[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> str:
    """Joined multi-tag display string (e.g. 'PSU Bank · Bank · Financial Services')."""
    tags = resolve_market_sectors(
        symbol, nse_sector, nse_industry, mapping, data_dir=data_dir,
    )
    return iis.format_sector_tags(tags)


def symbol_set_for_market_sectors(
    data_dir: Path,
    db_path: Path,
    sector_names: List[str],
) -> Optional[Set[str]]:
    want_raw = {str(s).strip() for s in (sector_names or []) if str(s).strip()}
    if not want_raw:
        return None
    want: Set[str] = set()
    for name in want_raw:
        norm = iis.normalize_tag_label(name) or name
        want.add(norm)
    if not db_path.exists():
        return set()
    mapping = load_mapping(data_dir)
    iis.load_index_cores(data_dir)
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
        tags = resolve_market_sectors(sym, se, ind, mapping, data_dir=data_dir)
        if any(t in want for t in tags):
            out.add(str(sym).strip().upper())
    # Also include index-core members that may not be in screener yet.
    cores = iis.load_index_cores(data_dir)
    for tag in want:
        if tag == UNCLASSIFIED:
            continue
        out |= set(cores.get(tag) or set())
    return out


def ensure_index_sector_cores(data_dir: Path, db_path: Path) -> None:
    """Kick off index-core load / background refresh for hybrid tags."""
    iis.ensure_index_cores_async(data_dir, db_path)


def refresh_index_sector_cores(data_dir: Path, db_path: Path) -> Dict[str, Any]:
    return iis.refresh_index_cores(data_dir, db_path)
