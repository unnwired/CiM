"""
NSE Pulse — Financials Scraper
Fetches quarterly results and company info from BSE India API.
Run via Admin Panel → Fetch Latest Financials
"""

import sqlite3
import requests
import time
import random
import re
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

DB_PATH = Path(r"D:\Programs\NSE Pulse\Claude Ai\data\nse_data.db")

HEADERS = {
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":  "en-US,en;q=0.9",
    "Referer":          "https://www.bseindia.com/",
    "Origin":           "https://www.bseindia.com",
    "X-Requested-With": "XMLHttpRequest",
}

RATE_DELAY_MIN      = 0.8
RATE_DELAY_MAX      = 1.5
MAX_CONSEC_FAILURES = 10
MAX_FAILURE_RATE    = 0.30
PAUSE_ON_BLOCK      = 45


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    s.get("https://www.bseindia.com", timeout=15)
    time.sleep(random.uniform(1.5, 3.0))
    return s


def get_bse_code(session, symbol):
    url = f"https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&shname={symbol}&Type=EQ&Udiff=&segment=equity&status=Active"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            match = next((d for d in data if d.get("scrip_id","").upper() == symbol.upper()), None)
            if match:
                return match["SCRIP_CD"], match.get("Scrip_Name",""), match.get("INDUSTRY","")
    except Exception:
        pass
    return None, None, None


def parse_number(val):
    if not val:
        return None
    val = str(val).replace(",","").replace("%","").strip()
    try:
        return round(float(val), 2)
    except Exception:
        return None


def parse_period_sort(period):
    month_map = {
        "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
        "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"
    }
    try:
        parts = period.lower().split("-")
        if len(parts) == 2:
            mon = month_map.get(parts[0][:3], "00")
            yr  = parts[1]
            if len(yr) == 2:
                yr = "20" + yr
            return f"{yr}-{mon}"
    except Exception:
        pass
    return period


def fetch_quarterly(session, bse_code):
    url = f"https://api.bseindia.com/BseIndiaAPI/api/GetReportNewFor_Result/w?scripcode={bse_code}"
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        data   = r.json()
        html   = data.get("QtlyinCr","")
        if not html:
            return None
        soup   = BeautifulSoup(html, "html.parser")
        rows   = soup.find_all("tr")

        # Extract column headers
        header_row = rows[0] if rows else None
        if not header_row:
            return None
        cols = [td.text.strip() for td in header_row.find_all("td")]
        # cols[0] is label, cols[1..] are periods
        periods = cols[1:]

        # Extract data rows
        row_map = {}
        for row in rows[1:]:
            cells = [td.text.strip() for td in row.find_all("td")]
            if cells and cells[0] and cells[0] != "Income Statement":
                row_map[cells[0]] = cells[1:]

        # Build quarterly records — only quarterly columns (not FY annual)
        quarterly = []
        for i, period in enumerate(periods):
            if period.startswith("FY"):
                continue
            record = {
                "period":       period,
                "period_sort":  parse_period_sort(period),
                "revenue":      parse_number(row_map.get("Revenue",      [None]*10)[i] if i < len(row_map.get("Revenue",[])) else None),
                "other_income": parse_number(row_map.get("Other Income",  [None]*10)[i] if i < len(row_map.get("Other Income",[])) else None),
                "total_income": parse_number(row_map.get("Total Income",  [None]*10)[i] if i < len(row_map.get("Total Income",[])) else None),
                "expenditure":  parse_number(row_map.get("Expenditure",   [None]*10)[i] if i < len(row_map.get("Expenditure",[])) else None),
                "interest":     parse_number(row_map.get("Interest",      [None]*10)[i] if i < len(row_map.get("Interest",[])) else None),
                "pbdt":         parse_number(row_map.get("PBDT",          [None]*10)[i] if i < len(row_map.get("PBDT",[])) else None),
                "depreciation": parse_number(row_map.get("Depreciation",  [None]*10)[i] if i < len(row_map.get("Depreciation",[])) else None),
                "pbt":          parse_number(row_map.get("PBT",           [None]*10)[i] if i < len(row_map.get("PBT",[])) else None),
                "tax":          parse_number(row_map.get("Tax",           [None]*10)[i] if i < len(row_map.get("Tax",[])) else None),
                "net_profit":   parse_number(row_map.get("Net Profit",    [None]*10)[i] if i < len(row_map.get("Net Profit",[])) else None),
                "equity":       parse_number(row_map.get("Equity",        [None]*10)[i] if i < len(row_map.get("Equity",[])) else None),
                "eps":          parse_number(row_map.get("EPS",           [None]*10)[i] if i < len(row_map.get("EPS",[])) else None),
                "ceps":         parse_number(row_map.get("CEPS",          [None]*10)[i] if i < len(row_map.get("CEPS",[])) else None),
                "opm_percent":  parse_number(row_map.get("OPM %",         [None]*10)[i] if i < len(row_map.get("OPM %",[])) else None),
                "npm_percent":  parse_number(row_map.get("NPM %",         [None]*10)[i] if i < len(row_map.get("NPM %",[])) else None),
            }
            quarterly.append(record)

        return quarterly
    except Exception as e:
        return None


def fetch_company_info(session, bse_code):
    url = f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode={bse_code}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            name = data.get("Cmpname",{}).get("FullN","")
            hdr  = data.get("Header",{})
            return {
                "company_name": name,
                "high":         parse_number(hdr.get("High")),
                "low":          parse_number(hdr.get("Low")),
                "prev_close":   parse_number(hdr.get("PrevClose")),
            }
    except Exception:
        pass
    return {}


def write_company_info(conn, symbol, bse_code, company_name, industry, info):
    cursor = conn.cursor()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT OR REPLACE INTO company_info
        (symbol, bse_code, company_name, about, sector, industry, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        symbol, bse_code,
        company_name or info.get("company_name",""),
        None,  # about — not available via BSE API
        None,  # sector
        industry,
        now
    ))
    conn.commit()


def write_quarterly(conn, symbol, records):
    cursor = conn.cursor()
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for rec in records:
        cursor.execute("""
            INSERT OR REPLACE INTO quarterly_results
            (symbol, period, period_sort, revenue, other_income, total_income,
             expenditure, interest, pbdt, depreciation, pbt, tax, net_profit,
             equity, eps, ceps, opm_percent, npm_percent, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            symbol,
            rec["period"],
            rec["period_sort"],
            rec["revenue"],      rec["other_income"], rec["total_income"],
            rec["expenditure"],  rec["interest"],     rec["pbdt"],
            rec["depreciation"], rec["pbt"],           rec["tax"],
            rec["net_profit"],   rec["equity"],        rec["eps"],
            rec["ceps"],         rec["opm_percent"],   rec["npm_percent"],
            now
        ))
    conn.commit()


def needs_update(conn, symbol, days=90):
    cursor = conn.cursor()
    cursor.execute("SELECT updated_at FROM quarterly_results WHERE symbol=? ORDER BY updated_at DESC LIMIT 1", (symbol,))
    row = cursor.fetchone()
    if not row:
        return True
    try:
        updated = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - updated).days >= days
    except Exception:
        return True


def run(progress_callback=None, message_callback=None, force=False):
    def log(msg):
        print(msg)
        if message_callback:
            message_callback(msg)

    log("Connecting to database...")
    conn = sqlite3.connect(str(DB_PATH))

    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM screener ORDER BY market_cap DESC NULLS LAST")
    symbols = [r[0] for r in cursor.fetchall()]
    total   = len(symbols)

    log(f"Found {total} symbols to process")
    log("Initialising BSE session...")
    session = make_session()
    log("Session ready.\n")

    updated        = 0
    failed         = 0
    skipped        = 0
    consec_failures = 0

    for i, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(i + 1, total)

        # Skip if recently updated and not forced
        if not force and not needs_update(conn, symbol):
            skipped += 1
            continue

        # Safety checks
        if updated + failed > 50:
            fail_rate = failed / (updated + failed)
            if fail_rate > MAX_FAILURE_RATE:
                log(f"\n⚠ Failure rate {fail_rate:.0%} exceeds threshold. Stopping.")
                break

        if consec_failures >= MAX_CONSEC_FAILURES:
            log(f"\n⚠ {MAX_CONSEC_FAILURES} consecutive failures. Pausing {PAUSE_ON_BLOCK}s...")
            time.sleep(random.uniform(PAUSE_ON_BLOCK, PAUSE_ON_BLOCK + 15))
            session = make_session()
            consec_failures = 0

        try:
            # Step 1: Get BSE code
            bse_code, company_name, industry = get_bse_code(session, symbol)
            time.sleep(random.uniform(0.3, 0.8))
            if not bse_code:
                failed       += 1
                consec_failures += 1
                log(f"  ✗ {symbol}: BSE code not found")
                continue

            # Step 2: Fetch quarterly results
            quarterly = fetch_quarterly(session, bse_code)
            if not quarterly:
                failed          += 1
                consec_failures += 1
                log(f"  ✗ {symbol} ({bse_code}): No quarterly data")
                continue

            time.sleep(random.uniform(0.3, 0.8))
            # Step 3: Fetch company info
            info = fetch_company_info(session, bse_code)

            time.sleep(random.uniform(0.2, 0.5))
            # Step 4: Write to DB
            write_company_info(conn, symbol, bse_code, company_name, industry, info)
            write_quarterly(conn, symbol, quarterly)

            updated         += 1
            consec_failures  = 0
            log(f"  ✓ {symbol} ({bse_code}): {len(quarterly)} quarters")

        except Exception as e:
            failed          += 1
            consec_failures += 1
            log(f"  ✗ {symbol}: {e}")

        time.sleep(random.uniform(RATE_DELAY_MIN, RATE_DELAY_MAX))

    conn.close()
    log(f"\n✓ Done. Updated: {updated} | Skipped: {skipped} | Failed: {failed}")
    return updated


if __name__ == "__main__":
    print("=" * 60)
    print("NSE Pulse — Financials Scraper")
    print(f"Started: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
    print("=" * 60)
    run()
    print(f"\nFinished: {datetime.now().strftime('%d %b %Y %H:%M:%S')}")
