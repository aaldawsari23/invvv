#!/usr/bin/env python3
"""
Product image scraper — multi-engine, no-API, free.
====================================================

Search strategy (in order, until a valid image is found):
  1. Bing Image Search       (HTML scraping — extracts full-res mediaurl from m= JSON)
  2. DuckDuckGo Images       (HTML scraping via the /i.js endpoint, vqd token fetched)
  3. Yandex Images           (HTML scraping fallback)
  4. Brave Search snippets   (last-resort image result)

For each product, the script:
  - builds a clean search query (description + medical context keywords),
  - tries each engine in order,
  - downloads candidate images,
  - validates that the file is a real image (PIL decode),
  - keeps the first image that meets size / aspect-ratio / format criteria,
  - resizes it to MAX_SIZE (longest side), compresses to JPEG q=85,
  - saves it as <product_num>.jpg inside OUT_DIR,
  - records the result row in a CSV log.

Concurrency: ThreadPoolExecutor with N workers, per-engine rate-limit.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import random
import re
import sys
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, UnidentifiedImageError

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

PRODUCTS_CSV = "/home/z/my-project/download/_work/products.csv"
OUT_DIR      = Path("/home/z/my-project/download/product_images")
LOG_CSV      = Path("/home/z/my-project/download/_work/scrape_log.csv")
LOG_FILE     = Path("/home/z/my-project/download/_work/scrape.log")

MAX_SIZE        = 600     # longest side after resize (px)
JPEG_QUALITY    = 85      # output JPEG quality
MIN_DIM         = 200     # min acceptable width/height of source image
MAX_ASPECT      = 3.0     # max width/height or height/width ratio
TIMEOUT_SEARCH  = 15      # seconds for search HTTP
TIMEOUT_IMAGE   = 20      # seconds for image download
MAX_CANDIDATES  = 8       # max candidates to try per engine per product
MAX_WORKERS     = 6       # parallel workers
PER_ENGINE_DELAY = (0.4, 0.9)   # randomized delay between calls to the same engine

# Rotate user-agents to look like real browsers
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

# Will be populated per-engine last-call time for rate-limiting
_engine_locks = {
    "bing":       Lock(),
    "duckduckgo": Lock(),
    "yandex":     Lock(),
    "brave":      Lock(),
}
_engine_last_call = {k: 0.0 for k in _engine_locks}


def _rate_limit(engine: str) -> None:
    """Sleep a small random amount so we don't hammer one engine."""
    with _engine_locks[engine]:
        elapsed = time.time() - _engine_last_call[engine]
        wait = random.uniform(*PER_ENGINE_DELAY) - elapsed
        if wait > 0:
            time.sleep(wait)
        _engine_last_call[engine] = time.time()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("scraper")
# Suppress noisy library logs
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


# --------------------------------------------------------------------------- #
# Query building
# --------------------------------------------------------------------------- #

# Words we strip from descriptions — generic noise that hurts image search
_NOISE_WORDS = {
    "RELATED", "TO", "EACH", "PAIR", "PACK", "OF", "ASSORTED",
    "DISPENSER", "BOX", "EACH", "INDIVIDUALLY", "WRAPPED",
}

# Words that strongly indicate a medical item — appended to query if missing
_MEDICAL_HINTS = ["medical", "hospital", "healthcare"]


def build_query(rec: dict) -> str:
    """Build a clean search query for a product record."""
    desc = rec.get("desc", "").strip()
    code = rec.get("code", "").strip()
    cat  = rec.get("cat", "").strip()
    sub  = rec.get("subcat", "").strip()

    # If description contains "RELATED TO X", split into the actual product (left)
    # and the parent product (right). Use only the LEFT side for the search,
    # because that's what the actual image should show.
    main_desc = desc
    if " RELATED TO " in desc.upper():
        # Take everything before "RELATED TO"
        idx = desc.upper().find(" RELATED TO ")
        main_desc = desc[:idx].strip()

    # Take first 6-8 meaningful words of main_desc
    words = re.findall(r"[A-Za-z0-9+\-/&]+", main_desc.upper())
    words = [w for w in words if w not in _NOISE_WORDS and len(w) > 1]
    # Drop pure numbers / size tokens like "13-15" "0.5"
    words = [w for w in words if not re.fullmatch(r"[\d.\-/+]+", w)]
    words = words[:6]

    parts = []
    if code:
        parts.append(code)                # e.g. MGE30003
    parts.extend(words)
    if sub and sub.upper() not in ("GENERAL",):
        parts.extend(sub.split()[:2])

    # add medical context to focus results on medical equipment
    q = " ".join(parts).strip()
    if not any(h in q.lower() for h in _MEDICAL_HINTS):
        q = (q + " medical equipment").strip()
    return q


# --------------------------------------------------------------------------- #
# Search engines — each returns a list of image URLs (best first)
# --------------------------------------------------------------------------- #

def _warmup_bing(session: requests.Session) -> None:
    """Visit Bing homepage once to establish cookies."""
    if getattr(session, "_bing_warmed", False):
        return
    try:
        session.get("https://www.bing.com/",
                    headers={"User-Agent": random.choice(USER_AGENTS)},
                    timeout=10)
        session._bing_warmed = True
    except Exception:
        pass


def search_bing(session: requests.Session, query: str) -> list[str]:
    """Bing Image Search via the async endpoint (returns full-res murl)."""
    _rate_limit("bing")
    _warmup_bing(session)
    # The /images/async endpoint returns just the result tiles — much cleaner
    url = "https://www.bing.com/images/async"
    params = {
        "q": query,
        "first": "1",
        "count": "35",
        "qft": "",
        "form": "IRFLTR",
    }
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.bing.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = session.get(url, params=params, headers=headers,
                        timeout=TIMEOUT_SEARCH)
        r.raise_for_status()
    except Exception as e:
        log.debug("bing search error for %r: %s", query, e)
        return []

    urls: list[str] = []
    soup = BeautifulSoup(r.text, "lxml")
    # Each result tile is an <a class="iusc"> with m="<JSON containing murl>"
    for item in soup.select("a.iusc"):
        m = item.get("m")
        if not m:
            continue
        try:
            data = json.loads(m)
        except Exception:
            continue
        mu = data.get("murl") or data.get("turl")
        if mu and mu.startswith(("http://", "https://")):
            urls.append(mu)
    # Fallback: div.iuscp with m= attribute
    if not urls:
        for item in soup.select("div.iuscp"):
            m = item.get("m")
            if not m:
                continue
            try:
                data = json.loads(m)
            except Exception:
                continue
            mu = data.get("murl") or data.get("turl")
            if mu and mu.startswith(("http://", "https://")):
                urls.append(mu)
    return urls[:MAX_CANDIDATES]


def _ddg_vqd(session: requests.Session, query: str) -> Optional[str]:
    """Fetch DuckDuckGo's vqd token needed for the image endpoint."""
    _rate_limit("duckduckgo")
    u = "https://duckduckgo.com/"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = session.get(u, params={"q": query}, headers=headers, timeout=TIMEOUT_SEARCH)
    except Exception:
        return None
    # vqd is embedded in the HTML/JS as "vqd='1234-5678...'" or vqd="..."
    m = re.search(r'vqd=["\']([\d-]+)["\']', r.text)
    if m:
        return m.group(1)
    m = re.search(r'vqd=([\d-]+)', r.text)
    return m.group(1) if m else None


def search_duckduckgo(session: requests.Session, query: str) -> list[str]:
    """DuckDuckGo Images via the /i.js endpoint."""
    vqd = _ddg_vqd(session, query)
    if not vqd:
        return []
    _rate_limit("duckduckgo")
    u = "https://duckduckgo.com/i.js"
    params = {
        "l": "us-en",
        "o": "json",
        "q": query,
        "vqd": vqd,
        "f": ",,,,,",
        "p": "1",
        "v7exp": "a",
    }
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://duckduckgo.com/",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        r = session.get(u, params=params, headers=headers, timeout=TIMEOUT_SEARCH)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as e:
        log.debug("ddg json error for %r: %s", query, e)
        return []
    urls = []
    for item in data.get("results", []):
        image = item.get("image") or item.get("thumbnail")
        if image and image.startswith(("http://", "https://")):
            urls.append(image)
    return urls[:MAX_CANDIDATES]


def search_yandex(session: requests.Session, query: str) -> list[str]:
    """Yandex Images via HTML scraping."""
    _rate_limit("yandex")
    u = "https://yandex.com/images/search"
    params = {"text": query, "rpt": "image"}
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = session.get(u, params=params, headers=headers, timeout=TIMEOUT_SEARCH)
        r.raise_for_status()
    except Exception as e:
        log.debug("yandex search error for %r: %s", query, e)
        return []
    urls = []
    soup = BeautifulSoup(r.text, "lxml")
    # Yandex embeds the original image URL inside data-bem JSON on .serp-item
    for item in soup.select("div.serp-item"):
        b = item.get("data-bem")
        if not b:
            continue
        try:
            d = json.loads(b)
            img_url = d.get("serp-item", {}).get("img_href")
            if img_url and img_url.startswith(("http://", "https://")):
                urls.append(img_url)
        except Exception:
            continue
    # Fallback: simpledata-img attributes
    if not urls:
        for tag in soup.select("[data-img]"):
            v = tag.get("data-img")
            if v:
                try:
                    d = json.loads(v)
                    if isinstance(d, dict):
                        u2 = d.get("href") or d.get("src")
                        if u2 and u2.startswith(("http://", "https://")):
                            urls.append(u2)
                except Exception:
                    continue
    return urls[:MAX_CANDIDATES]


def search_brave(session: requests.Session, query: str) -> list[str]:
    """Brave Search images via HTML scraping (last resort)."""
    _rate_limit("brave")
    u = "https://search.brave.com/images"
    params = {"q": query}
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        r = session.get(u, params=params, headers=headers, timeout=TIMEOUT_SEARCH)
        r.raise_for_status()
    except Exception as e:
        log.debug("brave search error for %r: %s", query, e)
        return []
    urls = []
    soup = BeautifulSoup(r.text, "lxml")
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        if src.startswith(("http://", "https://")) and "brave" not in src and "favicon" not in src:
            urls.append(src)
    return urls[:MAX_CANDIDATES]


def search_google(session: requests.Session, query: str) -> list[str]:
    """Google Images via HTML scraping (extracts full-res URLs from imgrefurl)."""
    _rate_limit("bing")  # share bing rate limit slot
    url = "https://www.google.com/search"
    params = {
        "q": query,
        "tbm": "isch",
        "hl": "en",
        "tbs": "isz:m",  # medium size
    }
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    try:
        r = session.get(url, params=params, headers=headers, timeout=TIMEOUT_SEARCH)
        r.raise_for_status()
    except Exception as e:
        log.debug("google search error for %r: %s", query, e)
        return []
    urls = []
    text = r.text
    # Google embeds full-res image URLs in JSON inside script tags.
    # The pattern "ou":"https://..." is the original URL in the metadata.
    for m in re.finditer(r'"ou":"(https?:[^"]+)"', text):
        u = m.group(1).replace("\\u003d", "=").replace("\\/", "/")
        if u.startswith(("http://", "https://")):
            urls.append(u)
    # Fallback: parse img tags with data-src
    if not urls:
        soup = BeautifulSoup(text, "lxml")
        for img in soup.select("img"):
            src = img.get("data-src") or img.get("src")
            if src and src.startswith(("http://", "https://")) and "gstatic" not in src and "google" not in src:
                urls.append(src)
    return urls[:MAX_CANDIDATES]


ENGINES = [
    ("bing",       search_bing),
    ("duckduckgo", search_duckduckgo),
    ("google",     search_google),
    ("yandex",     search_yandex),
    ("brave",      search_brave),
]


# --------------------------------------------------------------------------- #
# Image download + validation + optimization
# --------------------------------------------------------------------------- #

# File extensions / URL fragments to skip — likely icons, sprites, placeholders
_BAD_FRAGMENTS = (
    "favicon", "logo", "sprite", "icon", "placeholder",
    "pixel.gif", "1x1", "blank.gif", "no-image",
    "data:image",
)
_BAD_EXTENSIONS = (".svg", ".gif", ".webp", ".avif")  # we still accept .jpg/.jpeg/.png/.bmp


def _is_bad_url(u: str) -> bool:
    ul = u.lower()
    if any(b in ul for b in _BAD_FRAGMENTS):
        return True
    # extract extension from URL path
    path = urllib.parse.urlparse(ul).path
    _, ext = os.path.splitext(path)
    if ext in _BAD_EXTENSIONS:
        return True
    return False


def _download_image(session: requests.Session, url: str) -> Optional[bytes]:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": urllib.parse.urlparse(url).scheme + "://" + urllib.parse.urlparse(url).netloc + "/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    try:
        r = session.get(url, headers=headers, timeout=TIMEOUT_IMAGE, stream=True)
        if r.status_code != 200:
            return None
        ctype = r.headers.get("Content-Type", "").lower()
        if ctype and "image/" not in ctype and "octet-stream" not in ctype:
            return None
        # cap at 8 MB to avoid huge downloads
        chunks = []
        size = 0
        for chunk in r.iter_content(8192):
            chunks.append(chunk)
            size += len(chunk)
            if size > 8_000_000:
                return None
        return b"".join(chunks)
    except Exception:
        return None


def _validate_and_process(raw: bytes) -> Optional[bytes]:
    """Validate the raw bytes as an image and return optimized JPEG bytes."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)  # fix orientation from EXIF
        img.load()
    except (UnidentifiedImageError, Exception):
        return None

    w, h = img.size
    if w < MIN_DIM or h < MIN_DIM:
        return None
    # reject extreme aspect ratios (banners, panorama strips)
    if w / h > MAX_ASPECT or h / w > MAX_ASPECT:
        return None

    # resize so the longest side <= MAX_SIZE
    if max(w, h) > MAX_SIZE:
        ratio = MAX_SIZE / float(max(w, h))
        new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
        img = img.resize(new_size, Image.LANCZOS)

    # convert to RGB (drop alpha) and save as JPEG
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return buf.getvalue()


def fetch_image_for_product(rec: dict) -> dict:
    """Try every engine in order; return first valid image as processed JPEG bytes."""
    query = build_query(rec)
    session = _session()
    last_engine = None
    for engine_name, engine_fn in ENGINES:
        try:
            urls = engine_fn(session, query)
        except Exception as e:
            log.debug("engine %s raised for %s: %s", engine_name, rec["num"], e)
            urls = []
        last_engine = engine_name
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
                    "query": query,
                    "bytes": processed,
                }
    return {
        "status": "no_image",
        "engine": last_engine or "none",
        "source_url": "",
        "query": query,
        "bytes": b"",
    }


# --------------------------------------------------------------------------- #
# Main driver
# --------------------------------------------------------------------------- #

@dataclass
class Stats:
    total: int = 0
    ok: int = 0
    fail: int = 0
    per_engine: dict = field(default_factory=lambda: {"bing": 0, "duckduckgo": 0, "google": 0, "yandex": 0, "brave": 0})
    start_time: float = 0.0


def load_products(path: str, limit: Optional[int] = None,
                  source_filter: Optional[str] = None) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if source_filter and row["source_file"] != source_filter:
                continue
            out.append(row)
    if limit:
        out = out[:limit]
    return out


def process_one(rec: dict, stats: Stats, log_lock: Lock) -> dict:
    """Process a single product. Returns the result row."""
    num = rec["num"]
    out_path = OUT_DIR / f"{num}.jpg"
    # Skip if already done (resume support)
    if out_path.exists() and out_path.stat().st_size > 1024:
        result = {
            "num": num,
            "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", "")[:200],
            "query": "",
            "status": "ok_cached",
            "engine": "cache",
            "source_url": "",
            "img_path": str(out_path),
            "img_size_kb": round(out_path.stat().st_size / 1024, 1),
        }
        return result

    res = fetch_image_for_product(rec)
    if res["status"] == "ok":
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(res["bytes"])
        size_kb = round(len(res["bytes"]) / 1024, 1)
        result = {
            "num": num,
            "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", "")[:200],
            "query": res["query"],
            "status": "ok",
            "engine": res["engine"],
            "source_url": res["source_url"],
            "img_path": str(out_path),
            "img_size_kb": size_kb,
        }
    else:
        result = {
            "num": num,
            "code": rec.get("code", ""),
            "barcode": rec.get("barcode", ""),
            "desc": rec.get("desc", "")[:200],
            "query": res["query"],
            "status": "no_image",
            "engine": res["engine"],
            "source_url": "",
            "img_path": "",
            "img_size_kb": 0,
        }
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="Process only the first N products (for testing).")
    ap.add_argument("--source", choices=["file1", "file2"], default=None,
                    help="Process only products from this source file.")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS,
                    help="Number of parallel workers.")
    ap.add_argument("--ids", type=str, default=None,
                    help="Comma-separated list of specific product numbers to (re)process.")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_CSV.parent.mkdir(parents=True, exist_ok=True)

    products = load_products(PRODUCTS_CSV, limit=args.limit, source_filter=args.source)
    if args.ids:
        wanted = set(s.strip() for s in args.ids.split(","))
        products = [p for p in products if p["num"] in wanted]

    log.info("Loaded %d products to process", len(products))

    stats = Stats(total=len(products), start_time=time.time())
    log_lock = Lock()

    # Open CSV log in append mode (write header if new)
    write_header = not LOG_CSV.exists()
    log_csv_f = open(LOG_CSV, "a", encoding="utf-8", newline="")
    log_csv_w = csv.DictWriter(log_csv_f, fieldnames=[
        "num", "code", "barcode", "desc", "query",
        "status", "engine", "source_url", "img_path", "img_size_kb",
    ])
    if write_header:
        log_csv_w.writeheader()

    completed = 0
    last_progress_ts = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_one, p, stats, log_lock): p for p in products}
        for fut in as_completed(futures):
            rec = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                log.error("Unhandled error for num=%s: %s", rec.get("num"), e)
                traceback.print_exc()
                result = {
                    "num": rec.get("num", ""),
                    "code": rec.get("code", ""),
                    "barcode": rec.get("barcode", ""),
                    "desc": rec.get("desc", "")[:200],
                    "query": "",
                    "status": "error",
                    "engine": "none",
                    "source_url": "",
                    "img_path": "",
                    "img_size_kb": 0,
                }
            # Write to CSV
            with log_lock:
                log_csv_w.writerow(result)
                log_csv_f.flush()
            # Update stats
            completed += 1
            if result["status"].startswith("ok"):
                stats.ok += 1
                if result["engine"] in stats.per_engine:
                    stats.per_engine[result["engine"]] += 1
            else:
                stats.fail += 1
            # Periodic progress
            now = time.time()
            if now - last_progress_ts >= 5.0 or completed == stats.total:
                elapsed = now - stats.start_time
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (stats.total - completed) / rate if rate > 0 else 0
                log.info(
                    "Progress: %d/%d (%.1f%%) | ok=%d fail=%d | "
                    "engines: bing=%d ddg=%d google=%d yandex=%d brave=%d | "
                    "rate=%.1f/s eta=%.0fs",
                    completed, stats.total, 100.0 * completed / stats.total,
                    stats.ok, stats.fail,
                    stats.per_engine["bing"], stats.per_engine["duckduckgo"],
                    stats.per_engine["google"], stats.per_engine["yandex"],
                    stats.per_engine["brave"],
                    rate, eta,
                )
                last_progress_ts = now

    log_csv_f.close()
    log.info("=" * 60)
    log.info("DONE. Total=%d  OK=%d  Fail=%d  Elapsed=%.1fs",
             stats.total, stats.ok, stats.fail, time.time() - stats.start_time)
    log.info("Images dir: %s", OUT_DIR)
    log.info("Log CSV:    %s", LOG_CSV)


if __name__ == "__main__":
    main()
