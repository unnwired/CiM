import sys
from pathlib import Path
sys.path.insert(0, r"D:\Programs\NSE Pulse\Claude Ai")
from server.app_code_crypto import install_key_for_machine
mc = "F1927C3F4CCD33A733DD8AECEFDA6469"
if len(sys.argv) > 1 and sys.argv[1]:
    print(install_key_for_machine(mc, base_dir=Path(sys.argv[1])))
else:
    print(install_key_for_machine(mc))
