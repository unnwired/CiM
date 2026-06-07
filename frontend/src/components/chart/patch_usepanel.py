path = r"D:\Programs\NSE Pulse\Claude Ai\frontend\src\components\chart\ChartContainer.js"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = "      if (width <= 0 || height <= 0) return;"
new = "      if (width <= 0 || height <= 0 || !Number.isFinite(width) || !Number.isFinite(height)) return;\n      if (width < 10 || height < 10) return;"

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch applied.")
else:
    print("Target not found. Paste current usePanel guard line here.")