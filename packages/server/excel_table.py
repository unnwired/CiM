"""Convert uploaded Excel workbooks (.xlsx / .xls / HTML-as-xls) to CSV text."""
from __future__ import annotations

import base64
import csv
import io
import re
from html.parser import HTMLParser
from typing import Any, Optional
from xml.etree import ElementTree as ET


def decode_upload_bytes(
    *,
    excel_base64: Optional[str] = None,
    raw: Optional[bytes] = None,
) -> bytes:
    if raw is not None:
        return raw
    if not excel_base64:
        raise ValueError("excel_base64 required")
    s = str(excel_base64).strip()
    if "," in s and s.lower().startswith("data:"):
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False)
    except Exception as e:
        raise ValueError(f"invalid excel_base64: {e}") from e


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value) if abs(value) < 1e-6 or abs(value) >= 1e12 else str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            # date / datetime
            if hasattr(value, "hour"):
                return value.isoformat(sep=" ", timespec="seconds")
            return value.isoformat()
        except Exception:
            pass
    return str(value).strip()


def _rows_to_csv(rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for row in rows:
        w.writerow([_cell_str(c) for c in row])
    return buf.getvalue()


def _nonempty_rows(rows: list[list[Any]]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for row in rows:
        if row is None:
            continue
        cells = list(row)
        if any(c is not None and str(c).strip() not in ("", "None") for c in cells):
            out.append(cells)
    return out


def _sniff_format(data: bytes, filename: str = "") -> str:
    """Return: xlsx | xls | html | spreadsheetml | text | unknown"""
    name = (filename or "").lower()
    head = data[:4096]
    head_l = head.lstrip()
    # UTF-16 HTML/XML exports sometimes used by older Excel "Save as"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        try:
            text = data[:8000].decode("utf-16", errors="ignore").lstrip().lower()
            if text.startswith("<html") or "<table" in text[:2000]:
                return "html"
            if "workbook" in text[:2000] or "spreadsheet" in text[:2000]:
                return "spreadsheetml"
        except Exception:
            pass
    if head_l.startswith(b"<") or head_l.startswith(b"\xef\xbb\xbf<"):
        sample = head_l[:2000].decode("utf-8", errors="ignore").lower()
        if "<html" in sample or "<table" in sample or "xmlns:x=" in sample:
            if "urn:schemas-microsoft-com:office:spreadsheet" in sample or "ss:workbook" in sample:
                return "spreadsheetml"
            return "html"
        if "workbook" in sample and "spreadsheet" in sample:
            return "spreadsheetml"
    if data[:2] == b"PK":
        return "xlsx"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "xls"
    if name.endswith((".xlsx", ".xlsm")):
        return "xlsx"
    if name.endswith(".xls"):
        # Many broker "xls" downloads are HTML tables
        sample = head.decode("utf-8", errors="ignore").lower()
        if "<html" in sample or "<table" in sample:
            return "html"
        return "xls"
    if b"," in head[:200] and b"\n" in head[:500]:
        return "text"
    return "unknown"


def _read_xlsx_sheets(data: bytes) -> list[tuple[str, str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise ValueError(
            "Excel support requires openpyxl. Install openpyxl in the runtime, or export CSV from Console."
        ) from e

    errors: list[str] = []
    # data_only=True often returns blank cells when formula caches are missing.
    # Prefer stored values first; fall back to data_only; avoid read_only (empty dims).
    for data_only in (False, True):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=False, data_only=data_only)
        except Exception as e:
            errors.append(f"openpyxl(data_only={data_only}): {e}")
            continue
        out: list[tuple[str, str]] = []
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                rows: list[list[Any]] = []
                # Explicit bounds — some Zerodha sheets have broken dimensions
                max_row = ws.max_row or 0
                max_col = ws.max_column or 0
                if max_row <= 0 or max_col <= 0:
                    # Fall back to iterating used range via values
                    for row in ws.iter_rows(values_only=True):
                        rows.append(list(row) if row is not None else [])
                else:
                    for r in range(1, max_row + 1):
                        cells = [ws.cell(r, c).value for c in range(1, max_col + 1)]
                        rows.append(cells)
                kept = _nonempty_rows(rows)
                if kept:
                    out.append((str(name), _rows_to_csv(kept)))
        finally:
            n_sheets = len(wb.sheetnames)
            wb.close()
        if out:
            return out
        errors.append(f"openpyxl(data_only={data_only}): {n_sheets} sheet(s) but no cell values")

    # pandas fallback (uses openpyxl engine)
    try:
        import pandas as pd

        xls = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
        out = []
        for name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=name, header=None, dtype=object)
            if df is None or df.empty:
                continue
            rows = df.where(pd.notnull(df), None).values.tolist()
            kept = _nonempty_rows(rows)
            if kept:
                out.append((str(name), _rows_to_csv(kept)))
        if out:
            return out
        errors.append("pandas: sheets present but empty")
    except Exception as e:
        errors.append(f"pandas: {e}")

    raise ValueError(
        "Could not read any rows from .xlsx ("
        + "; ".join(errors[:3])
        + "). Try Save As → CSV, or re-download from Console."
    )


def _read_xls_sheets(data: bytes) -> list[tuple[str, str]]:
    try:
        import xlrd
    except ImportError as e:
        raise ValueError(
            "Old .xls support requires xlrd. Save as .xlsx in Excel, or export CSV from Console."
        ) from e

    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=False)
    except Exception as e:
        # Zerodha / brokers often ship HTML named .xls
        sniff = _sniff_format(data, "file.xls")
        if sniff in ("html", "spreadsheetml"):
            return workbook_to_sheet_csvs(data, filename="file.html")
        raise ValueError(f"Could not open .xls ({e}). If Excel opens it, Save As → .xlsx or CSV.") from e

    out: list[tuple[str, str]] = []
    for i in range(book.nsheets):
        sheet = book.sheet_by_index(i)
        rows: list[list[Any]] = []
        for r in range(sheet.nrows):
            cells = []
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    try:
                        from datetime import datetime

                        dt = datetime(*xlrd.xldate_as_tuple(cell.value, book.datemode))
                        cells.append(dt.date().isoformat())
                    except Exception:
                        cells.append(cell.value)
                elif cell.ctype == xlrd.XL_CELL_EMPTY:
                    cells.append(None)
                else:
                    cells.append(cell.value)
            rows.append(cells)
        kept = _nonempty_rows(rows)
        if kept:
            out.append((sheet.name, _rows_to_csv(kept)))
    return out


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: Optional[list[list[str]]] = None
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t == "table":
            self._table = []
        elif t == "tr" and self._table is not None:
            self._row = []
        elif t in ("td", "th") and self._row is not None:
            self._cell = []
            self._in_cell = True
            # colspan ignored — keep simple

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell and self._row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell or [])).strip()
            self._row.append(text)
            self._cell = None
            self._in_cell = False
        elif t == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif t == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._cell is not None:
            self._cell.append(data)


def _decode_text_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1252", "latin1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_html_tables(data: bytes) -> list[tuple[str, str]]:
    text = _decode_text_bytes(data)
    parser = _HtmlTableParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:
        raise ValueError(f"HTML spreadsheet parse failed: {e}") from e
    out: list[tuple[str, str]] = []
    for i, table in enumerate(parser.tables):
        kept = _nonempty_rows(table)
        if kept:
            out.append((f"Table{i + 1}", _rows_to_csv(kept)))
    return out


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _read_spreadsheetml(data: bytes) -> list[tuple[str, str]]:
    """Excel 2003 XML Spreadsheet."""
    text = _decode_text_bytes(data)
    try:
        root = ET.fromstring(text)
    except Exception as e:
        raise ValueError(f"SpreadsheetML parse failed: {e}") from e
    out: list[tuple[str, str]] = []
    for ws in root.iter():
        if _local(ws.tag) != "Worksheet":
            continue
        name = (
            ws.attrib.get("{urn:schemas-microsoft-com:office:spreadsheet}Name")
            or ws.attrib.get("Name")
            or f"Sheet{len(out) + 1}"
        )
        rows: list[list[Any]] = []
        for row_el in ws.iter():
            if _local(row_el.tag) != "Row":
                continue
            cells: list[Any] = []
            for cell_el in list(row_el):
                if _local(cell_el.tag) != "Cell":
                    continue
                # ss:Index can skip columns — keep simple sequential for now
                val = ""
                for child in list(cell_el):
                    if _local(child.tag) == "Data":
                        val = (child.text or "").strip()
                        break
                cells.append(val)
            rows.append(cells)
        kept = _nonempty_rows(rows)
        if kept:
            out.append((str(name), _rows_to_csv(kept)))
    return out


def workbook_to_sheet_csvs(data: bytes, filename: str = "") -> list[tuple[str, str]]:
    """Return [(sheet_name, csv_text), ...] from workbook bytes."""
    if not data:
        raise ValueError("Empty upload")
    kind = _sniff_format(data, filename)
    if kind == "xlsx":
        return _read_xlsx_sheets(data)
    if kind == "xls":
        return _read_xls_sheets(data)
    if kind == "html":
        return _read_html_tables(data)
    if kind == "spreadsheetml":
        return _read_spreadsheetml(data)
    if kind == "text":
        return [("Sheet1", _decode_text_bytes(data))]

    # Last-resort cascade
    attempts: list[str] = []
    for reader, label in (
        (_read_xlsx_sheets, "xlsx"),
        (_read_xls_sheets, "xls"),
        (_read_html_tables, "html"),
        (_read_spreadsheetml, "spreadsheetml"),
    ):
        try:
            sheets = reader(data)
            if sheets:
                return sheets
            attempts.append(f"{label}: empty")
        except Exception as e:
            attempts.append(f"{label}: {e}")
    raise ValueError(
        f"Unrecognized Excel file ({filename or 'upload'}; sniffed={kind}). "
        f"Tried: {'; '.join(attempts[:4])}. Use .xlsx / .xls / CSV."
    )


def excel_upload_to_csv_text(
    *,
    excel_base64: Optional[str] = None,
    raw: Optional[bytes] = None,
    filename: str = "",
    prefer_sheet: Optional[str] = None,
) -> tuple[str, str]:
    """
    Convert an Excel upload to a single CSV string.

    When prefer_sheet is set, use that sheet if present; otherwise pick the
    sheet that best looks like Tax P&L / realised trades.
    Returns (csv_text, sheet_name).
    """
    data = decode_upload_bytes(excel_base64=excel_base64, raw=raw)
    kind = _sniff_format(data, filename)
    try:
        sheets = workbook_to_sheet_csvs(data, filename=filename)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(
            f"Failed to read Excel ({filename or 'upload'}; format={kind}): {e}"
        ) from e

    if not sheets:
        raise ValueError(
            f"Excel workbook has no data rows ({filename or 'upload'}; format={kind}). "
            "If Excel shows data, Save As → CSV (UTF-8) and upload that, or Save As → .xlsx."
        )

    if prefer_sheet:
        want = prefer_sheet.strip().lower()
        for name, csv_text in sheets:
            if name.strip().lower() == want or want in name.strip().lower():
                return csv_text, name

    scored: list[tuple[int, int, str, str]] = []
    for name, csv_text in sheets:
        low = csv_text[:12000].lower()
        score = 0
        if "symbol" in low or "scrip" in low or "tradingsymbol" in low:
            score += 5
        if "realis" in low or "realized" in low or "p&l" in low or "pnl" in low:
            score += 4
        if "buy" in low and "sell" in low:
            score += 3
        if "quantity" in low or "qty" in low:
            score += 2
        if "isin" in low:
            score += 1
        # Prefer trade tables over summary cover sheets
        if "summary" in name.lower() or "cover" in name.lower():
            score -= 2
        rows = max(csv_text.count("\n"), 1)
        scored.append((score, rows, name, csv_text))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    best = scored[0]
    return best[3], best[2]


def resolve_tax_pnl_csv_from_payload(payload: dict) -> str:
    """
    Extract Tax P&L CSV text from API payload.

    Accepts plain csv/text, or excel_base64 (+ optional filename).
    """
    csv_text = str(payload.get("csv") or payload.get("text") or payload.get("tax_pnl_csv") or "")
    if csv_text.strip():
        return csv_text

    b64 = payload.get("excel_base64") or payload.get("xlsx_base64") or payload.get("file_base64")
    if not b64:
        raise ValueError("Tax P&L CSV text or excel_base64 required")

    filename = str(payload.get("filename") or payload.get("file_name") or "tax_pnl.xlsx")
    prefer = payload.get("sheet") or payload.get("prefer_sheet")
    csv_out, sheet = excel_upload_to_csv_text(
        excel_base64=str(b64),
        filename=filename,
        prefer_sheet=str(prefer) if prefer else None,
    )
    # Stash sheet name for API callers that inspect payload after resolve — optional
    payload["_resolved_sheet"] = sheet
    return csv_out
