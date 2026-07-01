path = r"D:\Programs\NSE Pulse\Claude Ai\server\server.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = '''    def zip_with_time(values: list) -> list:
        return [
            {"time": times[i], "value": v}
            for i, v in enumerate(values)
            if v is not None and i < len(times)
        ]'''

new = '''    def zip_with_time(values: list) -> list:
        return [
            {"time": times[i], "value": v}
            for i, v in enumerate(values)
            if v is not None and i < len(times)
        ]

    def zip_with_time_padded(values: list) -> list:
        """
        Same as zip_with_time but pads None entries with the correct
        timestamp so the series always starts at the same time as price bars.
        This ensures lightweight-charts aligns all panels by time correctly.
        """
        result = []
        for i, v in enumerate(values):
            if i >= len(times):
                break
            if v is not None:
                result.append({"time": times[i], "value": v})
        return result'''

if old in content:
    content = content.replace(old, new)
    print("zip_with_time_padded added.")
else:
    print("ERROR: zip_with_time block not found.")
    exit()

# Replace stochrsi zip calls
old2 = '''    stochrsi  = {
        "k": zip_with_time(stoch["k"]),
        "d": zip_with_time(stoch["d"]),
    }'''

new2 = '''    stochrsi  = {
        "k": zip_with_time_padded(stoch["k"]),
        "d": zip_with_time_padded(stoch["d"]),
    }'''

if old2 in content:
    content = content.replace(old2, new2)
    print("StochRSI zip replaced.")
else:
    print("ERROR: StochRSI zip block not found.")

# Replace macd zip calls
old3 = '''    macd_out  = {
        "macd":      zip_with_time(macd_data["macd"]),
        "signal":    zip_with_time(macd_data["signal"]),
        "histogram": zip_with_time(macd_data["histogram"]),
    }'''

new3 = '''    macd_out  = {
        "macd":      zip_with_time_padded(macd_data["macd"]),
        "signal":    zip_with_time_padded(macd_data["signal"]),
        "histogram": zip_with_time_padded(macd_data["histogram"]),
    }'''

if old3 in content:
    content = content.replace(old3, new3)
    print("MACD zip replaced.")
else:
    print("ERROR: MACD zip block not found.")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("\nDone. Restart uvicorn.")
