#!/usr/bin/env python3
"""
Trusted image scraper for PT / Rehab products.

This does NOT accept the first random valid image.
It scores candidates by trusted medical/rehab domains, code/barcode/description overlap,
and image quality. Existing images are replaced only with --replace.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import os
import random
import re
import shutil
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = ROOT / "download"
WORK_DIR = DOWNLOAD_DIR / "_work"
PRODUCTS_CSV = WORK_DIR / "products.csv"
OUT_DIR = DOWNLOAD_DIR / "product_images"
BACKUP_DIR = DOWNLOAD_DIR / "product_images_old"
LOG_CSV = WORK_DIR / "trusted_scrape_log.csv"
AUDIT_CSV = WORK_DIR / "suspect_existing_images.csv"
LOG_FILE = WORK_DIR / "trusted_scrape.log"

MAX_SIZE = 700
JPEG_QUALITY = 88
MIN_DIM = 240
MAX_ASPECT = 2.8
TIMEOUT_SEARCH = 18
TIMEOUT_IMAGE = 22
MAX_CANDIDATES = 8
MAX_BYTES = 8_000_000
DEFAULT_MIN_SCORE = 62
DEFAULT_WORKERS = 8
PER_ENGINE_DELAY = (0.3, 0.6)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
]

TRUSTED_DOMAINS = {
    "performancehealth.com", "rehabmart.com", "alimed.com", "meyerpt.com",
    "medline.com", "medicaleshop.com", "physiosupplies.com", "physioparts.co.uk",
    "promedics.co.uk", "henryschein.com", "pattersonmedical.com",
    "fabricationenterprises.com", "scriphessco.com", "sourceortho.net",
    "healthproductsforyou.com", "cascade-usa.com", "activeforever.com",
    "djoglobal.com", "chattanoogarehab.com", "enovis.com", "theraband.com",
    "invacare.com", "drivemedical.com", "grahamfield.com", "arjo.com",
    "ottobock.com", "permobil.com", "sunrisemedical.com", "etac.com",
    "biodex.com", "jtechmedical.com", "seca.com", "btlnet.com",
    "enraf-nonius.com", "dynatronics.com", "richmarweb.com",
    "mettlerelectronics.com", "whitehallmfg.com", "hausmann.com",
    "clinton-ind.com", "tumbleforms.com", "optecusa.com",
    "boundtree.com", "quickmedical.com", "schoolhealth.com", "vitalitymedical.com",
    "nupco.com", "sfda.gov.sa", "amazon.com", "noon.com", "ubuy.com.sa",
}

REJECT_DOMAINS = {
    "pinterest.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "reddit.com", "linkedin.com",
    "alamy.com", "shutterstock.com", "istockphoto.com", "gettyimages.com",
    "dreamstime.com", "depositphotos.com", "freepik.com", "pngtree.com",
    "vecteezy.com", "123rf.com", "canva.com", "blogspot.com", "wordpress.com",
    "wikimedia.org", "wikipedia.org",
}

BAD_FRAGMENTS = (
    "favicon", "logo", "sprite", "icon", "placeholder", "no-image", "not-found",
    "coming-soon", "blank", "pixel", "loading", "default-image", "avatar", "profile",
)
BAD_EXT = (".svg", ".gif", ".webp", ".avif")
GOOD_EXT = (".jpg", ".jpeg", ".png", ".bmp")
NOISE = {
    "RELATED", "TO", "EACH", "PAIR", "PACK", "OF", "ASSORTED", "DISPENSER",
    "BOX", "INDIVIDUALLY", "WRAPPED", "SIZE", "CM", "MM", "INCH", "WITH",
    "WITHOUT", "SET", "UNIT", "PATIENT", "ADULT", "SMALL", "MEDIUM", "LARGE",
    "GENERAL", "MEDICAL", "HOSPITAL", "SUPPLY", "SUPPLIES", "EQUIPMENT",
    "STANDARD", "PORTABLE", "FOR", "AND", "OR", "THE",
}
STRICT_CONTEXT = "medical rehabilitation physiotherapy equipment"

_locks = {k: Lock() for k in ("bing", "duckduckgo", "google")}
_last = {k: 0.0 for k in _locks}

@dataclass
class Candidate:
    image_url: str
    page_url: str = ""
    title: str = ""
    engine: str = ""
    query: str = ""
    rank: int = 0
    domain: str = ""
    meta_score: int = 0
    final_score: int = 0
    reason: str = ""


def setup_logging():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)

log = logging.getLogger("trusted-images")


def rate_limit(engine: str):
    with _locks[engine]:
        elapsed = time.time() - _last[engine]
        wait = random.uniform(*PER_ENGINE_DELAY) - elapsed
        if wait > 0:
            time.sleep(wait)
        _last[engine] = time.time()


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    return s


def host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def domain_matches(h: str, domains: set[str]) -> bool:
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def is_trusted(h: str) -> bool:
    return domain_matches(h, TRUSTED_DOMAINS)


def is_rejected(h: str) -> bool:
    return domain_matches(h, REJECT_DOMAINS)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def toks(s: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9\u0600-\u06FF+\-/]+", str(s or "").upper())
    out = []
    for t in raw:
        t = t.strip("-_/+")
        if len(t) <= 2 or t in NOISE or re.fullmatch(r"[\d.\-/+]+", t):
            continue
        out.append(t)
    return out


def main_desc(desc: str, parent: bool = False) -> str:
    d = norm(desc)
    up = d.upper()
    if " RELATED TO " in up:
        i = up.find(" RELATED TO ")
        left = d[:i].strip()
        right = d[i + len(" RELATED TO "):].strip()
        return right if parent and right else left
    return d


def query_variants(rec: dict) -> list[str]:
    desc = rec.get("desc", "")
    code = norm(rec.get("code", ""))
    barcode = norm(rec.get("barcode", ""))
    subcat = norm(rec.get("subcat", ""))
    primary = " ".join(toks(main_desc(desc))[:7])
    parent = " ".join(toks(main_desc(desc, True))[:7])
    compact = " ".join(toks(main_desc(desc))[:4])
    qs = []
    if code:
        qs += [f'"{code}"', f'"{code}" {primary}'.strip()]
    if barcode:
        qs.append(f'"{barcode}"')
    if primary:
        qs.append(f"{primary} {STRICT_CONTEXT}")
    if parent and parent != primary:
        qs.append(f"{parent} {STRICT_CONTEXT}")
    if compact:
        qs.append(f"{compact} rehab equipment")
    if subcat and primary:
        qs.append(f"{primary} {subcat} medical")
    for d in ["performancehealth.com", "rehabmart.com", "alimed.com", "medline.com", "fabricationenterprises.com"]:
        if primary:
            qs.append(f"{primary} site:{d}")
    seen, out = set(), []
    for q in qs:
        q = norm(q)
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:12]


def bad_url(u: str) -> bool:
    if not u or not u.startswith(("http://", "https://")):
        return True
    ul = u.lower()
    if any(x in ul for x in BAD_FRAGMENTS):
        return True
    _, ext = os.path.splitext(urlparse(ul).path)
    return ext in BAD_EXT


def candidate_score(c: Candidate, rec: dict) -> tuple[int, str]:
    d = c.domain or host(c.page_url) or host(c.image_url)
    text = " ".join([c.title, c.image_url, c.page_url]).upper()
    desc_toks = toks(main_desc(rec.get("desc", "")))[:10]
    code = norm(rec.get("code", "")).upper()
    barcode = norm(rec.get("barcode", "")).upper()
    if is_rejected(d):
        return -999, "rejected domain"
    score, why = 0, []
    if is_trusted(d):
        score += 30; why.append("trusted domain")
    else:
        score -= 12; why.append("untrusted domain")
    overlap = sum(1 for t in set(desc_toks) if t and t in text)
    score += min(30, overlap * 7)
    if overlap: why.append(f"{overlap} desc tokens")
    if code and code in text:
        score += 28; why.append("code in metadata")
    if barcode and barcode in text:
        score += 24; why.append("barcode in metadata")
    if any(x in text.lower() for x in ("product", "shop", "catalog", "rehab", "therapy", "medical")):
        score += 8; why.append("product context")
    if any(x in text.lower() for x in ("logo", "banner", "blog", "article", "stock-photo")):
        score -= 18; why.append("generic/stock context")
    score += max(0, 8 - c.rank)
    return score, "; ".join(why)


def search_bing(s: requests.Session, q: str) -> list[Candidate]:
    rate_limit("bing")
    try:
        s.get("https://www.bing.com/", timeout=8)
    except Exception:
        pass
    try:
        r = s.get("https://www.bing.com/images/async", params={"q": q, "first": "1", "count": "35", "form": "IRFLTR"}, timeout=18)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for rank, item in enumerate(soup.select("a.iusc"), 1):
        m = item.get("m")
        if not m: continue
        try: data = json.loads(m)
        except Exception: continue
        img = data.get("murl") or data.get("turl") or ""
        page = data.get("purl") or data.get("p") or ""
        title = data.get("t") or item.get("aria-label") or ""
        if img.startswith(("http://", "https://")):
            out.append(Candidate(img, page, title, "bing", q, rank, host(page) or host(img)))
    return out[:MAX_CANDIDATES]


def ddg_vqd(s: requests.Session, q: str) -> Optional[str]:
    rate_limit("duckduckgo")
    try: r = s.get("https://duckduckgo.com/", params={"q": q}, timeout=18)
    except Exception: return None
    m = re.search(r'vqd=["\']([\d-]+)["\']', r.text) or re.search(r'vqd=([\d-]+)', r.text)
    return m.group(1) if m else None


def search_duckduckgo(s: requests.Session, q: str) -> list[Candidate]:
    vqd = ddg_vqd(s, q)
    if not vqd: return []
    rate_limit("duckduckgo")
    try:
        r = s.get("https://duckduckgo.com/i.js", params={"l":"us-en","o":"json","q":q,"vqd":vqd,"f":",,,,,","p":"1"}, headers={"Accept":"application/json","Referer":"https://duckduckgo.com/"}, timeout=18)
        if r.status_code != 200: return []
        data = r.json()
    except Exception:
        return []
    out = []
    for rank, item in enumerate(data.get("results", []), 1):
        img = item.get("image") or item.get("thumbnail") or ""
        page = item.get("url") or ""
        title = item.get("title") or ""
        if img.startswith(("http://", "https://")):
            out.append(Candidate(img, page, title, "duckduckgo", q, rank, host(page) or host(img)))
    return out[:MAX_CANDIDATES]


def search_google(s: requests.Session, q: str) -> list[Candidate]:
    rate_limit("google")
    try:
        r = s.get("https://www.google.com/search", params={"q":q,"tbm":"isch","hl":"en","tbs":"isz:m"}, timeout=18)
        r.raise_for_status()
    except Exception:
        return []
    out = []
    for rank, m in enumerate(re.finditer(r'"ou":"(https?:[^"]+)"', r.text), 1):
        img = m.group(1).replace("\\u003d", "=").replace("\\/", "/")
        if img.startswith(("http://", "https://")):
            out.append(Candidate(img, "", "", "google", q, rank, host(img)))
        if len(out) >= MAX_CANDIDATES: break
    return out

ENGINES = [search_bing, search_duckduckgo, search_google]


def download_image(s: requests.Session, url: str) -> Optional[bytes]:
    try:
        r = s.get(url, headers={"User-Agent": random.choice(USER_AGENTS), "Referer": urlparse(url).scheme + "://" + urlparse(url).netloc + "/", "Accept": "image/*,*/*;q=0.8"}, timeout=TIMEOUT_IMAGE, stream=True)
        if r.status_code != 200: return None
        ctype = r.headers.get("Content-Type", "").lower()
        if ctype and "image/" not in ctype and "octet-stream" not in ctype: return None
        chunks, size = [], 0
        for chunk in r.iter_content(8192):
            chunks.append(chunk); size += len(chunk)
            if size > MAX_BYTES: return None
        return b"".join(chunks)
    except Exception:
        return None


def process_image(raw: bytes) -> tuple[Optional[bytes], int, int, str]:
    try:
        img = Image.open(io.BytesIO(raw)); img = ImageOps.exif_transpose(img); img.load()
    except (UnidentifiedImageError, Exception):
        return None, 0, 0, "not decodable"
    w, h = img.size
    if w < MIN_DIM or h < MIN_DIM: return None, w, h, "too small"
    if w / h > MAX_ASPECT or h / w > MAX_ASPECT: return None, w, h, "bad aspect"
    try:
        colors = img.convert("RGB").resize((32,32)).getcolors(maxcolors=4096) or []
        if len(colors) < 12: return None, w, h, "too few colors"
    except Exception:
        pass
    if max(w, h) > MAX_SIZE:
        ratio = MAX_SIZE / float(max(w, h))
        img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), w, h, "ok"


def best_image(rec: dict, min_score: int, trusted_only: bool) -> tuple[Optional[Candidate], bytes]:
    s = session(); best = None; best_data = b""
    for q in query_variants(rec):
        candidates = []
        for engine in ENGINES:
            try: candidates.extend(engine(s, q))
            except Exception as e: log.debug("search error %s", e)
        scored = []
        for c in candidates:
            if bad_url(c.image_url): continue
            c.domain = c.domain or host(c.page_url) or host(c.image_url)
            c.meta_score, c.reason = candidate_score(c, rec)
            if trusted_only and not is_trusted(c.domain): continue
            if c.meta_score < 20: continue
            scored.append(c)
        scored.sort(key=lambda x: x.meta_score, reverse=True)
        for c in scored[:8]:
            raw = download_image(s, c.image_url)
            if not raw: continue
            data, w, h, reason = process_image(raw)
            if not data:
                c.reason += f"; image reject: {reason} {w}x{h}"; continue
            c.final_score = c.meta_score + (8 if w >= 500 and h >= 500 else 4 if w >= 350 and h >= 350 else 0)
            if c.image_url.lower().split("?")[0].endswith(GOOD_EXT): c.final_score += 3
            if not best or c.final_score > best.final_score:
                best, best_data = c, data
            if c.final_score >= min_score:
                return c, data
    return (best, best_data) if best and best.final_score >= min_score else (None, b"")


def load_products(path: Path, limit: Optional[int], ids: Optional[set[str]]) -> list[dict]:
    if not path.exists(): raise FileNotFoundError(f"Missing products CSV: {path}")
    out = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if ids and str(row.get("num", "")).strip() not in ids: continue
            out.append(row)
    return out[:limit] if limit else out


def row(rec, status, c=None, path="", size=0):
    c = c or Candidate("")
    return {"num":rec.get("num",""),"code":rec.get("code",""),"barcode":rec.get("barcode",""),"desc":rec.get("desc","")[:240],"status":status,"score":c.final_score or c.meta_score,"domain":c.domain,"engine":c.engine,"query":c.query,"title":c.title[:180],"source_url":c.image_url,"page_url":c.page_url,"reason":c.reason,"img_path":str(path),"img_size_kb":round(size/1024,1) if size else 0}


def write_image(rec, c, data, replace, dry_run):
    out = OUT_DIR / f"{rec['num']}.jpg"
    existed = out.exists() and out.stat().st_size > 1024
    if dry_run: return row(rec, "dry_ok", c, out if existed else "", len(data))
    if existed and not replace: return row(rec, "ok_existing_skip", c, out, out.stat().st_size)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if existed and replace:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup = BACKUP_DIR / f"{rec['num']}.jpg"
        if not backup.exists(): shutil.copy2(out, backup)
    out.write_bytes(data)
    return row(rec, "ok_replaced" if existed else "ok_new", c, out, len(data))


def audit_existing():
    rows = []
    for p in [WORK_DIR / "scrape_log.csv", WORK_DIR / "scrape_retry_log.csv", LOG_CSV]:
        if not p.exists(): continue
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                url = r.get("source_url", ""); d = host(url)
                if not url: status, reason = "suspect", "missing source_url"
                elif is_rejected(d): status, reason = "bad", "rejected domain"
                elif not is_trusted(d): status, reason = "suspect", "untrusted domain"
                else: continue
                rows.append({"num":r.get("num",""),"code":r.get("code",""),"barcode":r.get("barcode",""),"desc":r.get("desc",""),"status":status,"reason":reason,"domain":d,"source_url":url,"img_path":r.get("img_path","")})
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["num","code","barcode","desc","status","reason","domain","source_url","img_path"]); w.writeheader(); w.writerows(rows)
    log.info("Audit written: %s (%d suspect rows)", AUDIT_CSV, len(rows))


def process_one(rec, args):
    out = OUT_DIR / f"{rec['num']}.jpg"
    if out.exists() and out.stat().st_size > 1024 and not args.replace:
        return row(rec, "ok_existing", None, out, out.stat().st_size)
    c, data = best_image(rec, args.min_score, args.trusted_only)
    if not c: return row(rec, "no_confident_image")
    return write_image(rec, c, data, args.replace, args.dry_run)


def main():
    setup_logging()
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default=str(PRODUCTS_CSV))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", default="")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-untrusted", dest="trusted_only", action="store_false")
    ap.add_argument("--audit-existing", action="store_true")
    ap.set_defaults(trusted_only=True)
    args = ap.parse_args()
    if args.audit_existing:
        audit_existing(); return
    ids = {x.strip() for x in args.ids.split(",") if x.strip()} or None
    products = load_products(Path(args.products), args.limit, ids)
    OUT_DIR.mkdir(parents=True, exist_ok=True); WORK_DIR.mkdir(parents=True, exist_ok=True)
    fields = ["num","code","barcode","desc","status","score","domain","engine","query","title","source_url","page_url","reason","img_path","img_size_kb"]
    mode = "w" if args.dry_run else "a"
    write_header = not LOG_CSV.exists() or args.dry_run
    ok = fail = done = 0; start = time.time(); lock = Lock()
    log.info("Loaded %d products | replace=%s dry_run=%s trusted_only=%s min_score=%d", len(products), args.replace, args.dry_run, args.trusted_only, args.min_score)
    with open(LOG_CSV, mode, encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header: w.writeheader()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_one, rec, args): rec for rec in products}
            for fut in as_completed(futs):
                rec = futs[fut]
                try: r = fut.result()
                except Exception as e:
                    log.exception("error for num=%s: %s", rec.get("num"), e); r = row(rec, "error")
                with lock: w.writerow(r); f.flush()
                done += 1
                if r["status"].startswith(("ok", "dry_ok")): ok += 1
                else: fail += 1
                if done % 10 == 0 or done == len(products):
                    log.info("Progress %d/%d | ok=%d fail=%d | %.1fs", done, len(products), ok, fail, time.time()-start)
    log.info("DONE | total=%d ok=%d fail=%d log=%s", len(products), ok, fail, LOG_CSV)

if __name__ == "__main__":
    main()
