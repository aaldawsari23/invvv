#!/usr/bin/env python3
"""Stage 2 products.csv builder.

Purpose:
- Produce/validate download/_work/products.csv as the canonical product table.
- Keep a stable command name for the Stage 2 workflow.

Current behavior:
1. If download/_work/products.csv already exists, validate it.
2. Otherwise, build a fallback CSV from download/product_index.json.
3. Print row counts and key quality metrics.

Note:
This wrapper cannot recreate rich product descriptions from image filenames alone.
For production quality, upload or generate a real products.csv from the source catalog files.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = ROOT / "download" / "_work" / "products.csv"
FALLBACK = ROOT / "scripts" / "product_index_to_products_csv.py"
REQUIRED = ["num", "code", "barcode", "desc", "cat", "subcat", "source_file"]


def run_fallback() -> None:
    subprocess.run([sys.executable, str(FALLBACK)], cwd=str(ROOT), check=True)


def validate() -> None:
    if not PRODUCTS.exists():
        raise FileNotFoundError(f"Missing {PRODUCTS}")

    with PRODUCTS.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        missing = [c for c in REQUIRED if c not in fields]
        if missing:
            raise ValueError(f"products.csv missing columns: {missing}")

        total = 0
        nums = set()
        duplicate_nums = 0
        missing_desc = 0
        with_code = 0
        with_barcode = 0
        for row in reader:
            total += 1
            num = str(row.get("num", "")).strip()
            desc = str(row.get("desc", "")).strip()
            if num in nums:
                duplicate_nums += 1
            if num:
                nums.add(num)
            if not desc:
                missing_desc += 1
            if str(row.get("code", "")).strip():
                with_code += 1
            if str(row.get("barcode", "")).strip():
                with_barcode += 1

    print(f"products.csv: {PRODUCTS}")
    print(f"rows: {total:,}")
    print(f"unique num: {len(nums):,}")
    print(f"duplicate num rows: {duplicate_nums:,}")
    print(f"missing desc: {missing_desc:,}")
    print(f"with code: {with_code:,}")
    print(f"with barcode: {with_barcode:,}")

    if total == 0:
        print("WARNING: products.csv is header-only. Upload/generate source catalog rows for production.")


def main() -> None:
    if not PRODUCTS.exists():
        print("products.csv not found; building fallback from product_index.json")
        run_fallback()
    validate()


if __name__ == "__main__":
    main()
