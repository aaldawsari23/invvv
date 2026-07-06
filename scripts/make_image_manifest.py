#!/usr/bin/env python3
"""
Create an approved image manifest from trusted_scrape_log.csv.

Only rows produced by the trusted scraper are allowed into the site image index.
Old/random images may stay in download/product_images, but they will not be used
unless they appear here as approved.
"""
import csv
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "download"
WORK = DOWNLOAD / "_work"
IMG_DIR = DOWNLOAD / "product_images"
TRUSTED_LOG = WORK / "trusted_scrape_log.csv"
OUT = WORK / "image_manifest.csv"

APPROVED_STATUSES = {"ok_new", "ok_replaced", "ok", "ok_retry"}
MIN_SCORE = 62

TRUSTED_DOMAINS = {
    "performancehealth.com", "rehabmart.com", "alimed.com", "meyerpt.com",
    "medline.com", "medicaleshop.com", "physiosupplies.com", "physioparts.co.uk",
    "promedics.co.uk", "henryschein.com", "fabricationenterprises.com",
    "scriphessco.com", "sourceortho.net", "healthproductsforyou.com",
    "djoglobal.com", "chattanoogarehab.com", "enovis.com", "theraband.com",
    "invacare.com", "drivemedical.com", "ottobock.com", "permobil.com",
    "sunrisemedical.com", "etac.com", "biodex.com", "jtechmedical.com",
    "btlnet.com", "enraf-nonius.com", "dynatronics.com", "richmarweb.com",
    "whitehallmfg.com", "hausmann.com", "clinton-ind.com", "tumbleforms.com",
    "boundtree.com", "quickmedical.com", "schoolhealth.com", "vitalitymedical.com",
    "nupco.com", "sfda.gov.sa"
}

REJECT_DOMAINS = {
    "pinterest.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "reddit.com", "linkedin.com", "alamy.com",
    "shutterstock.com", "istockphoto.com", "gettyimages.com", "dreamstime.com",
    "depositphotos.com", "freepik.com", "pngtree.com", "vecteezy.com",
    "123rf.com", "canva.com", "blogspot.com", "wordpress.com",
    "wikimedia.org", "wikipedia.org"
}


def host(url: str) -> str:
    h = urlparse(url or "").netloc.lower()
    return h[4:] if h.startswith("www.") else h


def domain_matches(h: str, domains: set[str]) -> bool:
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def approved(row: dict) -> tuple[bool, str]:
    num = (row.get("num") or "").strip()
    status = (row.get("status") or "").strip()
    score_raw = (row.get("score") or "0").strip()
    url = row.get("source_url") or row.get("page_url") or ""
    domain = (row.get("domain") or host(url)).strip().lower()
    img = f"{num}.jpg"

    try:
        score = int(float(score_raw or 0))
    except Exception:
        score = 0

    if not num:
        return False, "missing num"
    if status not in APPROVED_STATUSES:
        return False, f"bad status: {status}"
    if score < MIN_SCORE:
        return False, f"low score: {score}"
    if domain_matches(domain, REJECT_DOMAINS):
        return False, f"rejected domain: {domain}"
    if not domain_matches(domain, TRUSTED_DOMAINS):
        return False, f"untrusted domain: {domain}"
    if not (IMG_DIR / img).exists():
        return False, "image file missing"
    if (IMG_DIR / img).stat().st_size < 2048:
        return False, "image file too small"
    return True, "approved"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    rows = []
    if TRUSTED_LOG.exists():
        with open(TRUSTED_LOG, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                ok, reason = approved(r)
                num = (r.get("num") or "").strip()
                if not num:
                    continue
                rows.append({
                    "num": num,
                    "img": f"{num}.jpg" if ok else "",
                    "status": "approved" if ok else "rejected",
                    "confidence": r.get("score", "0"),
                    "source_domain": (r.get("domain") or host(r.get("source_url") or r.get("page_url") or "")),
                    "source_url": r.get("source_url", ""),
                    "reason": reason,
                })

    # keep the latest row per num, prefer approved over rejected
    by_num = {}
    for r in rows:
        old = by_num.get(r["num"])
        if old is None or (old["status"] != "approved" and r["status"] == "approved"):
            by_num[r["num"]] = r

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["num", "img", "status", "confidence", "source_domain", "source_url", "reason"])
        w.writeheader()
        w.writerows(sorted(by_num.values(), key=lambda x: int(x["num"]) if x["num"].isdigit() else x["num"]))

    approved_count = sum(1 for r in by_num.values() if r["status"] == "approved")
    print(f"Wrote {OUT}")
    print(f"Approved images: {approved_count:,}")
    print(f"Rejected/unapproved: {len(by_num) - approved_count:,}")


if __name__ == "__main__":
    main()
