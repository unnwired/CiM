import os
import shutil
from pathlib import Path

backup_root = Path(r"D:\Programs\NSE Pulse\Claude Ai\backups")
src_dir     = Path(r"D:\Programs\NSE Pulse\Claude Ai\frontend\src")

# Find all backup folders
backup_folders = [f for f in backup_root.iterdir() if f.is_dir() and f.name != 'db']
if not backup_folders:
    print("No backups found.")
    exit()

all_backups = sorted(backup_folders)

print("=" * 60)
print("NSE PULSE — BACKUP RESTORE")
print("=" * 60)
print(f"\nRestore target: {src_dir}")
print("\nAvailable backups:")
print()
for i, b in enumerate(all_backups):
    marker = " ← latest" if b == all_backups[-1] else ""
    print(f"  r{i+1}  {b.name}{marker}")

print()
print("To restore, type r followed by the backup number (e.g. r3)")
print("Press Enter with no input to quit.")
print()

choice = input("Your choice: ").strip()

if choice == '':
    print("No input. Restore cancelled.")
    exit()

if not choice.lower().startswith('r'):
    print("Invalid input. Must start with 'r' (e.g. r1, r2). Restore cancelled.")
    exit()

try:
    idx = int(choice[1:]) - 1
    if idx < 0 or idx >= len(all_backups):
        print(f"Invalid backup number. Must be between r1 and r{len(all_backups)}. Restore cancelled.")
        exit()
    selected = all_backups[idx]
except ValueError:
    print("Invalid input. Must be r followed by a number (e.g. r1). Restore cancelled.")
    exit()

print()
print(f"  Selected backup: {selected.name}")
print(f"  This will OVERWRITE all current JS/CSS files in src/")
print(f"  This action cannot be undone.")
print()
confirm = input("Type YES to confirm: ").strip()

if confirm != 'YES':
    print("Restore cancelled.")
    exit()

# Read manifest
manifest = selected / "_MANIFEST.txt"
if not manifest.exists():
    print("No manifest found in this backup. Cannot restore safely.")
    exit()

print("\nRestoring files...")
print()
restored = 0
failed   = 0

with open(manifest, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if "-->" not in line:
            continue
        parts     = line.split("  -->  ")
        flat_name = parts[0].strip()
        rel_path  = parts[1].strip().replace("src\\", "", 1)
        src_file  = selected / flat_name
        dst_file  = src_dir / rel_path

        if not src_file.exists():
            print(f"  MISSING: {flat_name}")
            failed += 1
            continue

        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        print(f"  ✓ {rel_path}")
        restored += 1

print()
print("=" * 60)
print(f"✓ Restored: {restored} files")
if failed:
    print(f"✗ Failed:   {failed} files")
print(f"From:       {selected.name}")
print("=" * 60)
print("\nRestart the frontend dev server to apply changes.")
