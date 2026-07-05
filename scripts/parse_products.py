#!/usr/bin/env python3
"""
Parse the uploaded product files into a clean normalized list.
File 1: <num>\t<code>\t<barcode>\t<desc>\t<cat>\t<subcat>
File 2: <num>\t<barcode>\t<desc>
"""

import csv
from pathlib import Path

UPLOAD1 = "/home/z/my-project/upload/Pasted Content_1783208594796.txt"
UPLOAD2 = "/home/z/my-project/upload/ؤؤؤؤ.txt"
OUT = "/home/z/my-project/download/_work/products.csv"


def _clean_desc(text: str) -> str:
    """Clean and normalize a product description for search queries."""
    text = text.strip()
    # collapse whitespace
    text = " ".join(text.split())
    return text


def parse_file1(path: str):
    """File 1 columns: num, code, barcode, desc, cat, subcat"""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            num = parts[0].strip()
            code = parts[1].strip() if len(parts) > 1 else ""
            barcode = parts[2].strip() if len(parts) > 2 else ""
            desc = parts[3].strip() if len(parts) > 3 else ""
            cat = parts[4].strip() if len(parts) > 4 else ""
            subcat = parts[5].strip() if len(parts) > 5 else ""
            rows.append({
                "num": num,
                "code": code,
                "barcode": barcode,
                "desc": _clean_desc(desc),
                "cat": cat.strip(),
                "subcat": subcat.strip(),
                "source_file": "file1",
            })
    return rows


# Common category suffixes that appear at the end of file2 descriptions
_FILE2_CATEGORIES = [
    "REHABILITATION AND PHYSIOTHERAPY SUPPLIES SUPPLEMENTARY",
    "REHABILITATION AND PHYSIOTHERAPY SUPPLIES",
]


def parse_file2(path: str):
    """File 2 columns: num, barcode, desc (with category suffix)."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            num = parts[0].strip()
            barcode = parts[1].strip()
            desc = " ".join(parts[2:]).strip()
            cat = ""
            # strip a known category suffix if present
            for c in _FILE2_CATEGORIES:
                if desc.endswith(c):
                    desc = desc[: -len(c)].strip()
                    cat = c
                    break
            rows.append({
                "num": num,
                "code": "",
                "barcode": barcode,
                "desc": _clean_desc(desc),
                "cat": cat,
                "subcat": "",
                "source_file": "file2",
            })
    return rows


def main():
    r1 = parse_file1(UPLOAD1)
    r2 = parse_file2(UPLOAD2)
    print(f"File 1: {len(r1)} rows")
    print(f"File 2: {len(r2)} rows")
    print(f"Total:  {len(r1) + len(r2)} rows")
    all_rows = r1 + r2
    # de-dup by num (file1 first wins)
    seen = set()
    deduped = []
    for r in all_rows:
        if r["num"] in seen:
            continue
        seen.add(r["num"])
        deduped.append(r)
    print(f"Unique (by num): {len(deduped)}")
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["num", "code", "barcode", "desc", "cat", "subcat", "source_file"])
        w.writeheader()
        w.writerows(deduped)
    print(f"Wrote {OUT}")
    # sample
    print("\nSample from file1:")
    for r in r1[:3]:
        print(" ", r)
    print("\nSample from file2:")
    for r in r2[:3]:
        print(" ", r)


if __name__ == "__main__":
    main()
