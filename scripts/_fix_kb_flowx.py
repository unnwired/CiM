from pathlib import Path
import re
for rel in ("data/knowledge_base.json", "server/knowledge_base.py"):
    p = Path(__file__).resolve().parent.parent / rel
    t = p.read_text(encoding="utf-8")
    t = t.replace("FlowX's", "Charts In Motion's")
    t = re.sub(r"\bFlowX\b", "Charts In Motion", t)
    p.write_text(t, encoding="utf-8")
print("done")
