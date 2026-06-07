"""
Populate screener.nse_sector / screener.nse_industry from free NSE/BSE master-style CSVs.

NSE: official index constituent CSVs on nsearchives.nseindia.com include columns
     Company Name, Industry, Symbol, Series, ISIN Code.

BSE: optional local CSV/XLSX under data/ (see parse_bse_style_table column hints in source).
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import urllib.request
import importlib.util
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _load_market_sectors():
    base = Path(__file__).resolve().parent / "market_sectors"
    path = base.with_suffix(".py")
    if not path.exists():
        path = base.with_suffix(".pyc")
    spec = importlib.util.spec_from_file_location("nse_pulse_market_sectors_ec", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load market_sectors from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


market_sectors = _load_market_sectors()

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Official NSE index constituent lists (Industry column). Union improves coverage vs a single file.
DEFAULT_NSE_INDUSTRY_CSV_URLS: Tuple[str, ...] = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymidsmallcap400list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap100list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap100list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_niftylargemidcap250list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500Value50_list.csv",
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500Quality50_list.csv",
)

DEFAULT_NSE_EQUITY_L_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def _fetch_url(url: str, user_agent: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_nse_index_industry_csv(
    text: str,
) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]]]:
    """
    Parse NSE index constituent CSV.
    Returns:
      by_symbol: SYMBOL (upper) -> (Industry, company name)
      by_isin:   ISIN (upper) -> (Industry, company name) for rows with ISIN (fills gaps by ISIN).
    """
    by_sym: Dict[str, Tuple[str, str]] = {}
    by_isin: Dict[str, Tuple[str, str]] = {}
    f = io.StringIO(text)
    reader = csv.DictReader(f, skipinitialspace=True)
    if not reader.fieldnames:
        return by_sym, by_isin
    fields = {h.strip(): h for h in reader.fieldnames}
    sym_key = fields.get("Symbol") or fields.get("SYMBOL")
    ind_key = fields.get("Industry") or fields.get("INDUSTRY")
    name_key = fields.get("Company Name") or fields.get("NAME") or fields.get("Security Name")
    isin_key = fields.get("ISIN Code") or fields.get("ISIN")
    if not ind_key:
        return by_sym, by_isin
    for row in reader:
        ind = (row.get(ind_key) or "").strip()
        if not ind:
            continue
        nm = (row.get(name_key) or "").strip() if name_key else ""
        if sym_key:
            sym = (row.get(sym_key) or "").strip().upper()
            if sym:
                by_sym[sym] = (ind, nm)
        if isin_key:
            isin = (row.get(isin_key) or "").strip().upper()
            if isin.startswith("IN"):
                by_isin[isin] = (ind, nm)
    return by_sym, by_isin


def merge_nse_industry_maps(
    urls: Iterable[str], user_agent: str
) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]], List[str]]:
    merged_sym: Dict[str, Tuple[str, str]] = {}
    merged_isin: Dict[str, Tuple[str, str]] = {}
    errors: List[str] = []
    for url in urls:
        u = str(url).strip()
        if not u:
            continue
        try:
            text = _fetch_url(u, user_agent=user_agent)
            if text.lstrip().startswith("<!"):
                errors.append(f"{u} (not CSV)")
                continue
            part_sym, part_isin = parse_nse_index_industry_csv(text)
            if not part_sym and not part_isin:
                errors.append(f"{u} (no rows parsed)")
                continue
            merged_sym.update(part_sym)
            merged_isin.update(part_isin)
        except Exception as e:
            errors.append(f"{u} ({e})")
    return merged_sym, merged_isin, errors


def parse_nse_equity_l_isin(text: str) -> Dict[str, str]:
    """NSE EQUITY_L: EQ-series symbol -> ISIN (upper)."""
    out: Dict[str, str] = {}
    f = io.StringIO(text)
    reader = csv.DictReader(f, skipinitialspace=True)
    if not reader.fieldnames:
        return out
    fh = {h.strip(): h for h in reader.fieldnames}
    sym_k = fh.get("SYMBOL")
    isin_k = fh.get("ISIN NUMBER") or fh.get("ISIN")
    ser_k = fh.get("SERIES") or fh.get("Series")
    if not sym_k or not isin_k:
        return out
    for row in reader:
        if ser_k and (row.get(ser_k) or "").strip().upper() != "EQ":
            continue
        sym = (row.get(sym_k) or "").strip().upper()
        isin = (row.get(isin_k) or "").strip().upper()
        if sym and isin.startswith("IN"):
            out[sym] = isin
    return out


def sync_isin_column(db_path: Path, symbol_to_isin: Dict[str, str]) -> int:
    """Write ISIN for screener symbols present in symbol_to_isin."""
    if not db_path.exists() or not symbol_to_isin:
        return 0
    conn = sqlite3.connect(str(db_path))
    n = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM screener")
        have = {str(r[0]).strip().upper() for r in cur.fetchall()}
        for sym, isin in symbol_to_isin.items():
            su = sym.strip().upper()
            if su not in have:
                continue
            cur.execute("UPDATE screener SET isin = ? WHERE symbol = ?", (isin, su))
            if cur.rowcount and cur.rowcount > 0:
                n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n


def _norm_header(h: str) -> str:
    return "".join(ch.lower() for ch in h if ch.isalnum())


def parse_bse_style_table(path: Path) -> Tuple[Dict[str, Tuple[str, str]], Dict[str, Tuple[str, str]]]:
    """
    Parse a user-supplied BSE-style CSV/XLSX.
    Returns (by_symbol, by_isin) when Industry + ISIN columns exist.
    """
    try:
        import pandas as pd
    except ImportError:
        return {}, {}

    suf = path.suffix.lower()
    if suf in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        df = None
        for enc in ("utf-8", "utf-8-sig", "latin1", "cp1252"):
            try:
                df = pd.read_csv(path, dtype=str, encoding=enc)
                break
            except Exception:
                pass
        if df is None:
            return {}, {}
    df.columns = [str(c).strip() for c in df.columns]
    norm_map = {_norm_header(c): c for c in df.columns}

    def pick(*candidates: str) -> Optional[str]:
        for cand in candidates:
            k = _norm_header(cand)
            if k in norm_map:
                return norm_map[k]
        return None

    sym_col = pick("SYMBOL", "Symbol", "SC_CODE", "Scrip Code", "Security Id", "SecurityId")
    ind_col = pick("Industry", "Industry New", "INDUSTRY", "Sector", "INDUSTRY_NAME")
    name_col = pick("Security Name", "NAME", "Company Name", "SCR_NAME")
    isin_col = pick("ISIN", "ISIN Code", "ISIN_NO", "ISINNumber")
    if not ind_col:
        return {}, {}
    if not sym_col and not isin_col:
        return {}, {}

    by_sym: Dict[str, Tuple[str, str]] = {}
    by_isin: Dict[str, Tuple[str, str]] = {}
    for _, row in df.iterrows():
        ind = str(row.get(ind_col) or "").strip()
        if not ind:
            continue
        nm = str(row.get(name_col) or "").strip() if name_col else ""
        if sym_col:
            sym = str(row.get(sym_col) or "").strip().upper()
            if sym:
                by_sym[sym] = (ind, nm)
        if isin_col:
            isin = str(row.get(isin_col) or "").strip().upper()
            if isin.startswith("IN"):
                by_isin[isin] = (ind, nm)
    return by_sym, by_isin


def apply_classification_to_db(
    db_path: Path,
    by_symbol: Dict[str, Tuple[str, str]],
    *,
    only_symbols_in_db: bool = True,
) -> Tuple[int, int, Set[str]]:
    """
    Set nse_sector = nse_industry = Industry text from exchange (single trusted label).
    Returns: (rows_updated, symbols_in_map, distinct_industries)
    """
    if not db_path.exists():
        return 0, 0, set()
    conn = sqlite3.connect(str(db_path))
    industries: Set[str] = set()
    n = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM screener")
        have = {str(r[0]).strip().upper() for r in cur.fetchall()}
        for sym, (ind, _nm) in by_symbol.items():
            su = sym.strip().upper()
            if only_symbols_in_db and su not in have:
                continue
            if su not in have:
                continue
            industries.add(ind)
            cur.execute(
                "UPDATE screener SET nse_sector = ?, nse_industry = ? WHERE symbol = ?",
                (ind, ind, su),
            )
            if cur.rowcount and cur.rowcount > 0:
                n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n, len(by_symbol), industries


def apply_industry_by_isin(
    db_path: Path,
    by_isin: Dict[str, Tuple[str, str]],
    *,
    only_if_industry_empty: bool = True,
) -> Tuple[int, Set[str]]:
    """
    For screener rows with a known ISIN, set nse_sector / nse_industry from by_isin when still blank.
    Returns (rows_updated, industry labels touched).
    """
    if not db_path.exists() or not by_isin:
        return 0, set()
    touched: Set[str] = set()
    conn = sqlite3.connect(str(db_path))
    n = 0
    try:
        cur = conn.cursor()
        cur.execute("SELECT symbol, isin, nse_industry FROM screener")
        for row in cur.fetchall():
            sym, isin, ni = str(row[0]).strip().upper(), (row[1] or "").strip().upper(), (row[2] or "").strip()
            if only_if_industry_empty and ni:
                continue
            if not isin or isin not in by_isin:
                continue
            ind = by_isin[isin][0]
            cur.execute(
                "UPDATE screener SET nse_sector = ?, nse_industry = ? WHERE symbol = ?",
                (ind, ind, sym),
            )
            if cur.rowcount and cur.rowcount > 0:
                n += cur.rowcount
                touched.add(ind)
        conn.commit()
    finally:
        conn.close()
    return n, touched


def refresh_canonical_sectors_from_db(data_dir: Path, db_path: Path) -> None:
    """Reset sector checklist to 12 macro buckets (raw labels are remapped at display time)."""
    update_sector_mapping_canonicals(data_dir, set())


def update_sector_mapping_canonicals(data_dir: Path, industries: Set[str]) -> None:
    """Keep sector_mapping canonical_sectors aligned with macro list + Unclassified (industries arg ignored)."""
    _ = industries  # Kept for callers; Market Sector is always one of 12 + Unclassified after remap.
    ms = market_sectors
    ms.ensure_default_mapping_file(data_dir)
    data = ms.load_mapping(data_dir)
    u = ms.UNCLASSIFIED
    data["canonical_sectors"] = list(ms.MACRO_ECONOMIC_SECTORS) + [u]
    data["use_exchange_labels"] = True
    data["macro_sector_schema_version"] = ms.MACRO_SECTOR_SCHEMA_VERSION
    ms.save_mapping(data_dir, data)


def run_sync(
    data_dir: Path,
    db_path: Path,
    *,
    nse_urls: Optional[List[str]] = None,
    bse_local_path: Optional[Path] = None,
    user_agent: str = DEFAULT_USER_AGENT,
    refresh_canonical: bool = True,
    nse_equity_l_url: Optional[str] = None,
    skip_equity_l: bool = False,
) -> Dict[str, Any]:
    market_sectors.ensure_screener_isin_column(db_path)
    cfg = load_sync_config(data_dir)

    equity_note: Dict[str, Any] = {}
    n_isin_synced = 0
    if not skip_equity_l:
        el_url = str(nse_equity_l_url or cfg.get("nse_equity_l_url") or DEFAULT_NSE_EQUITY_L_URL).strip()
        try:
            el_text = _fetch_url(el_url, user_agent=user_agent, timeout=90)
            sym_isin = parse_nse_equity_l_isin(el_text)
            n_isin_synced = sync_isin_column(db_path, sym_isin)
            equity_note = {"url": el_url, "eq_symbols_with_isin": len(sym_isin), "screener_rows_updated": n_isin_synced}
        except Exception as e:
            equity_note = {"url": el_url, "error": str(e)}

    urls = list(nse_urls) if nse_urls else list(DEFAULT_NSE_INDUSTRY_CSV_URLS)
    nse_sym, nse_isin, nse_errors = merge_nse_industry_maps(urls, user_agent=user_agent)

    bse_sym: Dict[str, Tuple[str, str]] = {}
    bse_isin: Dict[str, Tuple[str, str]] = {}
    bse_note = None
    if bse_local_path and Path(bse_local_path).is_file():
        bse_sym, bse_isin = parse_bse_style_table(Path(bse_local_path))
        bse_note = {
            "path": str(bse_local_path),
            "rows_by_symbol": len(bse_sym),
            "rows_by_isin": len(bse_isin),
        }

    # Symbol path: BSE first, then NSE index (NSE wins on duplicate keys).
    combined_sym: Dict[str, Tuple[str, str]] = dict(bse_sym)
    combined_sym.update(nse_sym)

    rows_by_symbol, symbols_in_feed, industries_sym = apply_classification_to_db(db_path, combined_sym)

    # ISIN path: BSE file first, then NSE index ISIN map (NSE wins).
    merged_isin: Dict[str, Tuple[str, str]] = dict(bse_isin)
    merged_isin.update(nse_isin)

    rows_by_isin, industries_isin = apply_industry_by_isin(
        db_path, merged_isin, only_if_industry_empty=True
    )

    all_labels = {t[0] for t in combined_sym.values() if t[0]} | {t[0] for t in merged_isin.values() if t[0]}
    all_labels |= industries_sym | industries_isin

    if refresh_canonical and all_labels:
        update_sector_mapping_canonicals(data_dir, all_labels)

    return {
        "status": "ok",
        "rows_updated": rows_by_symbol + rows_by_isin,
        "rows_updated_by_symbol": rows_by_symbol,
        "rows_updated_by_isin": rows_by_isin,
        "symbols_in_feed": symbols_in_feed,
        "distinct_industries": len(all_labels),
        "nse_urls_used": len(urls),
        "nse_errors": nse_errors,
        "bse": bse_note,
        "equity_l": equity_note,
        "isin_column_rows_updated": n_isin_synced,
    }


def config_path(data_dir: Path) -> Path:
    return data_dir / "exchange_classification_config.json"


def load_sync_config(data_dir: Path) -> Dict[str, Any]:
    p = config_path(data_dir)
    if not p.is_file():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
