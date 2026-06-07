import shutil
from datetime import datetime
from pathlib import Path

src = Path(r"D:\Programs\NSE Pulse\Claude Ai\data\nse_data.db")
bak_dir = Path(r"D:\Programs\NSE Pulse\Claude Ai\backups\db")
bak_dir.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%A_%d-%m-%Y_%H-%M-%S")
dst = bak_dir / f"nse_data_{timestamp}.db"

print(f"Backing up {src.stat().st_size / (1024**3):.2f} GB...")
shutil.copy2(src, dst)
print(f"✓ Backup saved to: {dst}")
