#!/usr/bin/env python3
"""
Stage 3: trusted image candidate collector.

This script does not approve images and does not write product_index.json.
It uses scrape_images_trusted.py for search/scoring/image validation, then writes
Stage-3-normalized logs for the later manifest approval stage.
"""
from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from scrape_images_trusted import (
    BACKUP_DIR,
    OUT_DIR,
    PRODUCTS_CSV,
    WORK_DIR,
    best_image,
    host,
    load_products,
    setup_logging,
)

TRUSTED_LOG = WORK_DIR / "trusted_scrape_log.csv"
REJECTED_LOG = WORK_DIR / "rejected_image_candidates.csv"
REVIEW_LOG = WORK_DIR / "review_image_candidates.csv"
DEFAULT_MIN_SCORE = 70
DEFAULT_REVIEW_SCORE = 55
DEFAULT_WORKERS = 3

FIELDS = [
    "num",
    "code",
    "barcode",
    "desc",
    "query",
    "status",
    "score",
    "source_domain",
    "source_url",
    "page_url",
    "img_path",
    "matched_by",
    "matched_terms",
    "reason",
]


def infer_matched_by(rec: dict, candidate) -> str:
    text = " ".join([candidate.title or "", candidate.image_url or "", candidate.page_url or "", candidate.query or ""]).upper()
    code = str(rec.get("code", "")).strip().upper()
    barcode = str(rec.get("barcode", "")).strip().upper()
    if code and code in text:
        return "code"
    if barcode and barcode in text:
        return "barcode"
    return "description"


def infer_matched_terms(rec: dict, candidate) -> str:
    desc = str(rec.get("desc", "")).upper()
    text = " ".join([candidate.title or "", candidate.image_url or "", candidate.page_url or "", candidate.query or ""]).upper()
    terms = []
    for t in desc.replace(",", " ").replace("/", " ").split():
        t = t.strip(" .;:-_()[]{}")
        if len(t) > 3 and t in text and t not in terms:
            terms.append(t)
        if len(terms) >= 12:
            break
    return " ".join(terms)


def out_path_for(rec: dict) -> Path:
    return OUT_DIR / f"{str(rec.get('num', '')).strip()}.jpg"


def write_candidate_image(rec: dict, data: bytes, replace: bool, dry_run: bool) -> tuple[str, str]:
    out = out_path_for(rec)
    existed = out.exists() and out.stat().st_size > 1024
    if dry_run:
        return "dry_run_candidate", ""
    if existed and not replace:
        return "skipped_existing", str(out)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if existed and replace:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / out.name
        if not backup.exists():
            shutil.copy2(out, backup)
    out.write_bytes(data)
    return "candidate_saved", str(out)


def log_row(rec: dict, status: str, candidate=None, img_path: str = "", reason: str = "") -> dict:
    if candidate is None:
        return {
            "num": rec.get("num", ""),
            "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", ""),
            "query": "",
            "status": status,
            "score": 0,
            "source_domain": "",
            "source_url": "",
            "page_url": "",
            "img_path": img_path,
            "matched_by": "",
            "matched_terms": "",
            "reason": reason,
        }
    domain = candidate.domain or host(candidate.page_url) or host(candidate.image_url)
    return {
        "num": rec.get("num", ""),
        "code": rec.get("code", ""),
        "barcode": rec.get("barcode", ""),
        "desc": rec.get("desc", ""),
        "query": candidate.query,
        "status": status,
        "score": candidate.final_score or candidate.meta_score or 0,
        "source_domain": domain,
        "source_url": candidate.image_url,
        "page_url": candidate.page_url,
        "img_path": img_path,
        "matched_by": infer_matched_by(rec, candidate),
        "matched_terms": infer_matched_terms(rec, candidate),
        "reason": reason or candidate.reason,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def process(rec: dict, args) -> dict:
    try:
        candidate, data = best_image(rec, args.review_score, trusted_only=True)
        if not candidate or not data:
            return log_row(rec, "rejected", reason="no technically valid trusted candidate")
        score = candidate.final_score or candidate.meta_score or 0
        if score >= args.min_score:
            status, img_path = write_candidate_image(rec, data, args.replace, args.dry_run)
            return log_row(rec, status, candidate, img_path, candidate.reason)
        return log_row(rec, "review", candidate, "", f"score below approval threshold: {score} < {args.min_score}; {candidate.reason}")
    except Exception as e:
        return log_row(rec, "failed", reason=str(e))


def main() -> int:
    setup_logging()
    ap = argparse.ArgumentParser(description="Stage 3 trusted image candidate collector")
    ap.add_argument("--products", default=str(PRODUCTS_CSV))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", default="")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--review-score", type=int, default=DEFAULT_REVIEW_SCORE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ids = {x.strip() for x in args.ids.split(",") if x.strip()} or None
    products = load_products(Path(args.products), args.limit, ids)
    rows = [process(rec, args) for rec in products]

    write_csv(TRUSTED_LOG, rows)
    write_csv(REJECTED_LOG, [r for r in rows if r["status"] in {"rejected", "failed"}])
    write_csv(REVIEW_LOG, [r for r in rows if r["status"] == "review"])

    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("Stage 3 complete")
    print(f"products_tested: {len(products)}")
    for k in sorted(counts):
        print(f"{k}: {counts[k]}")
    print(f"wrote: {TRUSTED_LOG}")
    print(f"wrote: {REJECTED_LOG}")
    print(f"wrote: {REVIEW_LOG}")
    print("No image approval performed. product_index.json was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
