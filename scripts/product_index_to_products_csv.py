#!/usr/bin/env python3
"""Create download/_work/products.csv from download/product_index.json when source products.csv is absent.

This is only a fallback. The best source is still a real products.csv generated from the
catalog/source files. If product_index.json is empty or invalid, this script writes a
header-only CSV so workflows fail gracefully instead of crashing with JSONDecodeError.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "download"
INDEX = DOWNLOAD / "product_index.json"
OUT = DOWNLOAD / "_work" / "products.csv"
FIELDS = ["num", "code", "barcode", "desc", "cat", "subcat", "source_file"]


def write_rows(rows: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def safe_load_index() -> dict:
    if not INDEX.exists():
        print(f"WARNING: missing {INDEX}; writing header-only {OUT}")
        return {"byCode": {}, "byBarcode": {}, "byDesc": []}
    text = INDEX.read_text(encoding="utf-8").strip()
    if not text:
        print(f"WARNING: {INDEX} is empty; writing header-only {OUT}")
        return {"byCode": {}, "byBarcode": {}, "byDesc": []}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"WARNING: invalid JSON in {INDEX}: {exc}; writing header-only {OUT}")
        return {"byCode": {}, "byBarcode": {}, "byDesc": []}
    return data if isinstance(data, dict) else {"byCode": {}, "byBarcode": {}, "byDesc": []}


def main() -> None:
    data = safe_load_index()
    rows: dict[str, dict] = {}

    for code, item in (data.get("byCode") or {}).items():
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        row = rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})
        row["code"] = str(code).strip().upper()
        if item.get("desc") and len(item.get("desc", "")) > len(row.get("desc", "")):
            row["desc"] = item.get("desc", "")

    for barcode, item in (data.get("byBarcode") or {}).items():
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        row = rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})
        row["barcode"] = str(barcode).strip()
        if item.get("desc") and len(item.get("desc", "")) > len(row.get("desc", "")):
            row["desc"] = item.get("desc", "")

    for item in (data.get("byDesc") or []):
        num = str(item.get("num", "")).strip()
        if not num:
            continue
        rows.setdefault(num, {"num": num, "code": "", "barcode": "", "desc": item.get("desc", ""), "cat": "", "subcat": "", "source_file": "product_index"})

    ordered = sorted(rows.values(), key=lambda x: int(x["num"]) if str(x["num"]).isdigit() else str(x["num"]))
    write_rows(ordered)
    print(f"Wrote {OUT}: {len(ordered)} rows")


if __name__ == "__main__":
    main()
