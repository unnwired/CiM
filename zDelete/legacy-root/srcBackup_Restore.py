"""
NSE Pulse — Backup & Restore
Includes:
  1) Source backup (frontend/src + server.py)
  2) Comprehensive backup (project-wide, excluding DB/data and heavy/generated folders)
"""

import fnmatch
import shutil
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE        = Path(r"D:\Programs\NSE Pulse\Claude Ai")
FRONTEND    = BASE / "frontend" / "src"
SERVER_FILE = BASE / "server" / "server.py"
BACKUP_ROOT = BASE / "backups"
BACKUP_FULL_ROOT = BASE / "backups_full"

# ── Comprehensive backup exclusions ───────────────────────────────────────────
# Database/data is excluded by request.
EXCLUDE_DIR_NAMES = {
    "data",
    "backups",
    "backups_full",
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
EXCLUDE_FILE_PATTERNS = {
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pyc",
    "*.pyo",
    "*.log",
}


def create_backup():
    now       = datetime.now()
    day       = now.strftime("%A")
    timestamp = now.strftime("%d-%m-%Y_%H-%M-%S")
    name      = f"{day}_{timestamp}"
    dest      = BACKUP_ROOT / name
    dest.mkdir(parents=True, exist_ok=True)

    manifest_lines = []
    backed_up      = []
    count          = 0

    # Backup frontend src files
    for path in sorted(FRONTEND.rglob("*")):
        if path.is_file() and path.suffix in (".js", ".css", ".html", ".json"):
            rel      = path.relative_to(FRONTEND)
            flat     = str(rel).replace("\\", "__").replace("/", "__")
            dst_file = dest / flat
            shutil.copy2(path, dst_file)
            manifest_lines.append(f"{flat}  -->  {rel}")
            backed_up.append((str(path), str(dst_file)))
            count += 1

    # Backup server.py
    if SERVER_FILE.exists():
        shutil.copy2(SERVER_FILE, dest / "server.py")
        manifest_lines.append("server.py  -->  server.py")
        backed_up.append((str(SERVER_FILE), str(dest / "server.py")))
        count += 1

    # Write manifest
    with open(dest / "_MANIFEST.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(manifest_lines))

    print(f"\n✓ Backup created: {name}")
    print(f"  Location: {dest}")
    print(f"\n{'─'*70}")
    print(f"  {'SOURCE FILE':<55} BACKED UP TO")
    print(f"{'─'*70}")
    for src, dst in backed_up:
        src_short = src.replace(str(BASE), "").lstrip("\\")
        dst_short = dst.replace(str(BACKUP_ROOT), "backups").lstrip("\\")
        print(f"  {src_short:<55} {dst_short}")
    print(f"{'─'*70}")
    print(f"  Total: {count} files\n")
    return dest


def list_backups(root: Path):
    if not root.exists():
        return []
    return sorted([
        d for d in root.iterdir()
        if d.is_dir() and d.name != "db"
    ], reverse=True)


def restore_backup(backup_path, root: Path):
    manifest = backup_path / "_MANIFEST.txt"
    if not manifest.exists():
        print(f"✗ No manifest found in {backup_path.name}")
        return False

    restored      = 0
    restored_list = []

    with open(manifest, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "-->" not in line:
                continue
            parts     = line.split("  -->  ")
            flat_name = parts[0].strip()
            rel_path  = parts[1].strip()
            src_file  = backup_path / flat_name

            if not src_file.exists():
                print(f"  ✗ Missing in backup: {flat_name}")
                continue

            if flat_name == "server.py":
                dst_file = SERVER_FILE
            else:
                dst_file = FRONTEND / rel_path

            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            restored_list.append((str(src_file), str(dst_file)))
            restored += 1

    print(f"\n{'─'*70}")
    print(f"  {'RESTORED FROM':<55} RESTORED TO")
    print(f"{'─'*70}")
    for src, dst in restored_list:
        src_short = src.replace(str(root), root.name).lstrip("\\")
        dst_short = dst.replace(str(BASE), "").lstrip("\\")
        print(f"  {src_short:<55} {dst_short}")
    print(f"{'─'*70}")
    print(f"  ✓ Restored {restored} files from {backup_path.name}\n")
    return True


def should_exclude_file(path: Path) -> bool:
    for pat in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(path.name.lower(), pat.lower()):
            return True
    return False


def iter_project_files():
    """Yield project files under BASE, skipping excluded folders/patterns."""
    for path in BASE.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(BASE)
        if EXCLUDE_DIR_NAMES & set(rel.parts):
            continue
        if should_exclude_file(path):
            continue
        yield path


def create_backup_full():
    now = datetime.now()
    day = now.strftime("%A")
    timestamp = now.strftime("%d-%m-%Y_%H-%M-%S")
    name = f"{day}_{timestamp}"
    dest = BACKUP_FULL_ROOT / name
    dest.mkdir(parents=True, exist_ok=True)

    manifest_lines = []
    count = 0
    for src in sorted(iter_project_files()):
        rel = src.relative_to(BASE)
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        manifest_lines.append(str(rel).replace("\\", "/"))
        count += 1

    with open(dest / "_MANIFEST.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(manifest_lines))

    print(f"\n✓ Comprehensive backup created: {name}")
    print(f"  Location: {dest}")
    print(f"  Total: {count} files")
    return dest


def restore_backup_full(backup_path: Path):
    manifest = backup_path / "_MANIFEST.txt"
    if not manifest.exists():
        print(f"✗ No manifest found in {backup_path.name}")
        return False

    restored = 0
    with open(manifest, encoding="utf-8") as f:
        for line in f:
            rel = line.strip()
            if not rel:
                continue
            src_file = backup_path / rel
            if not src_file.exists():
                print(f"  ✗ Missing in backup: {rel}")
                continue
            dst_file = BASE / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            restored += 1
    print(f"\n✓ Restored {restored} files from {backup_path.name}\n")
    return True


def format_backup_name(b, idx):
    parts = b.name.split("_")
    try:
        date_str = parts[1]
        time_str = parts[2]
        d, m, y  = date_str.split("-")
        h, mn, s = time_str.split("-")
        display  = f"{parts[0]} {d}/{m}/{y} {h}:{mn}:{s}"
    except Exception:
        display = b.name
    tag = "  ← LATEST" if idx == 0 else ""
    return display, tag


def main():
    print("=" * 60)
    print("NSE Pulse — Backup & Restore")
    print("=" * 60)

    print("\nOptions:")
    print("  b   — Create source backup (frontend/src + server.py)")
    print("  r   — Restore source backup")
    print("  cb  — Create comprehensive backup (data excluded)")
    print("  cr  — Restore comprehensive backup")
    print("  q  — Quit")

    choice = input("\nChoice: ").strip().lower()

    if choice == "b":
        create_backup()

    elif choice == "r":
        backups = list_backups(BACKUP_ROOT)
        if not backups:
            print("No backups found.")
            return

        print(f"\nAvailable backups ({len(backups)}):")
        print(f"{'─'*50}")
        for i, b in enumerate(backups):
            display, tag = format_backup_name(b, i)
            print(f"  r{i+1:02d}  {display}{tag}")
        print(f"{'─'*50}")

        sel = input("\nEnter backup number (e.g. r1) or Enter to quit: ").strip().lower()
        if not sel.startswith("r"):
            print("Cancelled.")
            return

        try:
            idx    = int(sel[1:]) - 1
            backup = backups[idx]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return

        display, tag = format_backup_name(backup, idx)
        print(f"\nSelected: {display}{tag}")
        confirm = input("Type YES to confirm restore: ").strip()
        if confirm != "YES":
            print("Cancelled.")
            return

        restore_backup(backup, BACKUP_ROOT)

    elif choice == "cb":
        create_backup_full()

    elif choice == "cr":
        backups = list_backups(BACKUP_FULL_ROOT)
        if not backups:
            print("No comprehensive backups found.")
            return

        print(f"\nAvailable comprehensive backups ({len(backups)}):")
        print(f"{'─'*56}")
        for i, b in enumerate(backups):
            display, tag = format_backup_name(b, i)
            print(f"  r{i+1:02d}  {display}{tag}")
        print(f"{'─'*56}")

        sel = input("\nEnter backup number (e.g. r1) or Enter to quit: ").strip().lower()
        if not sel.startswith("r"):
            print("Cancelled.")
            return

        try:
            idx = int(sel[1:]) - 1
            backup = backups[idx]
        except (ValueError, IndexError):
            print("Invalid selection.")
            return

        display, tag = format_backup_name(backup, idx)
        print(f"\nSelected: {display}{tag}")
        confirm = input("Type YES to confirm restore: ").strip()
        if confirm != "YES":
            print("Cancelled.")
            return

        restore_backup_full(backup)

    elif choice == "q":
        return
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
