"""
Index ∪ industry Market Sector tags.

Each tag = Nifty sector/theme index constituents ∪ industry expansion (nse_industry /
nse_sector keywords). Symbols may carry multiple tags. Unclassified only when none match.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

UNCLASSIFIED = "Unclassified"

# Display order for UI / joined labels.
SECTOR_TAG_ORDER: List[str] = [
    "Auto",
    "IT",
    "FMCG",
    "Pharma",
    "Healthcare",
    "Metal",
    "Realty",
    "Energy",
    "Oil & Gas",
    "Infra",
    "Defence",
    "Bank",
    "PSU Bank",
    "Private Bank",
    "Financial Services",
    "Fin Ex-Bank",
    "Media",
    "Consumer Durables",
    "Consumption",
    "Chemicals",
    "Commodities",
    "Services",
    "Telecom",
    "PSE",
    "CPSE",
]

_TAG_RANK = {name: i for i, name in enumerate(SECTOR_TAG_ORDER)}

# Legacy macro labels → new tags (symbol_overrides / old mapping files).
LEGACY_SECTOR_ALIASES: Dict[str, str] = {
    "automobile and auto components": "Auto",
    "automobiles": "Auto",
    "consumer discretionary": "Consumption",
    "fast moving consumer goods (fmcg)": "FMCG",
    "fast moving consumer goods": "FMCG",
    "information technology": "IT",
    "industrials": "Infra",
    "utilities": "Energy",
    "telecommunication": "Telecom",
    "diversified": UNCLASSIFIED,
}

# Exact Screener industry/sector labels → tag(s). Avoids brittle substring traps
# (e.g. bare "Services" must not require matching inside "Financial Services").
_EXACT_LABEL_TAGS: Dict[str, Tuple[str, ...]] = {
    "chemicals": ("Chemicals", "Commodities"),
    "capital goods": ("Infra",),
    "construction": ("Infra",),
    "textiles": ("Consumption",),
    "telecommunication": ("Telecom",),
    "services": ("Services",),
    "utilities": ("Energy",),
    "diversified": (),
    "forest materials": ("Commodities",),
}


@dataclass(frozen=True)
class SectorTagSpec:
    label: str
    index_symbol: Optional[str]
    # Substrings matched against padded lowercase " nse_industry + nse_sector ".
    industry_keywords: Tuple[str, ...]


# Keyword rules are inclusive by design (overlap across tags is allowed).
# Blobs are punctuation-normalized (/, -, & → spaces) before matching.
SECTOR_TAG_SPECS: Tuple[SectorTagSpec, ...] = (
    SectorTagSpec(
        "Auto",
        "^CNXAUTO",
        (
            " automobile and auto components ",
            " auto components ",
            " auto component ",
            " automobiles ",
            " passenger cars ",
            " 2/3 wheelers ",
            " 2/3 wheeler ",
            " auto dealer ",
            " tyres ",
            " tire ",
            " two & three wheelers ",
            " two and three wheelers ",
            " tractors ",
            " commercial vehicles ",
            " construction vehicles ",
            " cycles ",
            " dealers commercial vehicles ",
        ),
    ),
    SectorTagSpec(
        "IT",
        "^CNXIT",
        (
            " information technology ",
            " it enabled ",
            " computers - software ",
            " computers software ",
            " software products ",
            " software & consulting ",
            " software and consulting ",
            " it services ",
            " it consulting ",
            " computers hardware ",
        ),
    ),
    SectorTagSpec(
        "FMCG",
        "^CNXFMCG",
        (
            " fast moving consumer goods ",
            " fmcg ",
            " packaged foods ",
            " personal care ",
            " household products ",
            " beverages ",
            " tobacco ",
            " edible oil ",
            " dairy products ",
            " breweries ",
            " tea & coffee ",
            " tea coffee ",
            " sugar ",
            " other agricultural products ",
        ),
    ),
    SectorTagSpec(
        "Pharma",
        "^CNXPHARMA",
        (
            " pharmaceuticals ",
            " pharmaceutical ",
            " pharma ",
            " drugs ",
            " biotechnology ",
        ),
    ),
    SectorTagSpec(
        "Healthcare",
        "NIFTY_HEALTHCARE.NS",
        (
            " healthcare ",
            " hospital ",
            " diagnostic ",
            " medical equipment ",
            " health services ",
            " health technology ",
            " healthcare research ",
        ),
    ),
    SectorTagSpec(
        "Metal",
        "^CNXMETAL",
        (
            " metals & mining ",
            " metals and mining ",
            " iron & steel ",
            " iron and steel ",
            " sponge iron ",
            " aluminium ",
            " aluminum ",
            " zinc ",
            " copper ",
            " ferro & silica ",
            " ferro silica ",
            " trading - metals ",
            " trading metals ",
            " castings & forgings ",
            " castings forgings ",
        ),
    ),
    SectorTagSpec(
        "Realty",
        "^CNXREALTY",
        (
            " realty ",
            " real estate ",
            " residential commercial projects ",
            " residential commercial projects ",
        ),
    ),
    SectorTagSpec(
        "Energy",
        "^CNXENERGY",
        (
            " power ",
            " power generation ",
            " power distribution ",
            " power transmission ",
            " integrated power ",
            " renewable ",
            " nuclear power ",
            " utilities power ",
            " oil gas & consumable fuels ",
            " oil gas consumable fuels ",
            " petroleum ",
            " refining ",
            " refiner ",
            " refineries ",
            " coal ",
            " lpg ",
            " cng ",
            " png ",
            " lng ",
            " gas transmission ",
            " gas marketing ",
            " oil equipment ",
            " oil storage ",
            " heavy electrical ",
            " solar ",
            " wind ",
            " waste management ",
            " water supply ",
        ),
    ),
    SectorTagSpec(
        "Oil & Gas",
        "NIFTY_OIL_GAS",
        (
            " oil gas & consumable fuels ",
            " oil gas consumable fuels ",
            " oil & gas ",
            " oil and gas ",
            " petroleum ",
            " refining ",
            " refiner ",
            " refineries ",
            " exploration & production ",
            " exploration and production ",
            " lubricants ",
            " offshore support ",
            " gas distribution ",
            " gas transmission ",
            " gas marketing ",
            " oil equipment ",
            " oil storage ",
            " lpg ",
            " cng ",
            " png ",
            " lng ",
        ),
    ),
    SectorTagSpec(
        "Infra",
        "^CNXINFRA",
        (
            " civil construction ",
            " infrastructure ",
            " road assets ",
            " road asset ",
            " construction materials ",
            " cement & cement ",
            " cement cement ",
            " engineering ",
            " heavy electrical ",
            " capital goods ",
            " industrial products ",
            " other industrial products ",
            " other electrical equipment ",
            " cables electricals ",
            " cables electrical ",
            " plastic products industrial ",
            " electrodes ",
            " refractories ",
            " abrasives ",
            " bearings ",
            " compressors ",
            " pumps & diesel ",
            " pumps diesel ",
            " glass industrial ",
            " packaging ",
            " construction ",
            " dredging ",
            " port & port ",
            " port port ",
            " ship building ",
            " shipbuilding ",
            " waste management ",
            " water supply ",
        ),
    ),
    SectorTagSpec(
        "Defence",
        "^CNXINDDEF",
        (
            " aerospace & defense ",
            " aerospace and defense ",
            " aerospace & defence ",
            " aerospace and defence ",
            " aerospace defense ",
            " aerospace defence ",
            " defence ",
            " defense ",
        ),
    ),
    SectorTagSpec(
        "Bank",
        "^NSEBANK",
        (
            " public sector bank ",
            " private sector bank ",
            " other bank ",
        ),
    ),
    SectorTagSpec(
        "PSU Bank",
        "^CNXPSUBANK",
        (" public sector bank ",),
    ),
    SectorTagSpec(
        "Private Bank",
        "NIFTY_PVT_BANK",
        (" private sector bank ",),
    ),
    SectorTagSpec(
        "Financial Services",
        "NIFTY_FIN_SERVICE",
        (
            " financial services ",
            " financial service ",
            " non banking financial ",
            " nbfc ",
            " insurance ",
            " asset management ",
            " capital markets ",
            " stockbroking ",
            " stock broking ",
            " fintech ",
            " housing finance ",
            " mutual fund ",
            " microfinance ",
            " investment company ",
            " other financial services ",
            " public sector bank ",
            " private sector bank ",
            " other bank ",
        ),
    ),
    SectorTagSpec(
        "Fin Ex-Bank",
        "NIFTY_FIN_EX_BANK",
        (
            " non banking financial ",
            " nbfc ",
            " insurance ",
            " asset management ",
            " capital markets ",
            " stockbroking ",
            " stock broking ",
            " fintech ",
            " housing finance ",
            " mutual fund ",
            " microfinance ",
            " investment company ",
            " other financial services ",
        ),
    ),
    SectorTagSpec(
        "Media",
        "^CNXMEDIA",
        (
            " media & entertainment ",
            " media and entertainment ",
            " media entertainment ",
            " tv broadcasting ",
            " film production ",
            " print media ",
            " electronic media ",
            " advertising & media ",
            " advertising and media ",
            " digital entertainment ",
            " printing & publication ",
            " printing publication ",
        ),
    ),
    SectorTagSpec(
        "Consumer Durables",
        "NIFTY_CONSUMER_DURABLES",
        (
            " consumer durables ",
            " household appliances ",
            " consumer electronics ",
            " furniture home furnishing ",
            " houseware ",
            " plywood ",
            " laminates ",
            " ceramics ",
            " paints ",
            " plastic products consumer ",
        ),
    ),
    SectorTagSpec(
        "Consumption",
        "NIFTY_CONSUMPTION",
        (
            " consumer discretionary ",
            " textile ",
            " garments ",
            " apparels ",
            " apparel ",
            " gems jewellery ",
            " jewellery ",
            " watches ",
            " footwear ",
            " leather ",
            " speciality retail ",
            " specialty retail ",
            " diversified retail ",
            " e retail ",
            " e commerce ",
            " internet & catalogue retail ",
            " internet catalogue retail ",
            " education ",
            " e learning ",
            " elearning ",
            " restaurants ",
            " amusement ",
            " recreation ",
            " tour travel ",
            " leisure products ",
            " cycles ",
            " granites ",
            " marbles ",
        ),
    ),
    SectorTagSpec(
        "Chemicals",
        "NIFTY_CHEMICALS",
        (
            " chemicals ",
            " specialty chemicals ",
            " commodity chemicals ",
            " fertilizers ",
            " fertilisers ",
            " pesticides ",
            " agrochemicals ",
            " petrochemicals ",
            " dyes and pigments ",
            " dyes pigments ",
        ),
    ),
    SectorTagSpec(
        "Commodities",
        "^CNXCMDT",
        (
            " commodities ",
            " specialty chemicals ",
            " commodity chemicals ",
            " fertilizers ",
            " fertilisers ",
            " pesticides ",
            " agrochemicals ",
            " petrochemicals ",
            " paper & paper ",
            " paper paper ",
            " dyes and pigments ",
            " dyes pigments ",
            " cement & cement ",
            " cement cement ",
            " metals & mining ",
            " metals mining ",
            " iron & steel ",
            " iron steel ",
            " aluminium ",
            " aluminum ",
            " rubber ",
            " forest materials ",
            " packaging ",
            " plastic products industrial ",
            " electrodes ",
            " refractories ",
            " glass industrial ",
        ),
    ),
    SectorTagSpec(
        "Services",
        "^CNXSERVICE",
        (
            " logistics ",
            " shipping ",
            " trading & distributors ",
            " trading distributors ",
            " diversified commercial services ",
            " business process outsourcing ",
            " consulting services ",
            " consumer services ",
            " hotels & resorts ",
            " hotels resorts ",
            " education ",
            " e learning ",
            " restaurants ",
            " tour travel ",
            " dredging ",
            " port & port ",
            " port port ",
            " amusement ",
            " recreation ",
            " airport ",
            " airline ",
            " road transport ",
            " transport related ",
            " data processing ",
        ),
    ),
    SectorTagSpec(
        "Telecom",
        None,
        (
            " telecommunication ",
            " telecom ",
            " cellular ",
            " fixed line ",
        ),
    ),
    SectorTagSpec("PSE", "^CNXPSE", ()),
    SectorTagSpec("CPSE", "NIFTY_CPSE", ()),
)

_INDEX_CORES_LOCK = threading.RLock()
_INDEX_CORES_CACHE: Dict[str, Set[str]] = {}
_INDEX_CORES_LOADED_FROM: Optional[Path] = None
_INDEX_CORES_META: Dict[str, Any] = {}
_REFRESH_THREAD: Optional[threading.Thread] = None


def sets_cache_path(data_dir: Path) -> Path:
    return data_dir / "index_industry_sector_sets.json"


def canonical_sector_tags() -> List[str]:
    return list(SECTOR_TAG_ORDER) + [UNCLASSIFIED]


def normalize_tag_label(raw: str) -> Optional[str]:
    """Map UI / override / legacy label to a canonical tag (or Unclassified)."""
    if raw is None:
        return None
    t = " ".join(str(raw).split()).strip()
    if not t:
        return None
    tl = t.lower()
    if tl == UNCLASSIFIED.lower():
        return UNCLASSIFIED
    for label in SECTOR_TAG_ORDER:
        if tl == label.lower():
            return label
    aliased = LEGACY_SECTOR_ALIASES.get(tl)
    if aliased:
        return aliased
    soft = {
        "auto": "Auto",
        "it": "IT",
        "pharma": "Pharma",
        "banks": "Bank",
        "banking": "Bank",
        "psu banks": "PSU Bank",
        "pvt bank": "Private Bank",
        "private banks": "Private Bank",
        "fin services": "Financial Services",
        "financials": "Financial Services",
        "fin ex bank": "Fin Ex-Bank",
        "oil and gas": "Oil & Gas",
        "defense": "Defence",
        "consumer durable": "Consumer Durables",
        "consumption": "Consumption",
        "chemicals": "Chemicals",
        "telecom": "Telecom",
        "telecommunication": "Telecom",
    }
    return soft.get(tl)


def _normalize_industry_text(raw: str) -> str:
    t = str(raw or "")
    # "Road AssetsToll" / "CNG/PNG" style labels → tokenizable words
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", t)
    t = t.lower()
    for ch in ("/", "-", "&", ",", ">", "(", ")", "'"):
        t = t.replace(ch, " ")
    return " ".join(t.split())


def _pad_blob(nse_sector: Optional[str], nse_industry: Optional[str]) -> str:
    parts = []
    for x in (nse_industry, nse_sector):
        if x is None:
            continue
        s = _normalize_industry_text(x)
        if s:
            parts.append(s)
    if not parts:
        return ""
    # Dedupe while preserving order (industry first, then sector).
    seen = set()
    ordered = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return f" {' '.join(ordered)} "


def industry_tags_for_fields(
    nse_sector: Optional[str],
    nse_industry: Optional[str],
) -> List[str]:
    hit: Set[str] = set()

    for raw in (nse_industry, nse_sector):
        if raw is None:
            continue
        exact = _normalize_industry_text(raw)
        if exact in _EXACT_LABEL_TAGS:
            hit.update(_EXACT_LABEL_TAGS[exact])

    blob = _pad_blob(nse_sector, nse_industry)
    if blob.strip():
        for spec in SECTOR_TAG_SPECS:
            for kw in spec.industry_keywords:
                # Keywords are already space-padded; normalize keyword punctuation too.
                nkw = _normalize_industry_text(kw)
                if not nkw:
                    continue
                needle = f" {nkw} "
                if needle in blob:
                    hit.add(spec.label)
                    break
    return list(hit)


def sort_tags(tags: Iterable[str]) -> List[str]:
    uniq = []
    seen = set()
    for t in tags:
        if not t or t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    uniq.sort(key=lambda x: (_TAG_RANK.get(x, 999), x.lower()))
    return uniq


def format_sector_tags(tags: Iterable[str]) -> str:
    ordered = sort_tags(tags)
    if not ordered:
        return UNCLASSIFIED
    return " · ".join(ordered)


def load_index_cores(data_dir: Path) -> Dict[str, Set[str]]:
    """Load cached index constituent cores from disk into memory."""
    global _INDEX_CORES_CACHE, _INDEX_CORES_LOADED_FROM, _INDEX_CORES_META
    path = sets_cache_path(data_dir)
    with _INDEX_CORES_LOCK:
        if _INDEX_CORES_LOADED_FROM == path and _INDEX_CORES_CACHE:
            return {k: set(v) for k, v in _INDEX_CORES_CACHE.items()}
        cores: Dict[str, Set[str]] = {spec.label: set() for spec in SECTOR_TAG_SPECS}
        meta: Dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = {
                    "version": data.get("version"),
                    "updated_at": data.get("updated_at"),
                    "errors": data.get("errors") or {},
                }
                raw = data.get("index_cores") or {}
                if isinstance(raw, dict):
                    for label, syms in raw.items():
                        if label not in cores or not isinstance(syms, list):
                            continue
                        cores[label] = {
                            str(s).strip().upper()
                            for s in syms
                            if str(s).strip()
                        }
            except Exception as exc:
                meta = {"load_error": str(exc)}
        _INDEX_CORES_CACHE = cores
        _INDEX_CORES_LOADED_FROM = path
        _INDEX_CORES_META = meta
        return {k: set(v) for k, v in cores.items()}


def index_cores_meta() -> Dict[str, Any]:
    with _INDEX_CORES_LOCK:
        return dict(_INDEX_CORES_META)


def save_index_cores(
    data_dir: Path,
    cores: Dict[str, Set[str]],
    *,
    errors: Optional[Dict[str, str]] = None,
) -> None:
    global _INDEX_CORES_CACHE, _INDEX_CORES_LOADED_FROM, _INDEX_CORES_META
    path = sets_cache_path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "index_cores": {
            label: sorted(cores.get(label) or set())
            for label in SECTOR_TAG_ORDER
        },
        "errors": errors or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with _INDEX_CORES_LOCK:
        _INDEX_CORES_CACHE = {k: set(v) for k, v in cores.items()}
        _INDEX_CORES_LOADED_FROM = path
        _INDEX_CORES_META = {
            "version": 1,
            "updated_at": payload["updated_at"],
            "errors": payload["errors"],
        }


def refresh_index_cores(
    data_dir: Path,
    db_path: Path,
    *,
    log: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Fetch NSE constituents for each tagged index and persist cores.
    Unions archive CSV + live NSE when both are available (avoids stale archive gaps
    like Schneider missing from Energy). Industry expansion is resolved live.
    """
    def _log(msg: str) -> None:
        if log:
            try:
                log(msg)
            except Exception:
                pass
        print(f"[index-industry-sectors] {msg}")

    cores: Dict[str, Set[str]] = {spec.label: set() for spec in SECTOR_TAG_SPECS}
    errors: Dict[str, str] = {}
    if not db_path.exists():
        save_index_cores(data_dir, cores, errors={"db": "missing"})
        return {"ok": False, "error": "db missing", "cores": {}}

    try:
        from server.nse_constituents import (
            NSE_INDEX_MAP,
            fetch_constituents_for_symbol,
            fetch_live_constituents,
            make_nse_session,
            parse_live_rows,
        )
    except ImportError:  # packages\server on sys.path (unit tests)
        from nse_constituents import (
            NSE_INDEX_MAP,
            fetch_constituents_for_symbol,
            fetch_live_constituents,
            make_nse_session,
            parse_live_rows,
        )

    conn = sqlite3.connect(str(db_path), timeout=30)
    session = None
    try:
        try:
            session = make_nse_session()
        except Exception as sess_err:
            _log(f"NSE session warning: {sess_err}")

        for spec in SECTOR_TAG_SPECS:
            if not spec.index_symbol:
                continue
            syms: Set[str] = set()
            sources: List[str] = []
            try:
                rows, source, err = fetch_constituents_for_symbol(spec.index_symbol, conn)
                archive_syms = {
                    str(r.get("symbol") or "").strip().upper()
                    for r in (rows or [])
                    if str(r.get("symbol") or "").strip()
                }
                if archive_syms:
                    syms |= archive_syms
                    sources.append(source or "archive")
                elif err:
                    errors[spec.label] = err

                nse_name = NSE_INDEX_MAP.get(spec.index_symbol)
                if session is not None and nse_name:
                    try:
                        raw = fetch_live_constituents(session, nse_name)
                        live_rows = parse_live_rows(raw, nse_name, conn)
                        live_syms = {
                            str(r.get("symbol") or "").strip().upper()
                            for r in (live_rows or [])
                            if str(r.get("symbol") or "").strip()
                        }
                        if live_syms:
                            before = len(syms)
                            syms |= live_syms
                            sources.append(f"live(+{len(syms) - before})")
                    except Exception as live_exc:
                        if not syms:
                            errors[spec.label] = str(live_exc)

                cores[spec.label] = syms
                if not syms:
                    _log(f"{spec.label} ({spec.index_symbol}): empty — {errors.get(spec.label)}")
                else:
                    _log(
                        f"{spec.label} ({spec.index_symbol}): {len(syms)} from "
                        f"{','.join(sources) or 'n/a'}"
                    )
            except Exception as exc:
                errors[spec.label] = str(exc)
                _log(f"{spec.label} ({spec.index_symbol}): failed — {exc}")
    finally:
        conn.close()
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    save_index_cores(data_dir, cores, errors=errors)
    return {
        "ok": True,
        "updated_at": index_cores_meta().get("updated_at"),
        "counts": {k: len(v) for k, v in cores.items()},
        "errors": errors,
    }


def tags_from_index_cores(symbol: str, data_dir: Path) -> List[str]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return []
    cores = load_index_cores(data_dir)
    return [label for label, syms in cores.items() if sym in syms]


def resolve_market_sectors(
    symbol: str,
    nse_sector: Optional[str],
    nse_industry: Optional[str],
    mapping: Optional[Dict[str, Any]] = None,
    *,
    data_dir: Optional[Path] = None,
) -> List[str]:
    """
    Return all matching sector tags for a symbol (sorted). Never empty —
    falls back to [Unclassified].
    """
    mapping = mapping or {}
    sym_u = str(symbol or "").strip().upper()
    tags: Set[str] = set()

    overrides = mapping.get("symbol_overrides") or {}
    forced: Optional[str] = None
    if sym_u and sym_u in overrides:
        forced = normalize_tag_label(str(overrides[sym_u]))
        if forced == UNCLASSIFIED:
            return [UNCLASSIFIED]
        if forced:
            tags.add(forced)

    if data_dir is not None and sym_u:
        tags.update(tags_from_index_cores(sym_u, data_dir))

    if mapping.get("use_exchange_labels", True):
        tags.update(industry_tags_for_fields(nse_sector, nse_industry))

    ns = (nse_sector or "").strip() if nse_sector else ""
    ni = (nse_industry or "").strip() if nse_industry else ""
    for rule in mapping.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        field = str(rule.get("field") or "industry").lower().strip()
        rtype = (rule.get("type") or "contains").lower().strip()
        pattern = rule.get("pattern")
        target = rule.get("sector")
        if pattern is None or target is None:
            continue
        pattern_s = str(pattern).strip()
        target_norm = normalize_tag_label(str(target))
        if not pattern_s or not target_norm or target_norm == UNCLASSIFIED:
            continue
        hay = ni if field == "industry" else ns
        matched = False
        if rtype == "equals":
            matched = hay.lower() == pattern_s.lower()
        elif rtype == "regex":
            try:
                import re

                matched = bool(re.search(pattern_s, hay, flags=re.IGNORECASE))
            except re.error:
                matched = False
        else:
            matched = pattern_s.lower() in hay.lower()
        if matched:
            tags.add(target_norm)

    ordered = sort_tags(tags)
    return ordered if ordered else [UNCLASSIFIED]


def ensure_index_cores_async(data_dir: Path, db_path: Path) -> None:
    """Load cache; if empty or missing, refresh in a background thread once."""
    global _REFRESH_THREAD
    cores = load_index_cores(data_dir)
    nonempty = sum(1 for v in cores.values() if v)
    if nonempty > 0:
        return
    with _INDEX_CORES_LOCK:
        if _REFRESH_THREAD and _REFRESH_THREAD.is_alive():
            return

        def _run() -> None:
            try:
                time.sleep(0.2)
                refresh_index_cores(data_dir, db_path)
            except Exception as exc:
                print(f"[index-industry-sectors] background refresh failed: {exc}")

        _REFRESH_THREAD = threading.Thread(
            target=_run, name="index-industry-sector-refresh", daemon=True,
        )
        _REFRESH_THREAD.start()
