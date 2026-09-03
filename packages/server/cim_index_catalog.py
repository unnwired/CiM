"""
Single source of truth for chartable NSE equity indices in CiM.

OHLC / live quotes: Upstox (NSE_INDEX instrument keys).
Constituents: NSE archive CSV and/or NSE live equity-stockIndices API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChartableIndex:
    symbol: str
    display_name: str
    nse_name: str
    upstox_name: str
    archive_csv: Optional[str] = None
    yahoo_symbol: Optional[str] = None  # legacy Yahoo ticker when different from symbol


# Existing Yahoo-era chartables (keep symbols stable for DB / bookmarks).
_LEGACY: list[ChartableIndex] = [
    ChartableIndex("^NSEI", "NIFTY 50", "NIFTY 50", "Nifty 50", "ind_nifty50list.csv", "^NSEI"),
    ChartableIndex("^NSEBANK", "NIFTY Bank", "NIFTY BANK", "Nifty Bank", "ind_niftybanklist.csv", "^NSEBANK"),
    ChartableIndex("^CNXIT", "NIFTY IT", "NIFTY IT", "Nifty IT", "ind_niftyitlist.csv", "^CNXIT"),
    ChartableIndex("^NSMIDCP", "NIFTY Midcap 100", "NIFTY MIDCAP 100", "Nifty Midcap 100", "ind_niftymidcap100list.csv", "^NSMIDCP"),
    ChartableIndex("^NSEMDCP50", "NIFTY Midcap 50", "NIFTY MIDCAP 50", "Nifty Midcap 50", "ind_niftymidcap50list.csv", "^NSEMDCP50"),
    ChartableIndex("^CNXFMCG", "NIFTY FMCG", "NIFTY FMCG", "Nifty FMCG", "ind_niftyfmcglist.csv", "^CNXFMCG"),
    ChartableIndex("^CNXPHARMA", "NIFTY Pharma", "NIFTY PHARMA", "Nifty Pharma", "ind_niftypharmalist.csv", "^CNXPHARMA"),
    ChartableIndex(
        "NIFTY_HEALTHCARE.NS",
        "Nifty Healthcare",
        "NIFTY HEALTHCARE INDEX",
        "Nifty Healthcare",
        "ind_niftyhealthcarelist.csv",
        "NIFTY_HEALTHCARE.NS",
    ),
    ChartableIndex("^CNXAUTO", "NIFTY Auto", "NIFTY AUTO", "Nifty Auto", "ind_niftyautolist.csv", "^CNXAUTO"),
    ChartableIndex("^CNXMETAL", "NIFTY Metal", "NIFTY METAL", "Nifty Metal", "ind_niftymetallist.csv", "^CNXMETAL"),
    ChartableIndex("^CNXREALTY", "NIFTY Realty", "NIFTY REALTY", "Nifty Realty", "ind_niftyrealtylist.csv", "^CNXREALTY"),
    ChartableIndex("^CNXENERGY", "NIFTY Energy", "NIFTY ENERGY", "Nifty Energy", "ind_niftyenergylist.csv", "^CNXENERGY"),
    ChartableIndex("^CNXINFRA", "NIFTY Infra", "NIFTY INFRA", "Nifty Infra", "ind_niftyinfralist.csv", "^CNXINFRA"),
    ChartableIndex(
        "^CNXINDDEF",
        "Nifty India Defence",
        "NIFTY INDIA DEFENCE",
        "Nifty Ind Defence",
        "ind_niftyindiadefence_list.csv",
        "^CNXINDDEF",
    ),
    ChartableIndex("^CNXPSUBANK", "NIFTY PSU Bank", "NIFTY PSU BANK", "Nifty Psu Bank", "ind_niftypsubanklist.csv", "^CNXPSUBANK"),
    ChartableIndex("^CNXSC", "NIFTY Smallcap 100", "NIFTY SMALLCAP 100", "Nifty Smlcap 100", "ind_niftysmallcap100list.csv", "^CNXSC"),
    ChartableIndex("^CNXCMDT", "NIFTY Commodities", "NIFTY COMMODITIES", "Nifty Commodities", "ind_niftycommoditieslist.csv", "^CNXCMDT"),
    ChartableIndex("^CNXPSE", "NIFTY PSE", "NIFTY PSE", "Nifty Pse", "ind_niftypselist.csv", "^CNXPSE"),
    ChartableIndex("^CNXMNC", "NIFTY MNC", "NIFTY MNC", "Nifty Mnc", "ind_niftymnclist.csv", "^CNXMNC"),
    ChartableIndex(
        "^CNXSERVICE",
        "NIFTY Services Sector",
        "NIFTY SERVICES SECTOR",
        "Nifty Serv Sector",
        "ind_niftyservicelist.csv",
        "^CNXSERVICE",
    ),
    ChartableIndex("^CNXMEDIA", "NIFTY Media", "NIFTY MEDIA", "Nifty Media", "ind_niftymedialist.csv", "^CNXMEDIA"),
    ChartableIndex(
        "^CNXDIVOP",
        "NIFTY Dividend Opp 50",
        "NIFTY DIVIDEND OPPORTUNITIES 50",
        "Nifty Div Opps 50",
        "ind_niftydivopp50list.csv",
        "^CNXDIVOP",
    ),
    ChartableIndex("^CNXNXT50", "Nifty Next 50", "NIFTY NEXT 50", "Nifty Next 50", "ind_niftynext50list.csv", "^CNXNXT50"),
    ChartableIndex("^CNX100", "Nifty 100", "NIFTY 100", "Nifty 100", "ind_nifty100list.csv", "^CNX100"),
    ChartableIndex("^CNX200", "Nifty 200", "NIFTY 200", "Nifty 200", "ind_nifty200list.csv", "^CNX200"),
    ChartableIndex("^CRSLDX", "Nifty 500", "NIFTY 500", "Nifty 500", "ind_nifty500list.csv", "^CRSLDX"),
    ChartableIndex(
        "^CNXSMLCP50",
        "Nifty Smallcap 50",
        "NIFTY SMLCAP 50",
        "Nifty Smlcap 50",
        "ind_niftysmallcap50list.csv",
        "^CNXSMLCP50",
    ),
]

# High-value Upstox-first additions (breadth, banks, sectors/themes, VIX).
_HIGH_VALUE: list[ChartableIndex] = [
    # Breadth / size
    ChartableIndex("NIFTY_MIDCAP_150", "Nifty Midcap 150", "NIFTY MIDCAP 150", "Nifty Midcap 150", "ind_niftymidcap150list.csv"),
    ChartableIndex("NIFTY_SMALLCAP_250", "Nifty Smallcap 250", "NIFTY SMALLCAP 250", "Nifty Smlcap 250", "ind_niftysmallcap250list.csv"),
    ChartableIndex("NIFTY_SMALLCAP_500", "Nifty Smallcap 500", "NIFTY SMALLCAP 500", "Nifty Smallcap 500", None),
    ChartableIndex("NIFTY_MICROCAP_250", "Nifty Microcap 250", "NIFTY MICROCAP 250", "Nifty Microcap250", "ind_niftymicrocap250_list.csv"),
    ChartableIndex(
        "NIFTY_LARGEMIDCAP_250",
        "Nifty LargeMidcap 250",
        "NIFTY LARGEMIDCAP 250",
        "Nifty Largemid250",
        "ind_niftylargemidcap250list.csv",
    ),
    ChartableIndex("NIFTY_TOTAL_MARKET", "Nifty Total Market", "NIFTY TOTAL MARKET", "Nifty Total Mkt", "ind_niftytotalmarket_list.csv"),
    ChartableIndex("NIFTY_MIDCAP_SELECT", "Nifty Midcap Select", "NIFTY MIDCAP SELECT", "Nifty Mid Select", "ind_niftymidcapselect_list.csv"),
    ChartableIndex("NIFTY_MIDCAP_LIQUID_15", "Nifty Midcap Liquid 15", "NIFTY MIDCAP LIQUID 15", "Nifty Mid Liq 15", None),
    # Banks / financials
    ChartableIndex(
        "NIFTY_FIN_SERVICE",
        "Nifty Financial Services",
        "NIFTY FINANCIAL SERVICES",
        "Nifty Fin Service",
        "ind_niftyfinancelist.csv",
    ),
    ChartableIndex("NIFTY_PVT_BANK", "Nifty Private Bank", "NIFTY PRIVATE BANK", "Nifty Pvt Bank", "ind_nifty_privatebanklist.csv"),
    ChartableIndex(
        "NIFTY_FIN_EX_BANK",
        "Nifty Fin Services Ex-Bank",
        "NIFTY FINANCIAL SERVICES EX-BANK",
        "Nifty Finserexbnk",
        "ind_niftyfinancialservicesexbank_list.csv",
    ),
    ChartableIndex(
        "NIFTY_FIN_25_50",
        "Nifty Financial Services 25/50",
        "NIFTY FINANCIAL SERVICES 25/50",
        "Nifty Finsrv25 50",
        "ind_niftyfinancialservices25_50list.csv",
    ),
    # Sectors / themes
    ChartableIndex("NIFTY_OIL_GAS", "Nifty Oil & Gas", "NIFTY OIL & GAS", "Nifty Oil And Gas", "ind_niftyoilgaslist.csv"),
    ChartableIndex("NIFTY_CPSE", "Nifty CPSE", "NIFTY CPSE", "Nifty Cpse", "ind_niftycpselist.csv"),
    ChartableIndex(
        "NIFTY_CONSUMPTION",
        "Nifty India Consumption",
        "NIFTY INDIA CONSUMPTION",
        "Nifty Consumption",
        "ind_niftyconsumptionlist.csv",
    ),
    ChartableIndex(
        "NIFTY_CONSUMER_DURABLES",
        "Nifty Consumer Durables",
        "NIFTY CONSUMER DURABLES",
        "Nifty Consr Durbl",
        "ind_niftyconsumerdurableslist.csv",
    ),
    ChartableIndex("NIFTY_CAPITAL_MARKETS", "Nifty Capital Markets", "NIFTY CAPITAL MARKETS", "Nifty Capital Mkt", None),
    ChartableIndex("NIFTY_CEMENT", "Nifty Cement", "NIFTY CEMENT", "Nifty Cement", None),
    ChartableIndex("NIFTY_CHEMICALS", "Nifty Chemicals", "NIFTY CHEMICALS", "Nifty Chemicals", "ind_niftychemicals_list.csv"),
    ChartableIndex(
        "NIFTY_INDIA_DIGITAL",
        "Nifty India Digital",
        "NIFTY INDIA DIGITAL",
        "Nifty Ind Digital",
        "ind_niftyindiadigital_list.csv",
    ),
    ChartableIndex(
        "NIFTY_INDIA_MFG",
        "Nifty India Manufacturing",
        "NIFTY INDIA MANUFACTURING",
        "Nifty India Mfg",
        "ind_niftyindiamanufacturing_list.csv",
    ),
    ChartableIndex(
        "NIFTY_INDIA_TOURISM",
        "Nifty India Tourism",
        "NIFTY INDIA TOURISM",
        "Nifty Ind Tourism",
        "ind_niftyindiatourism_list.csv",
    ),
    ChartableIndex("NIFTY_EV", "Nifty EV & New Age Automotive", "NIFTY EV & NEW AGE AUTOMOTIVE", "Nifty Ev", None),
    ChartableIndex("NIFTY_HOUSING", "Nifty Housing", "NIFTY HOUSING", "Nifty Housing", None),
    ChartableIndex(
        "NIFTY_CORE_HOUSING",
        "Nifty Core Housing",
        "NIFTY CORE HOUSING",
        "Nifty Corehousing",
        "ind_niftycorehousing_list.csv",
    ),
    ChartableIndex("NIFTY_REITS_REALTY", "Nifty REITs & Realty", "NIFTY REITS & REALTY", "Nifty Reits Realty", None),
    ChartableIndex("NIFTY_MOBILITY", "Nifty Mobility", "NIFTY MOBILITY", "Nifty Mobility", "ind_niftymobility_list.csv"),
    ChartableIndex("NIFTY_INTERNET", "Nifty India Internet", "NIFTY INDIA INTERNET", "Nifty Internet", None),
    ChartableIndex("NIFTY_GROWSECT_15", "Nifty Growth Sectors 15", "NIFTY GROWTH SECTORS 15", "Nifty Growsect 15", None),
    ChartableIndex(
        "NIFTY_INFRALOG",
        "Nifty India Infrastructure & Logistics",
        "NIFTY INDIA INFRASTRUCTURE & LOGISTICS",
        "Nifty Infralog",
        None,
    ),
    ChartableIndex(
        "NIFTY_TRANS_LOGIS",
        "Nifty Transportation & Logistics",
        "NIFTY TRANSPORTATION & LOGISTICS",
        "Nifty Trans Logis",
        None,
    ),
    ChartableIndex("NIFTY_RURAL", "Nifty Rural", "NIFTY RURAL", "Nifty Rural", None),
    ChartableIndex("NIFTY_IPO", "Nifty IPO", "NIFTY IPO", "Nifty Ipo", None),
    ChartableIndex(
        "NIFTY_NEW_CONSUMP",
        "Nifty India New Age Consumption",
        "NIFTY INDIA NEW AGE CONSUMPTION",
        "Nifty New Consump",
        None,
    ),
    ChartableIndex(
        "NIFTY_NONCYC_CONS",
        "Nifty Non-Cyclical Consumer",
        "NIFTY NON-CYCLICAL CONSUMER",
        "Nifty Noncyc Cons",
        None,
    ),
    ChartableIndex(
        "NIFTY_RAILWAYS_PSU",
        "Nifty India Railways PSU",
        "NIFTY INDIA RAILWAYS PSU",
        "Nifty Railwayspsu",
        None,
    ),
    # Volatility (no equity constituents)
    ChartableIndex("INDIA_VIX", "India VIX", "INDIA VIX", "India Vix", None),
]

CHARTABLE_INDICES: tuple[ChartableIndex, ...] = tuple(_LEGACY + _HIGH_VALUE)

# Commodities stay on Yahoo (not Upstox NSE_INDEX).
COMMODITY_INDICES: tuple[tuple[str, str], ...] = (
    ("GC=F", "Gold Futures"),
    ("SI=F", "Silver Futures"),
)

# Yahoo has no usable daily OHLC for these; Upstox primary when mapped, else skip.
NSE_ONLY_FALLBACK_SYMBOLS = frozenset({"^CNXINDDEF", "NIFTY_HEALTHCARE.NS"})

NSE_INDEX_HISTORY_START = {
    "^CNXINDDEF": "2024-11-11",
    "NIFTY_HEALTHCARE.NS": "2020-11-18",
}


def by_symbol() -> dict[str, ChartableIndex]:
    return {row.symbol: row for row in CHARTABLE_INDICES}


def upstox_name_map() -> dict[str, str]:
    return {row.symbol: row.upstox_name for row in CHARTABLE_INDICES}


def nse_name_map() -> dict[str, str]:
    return {row.symbol: row.nse_name for row in CHARTABLE_INDICES}


def archive_csv_map() -> dict[str, str]:
    return {row.symbol: row.archive_csv for row in CHARTABLE_INDICES if row.archive_csv}


def scrape_indices_tuples() -> list[tuple[str, str, str]]:
    """(symbol, display_name, category) for scrape_indices.INDICES."""
    rows = [(r.symbol, r.display_name, "equity") for r in CHARTABLE_INDICES]
    rows.extend((sym, name, "commodity") for sym, name in COMMODITY_INDICES)
    return rows


def is_cim_index_symbol(symbol: str) -> bool:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return False
    if sym.startswith("^") or sym.startswith("NSE:"):
        return True
    if sym in by_symbol():
        return True
    if sym.startswith("NIFTY_") or sym == "INDIA_VIX":
        return True
    if sym.endswith(".NS") and "NIFTY" in sym:
        return True
    return False
