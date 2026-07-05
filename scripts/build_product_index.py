#!/usr/bin/env python3
"""
Build a compact JSON index of products for the PT Inventory Analyzer.
Output: product_index.json
  {
    "byCode": { "MGE30003": {"num":"1212","desc":"...","img":"1212.jpg"}, ... },
    "byBarcode": { "4214000006900": {"num":"1212",...}, ... },
    "byDesc": [ {"num":"1212","desc":"STOOL EXAMINATION","img":"1212.jpg"}, ... ]
  }
"""
import csv
import json
from pathlib import Path

ROOT = Path("/home/z/my-project/download")
PRODUCTS_CSV = ROOT / "_work/products.csv"
IMG_DIR = ROOT / "product_images"
OUT = ROOT / "product_index.json"


def main():
    by_code = {}
    by_barcode = {}
    by_desc = []

    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            num = r["num"]
            code = (r.get("code") or "").strip().upper()
            barcode = (r.get("barcode") or "").strip()
            desc = (r.get("desc") or "").strip()
            img = f"{num}.jpg"
            # Only include if image actually exists
            if not (IMG_DIR / img).exists():
                continue
            entry = {
                "num": num,
                "desc": desc[:200],  # truncate for size
                "img": img,
            }
            if code:
                by_code[code] = entry
            if barcode:
                by_barcode[barcode] = entry
            if desc:
                by_desc.append({
                    "num": num,
                    "desc": desc[:120].upper(),
                    "img": img,
                })

    out = {
        "byCode": by_code,
        "byBarcode": by_barcode,
        "byDesc": by_desc,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  byCode:    {len(by_code):,} entries")
    print(f"  byBarcode: {len(by_barcode):,} entries")
    print(f"  byDesc:    {len(by_desc):,} entries")
    print(f"  Size: {OUT.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    main()
