"""CLI / admin entry: refresh AMFI open-ended mutual fund NAVs into nse_data.db."""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "nse_data.db"


def _ensure_path() -> None:
    pkg = BASE_DIR / "packages"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))


def main() -> int:
    _ensure_path()
    from server import mf_nav

    def log(msg: str) -> None:
        text = str(msg)
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="replace").decode("ascii"))

    stats = mf_nav.run(DB_PATH, log_fn=log)
    log(f"[mf] done schemes={stats.get('schemes')} history={stats.get('history_rows')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
