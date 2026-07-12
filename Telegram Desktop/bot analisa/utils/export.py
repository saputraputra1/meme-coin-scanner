import json
import csv
from datetime import datetime
from pathlib import Path


def export_json(tokens: list, filename: str = None):
    if filename is None:
        filename = f"meme_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path = Path("exports") / filename
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False, default=str)
    return str(path)


def export_csv(tokens: list, filename: str = None):
    if filename is None:
        filename = f"meme_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path = Path("exports") / filename
    path.parent.mkdir(exist_ok=True)

    if not tokens:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("no data\n")
        return str(path)

    fieldnames = tokens[0].keys()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tokens)
    return str(path)
