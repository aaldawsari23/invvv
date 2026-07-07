#!/usr/bin/env python3
"""
Build a compact JSON reference index for the PT Inventory Analyzer.

Input:  download/_work/products.csv
Output: download/product_index.json

Expected CSV columns:
  num, code, barcode, desc, cat, subcat, source_file

Important behavior:
- The index includes products even when a product image is missing.
- The `img` field is empty unless download/product_images/<num>.jpg exists.
- Duplicate codes/barcodes keep the first complete row and ignore later empty duplicates.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "download"
PRODUCTS_CSV = DOWNLOAD / "_work" / "products.csv"
IMG_DIR = DOWNLOAD / "product_images"
OUT = DOWNLOAD / "product_index.json"


def clean(value: object) -> str:
    return str(value or "").strip()


def image_for(num: str) -> str:
    name = f"{num}.jpg"
    return name if (IMG_DIR / name).exists() else ""


def choose(existing: dict | None, entry: dict) -> dict:
    """Prefer an existing populated entry; otherwise keep the new one."""
    if not existing:
        return entry
    if len(clean(entry.get("desc"))) > len(clean(existing.get("desc"))):
        merged = dict(existing)
        merged.update({k: v for k, v in entry.items() if v})
        return merged
    return existing


def main() -> None:
    if not PRODUCTS_CSV.exists():
        raise FileNotFoundError(
            f"Missing {PRODUCTS_CSV}. Build or upload products.csv before rebuilding the index."
        )

    by_code: dict[str, dict] = {}
    by_barcode: dict[str, dict] = {}
    by_desc: list[dict] = []
    seen_desc_nums: set[str] = set()
    total = 0
    skipped = 0

    with open(PRODUCTS_CSV, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"num", "desc"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"products.csv missing required columns: {sorted(missing)}")

        for row in reader:
            total += 1
            num = clean(row.get("num"))
            desc = clean(row.get("desc"))
            if not num or not desc:
                skipped += 1
                continue

            code = clean(row.get("code")).upper()
            barcode = clean(row.get("barcode"))
            entry = {
                "num": num,
                "desc": desc[:240],
                "img": image_for(num),
            }

            if code:
                by_code[code] = choose(by_code.get(code), entry)
            if barcode:
                by_barcode[barcode] = choose(by_barcode.get(barcode), entry)
            if num not in seen_desc_nums:
                seen_desc_nums.add(num)
                by_desc.append({"num": num, "desc": desc[:180].upper(), "img": entry["img"]})

    out = {"byCode": by_code, "byBarcode": by_barcode, "byDesc": by_desc}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"Wrote {OUT}")
    print(f"  rows read:  {total:,}")
    print(f"  skipped:    {skipped:,}")
    print(f"  byCode:     {len(by_code):,}")
    print(f"  byBarcode:  {len(by_barcode):,}")
    print(f"  byDesc:     {len(by_desc):,}")
    print(f"  size:       {OUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
