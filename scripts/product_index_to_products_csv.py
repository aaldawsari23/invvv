#!/usr/bin/env python3
"""Create download/_work/products.csv from download/product_index.json when source products.csv is absent."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "download"
INDEX = DOWNLOAD / "product_index.json"
OUT = DOWNLOAD / "_work" / "products.csv"


def main():
    if not INDEX.exists():
        raise FileNotFoundError(f"Missing {INDEX}")
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = {}

    for code, item in (data.get("byCode") or {}).items():
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        r = rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})
        r["code"] = code
        if item.get("desc") and len(item.get("desc", "")) > len(r.get("desc", "")):
            r["desc"] = item.get("desc", "")

    for barcode, item in (data.get("byBarcode") or {}).items():
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        r = rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})
        r["barcode"] = barcode
        if item.get("desc") and len(item.get("desc", "")) > len(r.get("desc", "")):
            r["desc"] = item.get("desc", "")

    for item in (data.get("byDesc") or []):
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["num", "code", "barcode", "desc", "cat", "subcat", "source_file"])
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda x: int(x["num"]) if x["num"].isdigit() else x["num"]))
    print(f"Wrote {OUT}: {len(rows)} rows")


if __name__ == "__main__":
    main()
