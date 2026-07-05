#!/usr/bin/env python3
"""
Retry script for failed products.
Strategy: for "X RELATED TO Y" items, search for "Y" (the parent product).
Also try without the medical context suffix which can sometimes hurt results.
"""
import csv
import sys
from pathlib import Path

# Add the main script's directory to path
sys.path.insert(0, "/home/z/my-project/scripts")
from scrape_images import (
    OUT_DIR, LOG_CSV, fetch_image_for_product, log, _session,
    search_bing, search_duckduckgo, search_yandex, search_brave,
    _download_image, _validate_and_process, _is_bad_url,
    MAX_CANDIDATES, build_query, _NOISE_WORDS, _MEDICAL_HINTS,
)
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


LOG_CSV_RETRY = Path("/home/z/my-project/download/_work/scrape_retry_log.csv")


def build_retry_query(rec: dict) -> list[str]:
    """Build a list of alternative queries to try."""
    desc = rec.get("desc", "").strip()
    code = rec.get("code", "").strip()
    sub  = rec.get("subcat", "").strip()

    queries = []

    # Strategy 1: For "X RELATED TO Y" items, search for the parent product Y
    if " RELATED TO " in desc.upper():
        idx = desc.upper().find(" RELATED TO ")
        parent = desc[idx + len(" RELATED TO "):].strip()
        # clean parent
        parent_words = re.findall(r"[A-Za-z0-9+\-/&]+", parent.upper())
        parent_words = [w for w in parent_words if w not in _NOISE_WORDS and len(w) > 1]
        parent_words = [w for w in parent_words if not re.fullmatch(r"[\d.\-/+]+", w)]
        parent_words = parent_words[:5]
        if parent_words:
            queries.append(" ".join(parent_words) + " medical equipment")

    # Strategy 2: Just the description with category context
    main_desc = desc
    if " RELATED TO " in desc.upper():
        idx = desc.upper().find(" RELATED TO ")
        main_desc = desc[:idx].strip()
    words = re.findall(r"[A-Za-z0-9+\-/&]+", main_desc.upper())
    words = [w for w in words if w not in _NOISE_WORDS and len(w) > 1]
    words = [w for w in words if not re.fullmatch(r"[\d.\-/+]+", w)]
    if words:
        # Try with fewer words + no medical suffix
        queries.append(" ".join(words[:3]))
        # Try with medical suffix
        if not any(h in " ".join(words).lower() for h in _MEDICAL_HINTS):
            queries.append(" ".join(words[:4]) + " medical")

    # Strategy 3: Original query (try once more in case it was a transient failure)
    queries.append(build_query(rec))

    # Dedupe while preserving order
    seen = set()
    unique = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:4]  # max 4 attempts


def fetch_with_retry(rec: dict) -> dict:
    """Try multiple queries with multiple engines."""
    session = _session()
    queries = build_retry_query(rec)

    for q in queries:
        for engine_name, engine_fn in [
            ("bing",       search_bing),
            ("duckduckgo", search_duckduckgo),
            ("yandex",     search_yandex),
            ("brave",      search_brave),
        ]:
            try:
                urls = engine_fn(session, q)
            except Exception:
                urls = []
            for u in urls:
                if _is_bad_url(u):
                    continue
                raw = _download_image(session, u)
                if not raw:
                    continue
                processed = _validate_and_process(raw)
                if processed:
                    return {
                        "status": "ok",
                        "engine": engine_name,
                        "source_url": u,
                        "query": q,
                        "bytes": processed,
                    }
    return {"status": "no_image", "engine": "retry", "source_url": "",
            "query": " | ".join(queries), "bytes": b""}


def process_one_retry(rec: dict) -> dict:
    num = rec["num"]
    out_path = OUT_DIR / f"{num}.jpg"
    if out_path.exists() and out_path.stat().st_size > 1024:
        return {
            "num": num, "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", "")[:200],
            "query": "", "status": "already_ok", "engine": "cache",
            "source_url": "", "img_path": str(out_path),
            "img_size_kb": round(out_path.stat().st_size / 1024, 1),
        }
    res = fetch_with_retry(rec)
    if res["status"] == "ok":
        with open(out_path, "wb") as f:
            f.write(res["bytes"])
        size_kb = round(len(res["bytes"]) / 1024, 1)
        return {
            "num": num, "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", "")[:200],
            "query": res["query"], "status": "ok_retry",
            "engine": res["engine"], "source_url": res["source_url"],
            "img_path": str(out_path), "img_size_kb": size_kb,
        }
    return {
        "num": num, "code": rec.get("code", ""),
        "barcode": rec.get("barcode", ""),
        "desc": rec.get("desc", "")[:200],
        "query": res["query"], "status": "no_image",
        "engine": "retry", "source_url": "",
        "img_path": "", "img_size_kb": 0,
    }


def main():
    # Find all products that don't have an image yet
    products_csv = "/home/z/my-project/download/_work/products.csv"
    all_products = {}
    with open(products_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            all_products[r["num"]] = r

    # Find missing
    missing = []
    for num, rec in all_products.items():
        out_path = OUT_DIR / f"{num}.jpg"
        if not out_path.exists() or out_path.stat().st_size <= 1024:
            missing.append(rec)
    log.info("Retry: %d products missing images", len(missing))
    if not missing:
        return

    write_header = not LOG_CSV_RETRY.exists()
    f = open(LOG_CSV_RETRY, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=[
        "num", "code", "barcode", "desc", "query",
        "status", "engine", "source_url", "img_path", "img_size_kb",
    ])
    if write_header:
        w.writeheader()

    completed = 0
    ok = 0
    start = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(process_one_retry, p): p for p in missing}
        for fut in as_completed(futures):
            rec = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                log.error("Retry error for %s: %s", rec.get("num"), e)
                continue
            w.writerow(result)
            f.flush()
            completed += 1
            if result["status"].startswith("ok"):
                ok += 1
                log.info("  retry OK: #%s via %s — %s",
                         result["num"], result["engine"], result["desc"][:60])
            if completed % 10 == 0 or completed == len(missing):
                elapsed = time.time() - start
                log.info("Retry progress: %d/%d  ok=%d  elapsed=%.0fs",
                         completed, len(missing), ok, elapsed)
    f.close()
    log.info("Retry DONE. ok=%d/%d", ok, len(missing))


if __name__ == "__main__":
    main()
