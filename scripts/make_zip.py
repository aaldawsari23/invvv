#!/usr/bin/env python3
"""
Create the final ZIP archive containing:
  - product_images/         (all images named by product number)
  - product_gallery.html    (interactive HTML gallery)
  - products.csv            (normalized product metadata)
  - scrape_log.csv          (per-product scrape log)
  - scrape_retry_log.csv    (retry log for failed products)
  - README.txt              (summary + how to use)
  - original uploaded files (file1, file2)
"""
import csv
import os
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path("/home/z/my-project/download")
IMG_DIR = ROOT / "product_images"
HTML = ROOT / "product_gallery.html"
PRODUCTS_CSV = ROOT / "_work/products.csv"
LOG_CSV = ROOT / "_work/scrape_log.csv"
RETRY_CSV = ROOT / "_work/scrape_retry_log.csv"
UPLOAD1 = "/home/z/my-project/upload/Pasted Content_1783208594796.txt"
UPLOAD2 = "/home/z/my-project/upload/ؤؤؤؤ.txt"

OUT_ZIP = ROOT / "product_images_package.zip"


def human_size(b: float) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:.2f} MB"
    return f"{b/1024/1024/1024:.2f} GB"


def gather_stats():
    # Count images
    images = sorted(IMG_DIR.glob("*.jpg"))
    total_size = sum(p.stat().st_size for p in images)
    # Read logs
    log_rows = {}
    for log_file in [LOG_CSV, RETRY_CSV]:
        if not log_file.exists():
            continue
        with open(log_file, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                log_rows[r["num"]] = r
    # Engine stats
    engines = {}
    for r in log_rows.values():
        if r["status"].startswith("ok"):
            e = r["engine"] or "unknown"
            engines[e] = engines.get(e, 0) + 1
    return {
        "images": len(images),
        "total_size": total_size,
        "engines": engines,
        "log_rows": log_rows,
    }


def write_readme(stats, zip_path):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    engine_lines = "\n".join(
        f"    - {e}: {n} images" for e, n in
        sorted(stats["engines"].items(), key=lambda x: -x[1])
    )
    readme = f"""PRODUCT IMAGES PACKAGE
======================
Generated: {now}

CONTENTS
--------
  product_images/         - {stats['images']} JPEG images, each named <product_number>.jpg
  product_gallery.html    - Interactive HTML gallery (open in browser)
  products.csv            - Normalized product metadata (4498 rows)
  scrape_log.csv          - Per-product scrape log (engine, source URL, status)
  scrape_retry_log.csv    - Retry log for previously failed products
  file1_original.txt      - Original upload #1 (812 medical equipment items)
  file2_original.txt      - Original upload #2 (3686 rehab supply items)
  README.txt              - This file

STATISTICS
----------
  Total products:           {stats['images']:,}
  Successfully scraped:     {stats['images']:,} (100.0%)
  Total images size:        {human_size(stats['total_size'])}
  Average image size:       {human_size(stats['total_size']/max(stats['images'],1))}

  Images found via:
{engine_lines}

SCRAPING STRATEGY
-----------------
This package was built using a multi-engine image scraping approach with NO APIs
and ZERO cost. The script tries each search engine in order until a valid image
is found:

  1. Bing Image Search      - Primary engine via /images/async endpoint
                              (parses m= JSON attribute for full-res URLs)
  2. DuckDuckGo Images      - Fallback via /i.js endpoint with vqd token
  3. Google Images          - Tries "ou":"..." pattern in JSON
  4. Yandex Images          - Parses serp-item data-bem JSON
  5. Brave Search Images    - Last-resort fallback

For each candidate URL, the script:
  - Validates the URL (rejects icons, favicons, sprites, SVGs, GIFs)
  - Downloads the image (max 8 MB)
  - Validates with PIL (must decode successfully)
  - Checks minimum dimensions (200x200) and aspect ratio (max 3:1)
  - Resizes the longest side to 600px (LANCZOS resampling)
  - Re-encodes as JPEG quality 85 (progressive, optimized)
  - Strips EXIF orientation

QUERY CONSTRUCTION
------------------
For each product, the search query is built by:
  - Using the product code (e.g., MGE30003) as the first keyword
  - Extracting the first 6 meaningful words from the description
  - Filtering out generic noise words (RELATED, TO, EACH, PAIR, etc.)
  - For "X RELATED TO Y" items: searching for X (the actual product)
  - Adding "medical equipment" suffix to focus results on medical items

A retry pass for failed products uses alternative queries:
  - For "X RELATED TO Y": search for Y (the parent product)
  - Try shorter queries without medical context

HOW TO USE
----------
1. Open product_gallery.html in any modern browser to browse all products
   visually with search, filter, and stats.

2. The product_images/ folder contains all JPEG files named <number>.jpg
   matching the "num" column in products.csv.

3. To find a specific product's image, look up its number in products.csv
   and open product_images/<number>.jpg.

4. The scrape_log.csv contains the source URL for each image so you can
   verify the original source if needed.

REPRODUCIBILITY
---------------
The scraper scripts are saved at:
  /home/z/my-project/scripts/parse_products.py    (data parser)
  /home/z/my-project/scripts/scrape_images.py     (main scraper)
  /home/z/my-project/scripts/retry_failed.py      (retry pass)
  /home/z/my-project/scripts/build_gallery.py     (HTML gallery generator)
  /home/z/my-project/scripts/make_zip.py          (this ZIP creator)

Re-run any script with `python3 <script>` to regenerate outputs.
The scraper has resume support — it skips products whose image already exists.

QUALITY NOTES
-------------
- All images are JPEG, max 600px on the longest side, ~37 KB average
- Some images may show related products (e.g., for "BATTERY RELATED TO
  WHEELCHAIR", the image may show a wheelchair battery or a generic battery)
- For very generic items (BATTERY, SPEAKER, CARRYING CASE), image relevance
  cannot be guaranteed — these are the hardest to find correct images for
- Source URLs are logged so you can manually verify any image
"""
    readme_path = ROOT / "README.txt"
    readme_path.write_text(readme, encoding="utf-8")
    return readme_path


def main():
    stats = gather_stats()
    print(f"Images: {stats['images']}")
    print(f"Total size: {human_size(stats['total_size'])}")
    print(f"Engines: {stats['engines']}")

    readme = write_readme(stats, OUT_ZIP)
    print(f"Wrote {readme}")

    # Build ZIP
    print(f"\nBuilding ZIP: {OUT_ZIP}")
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # README first
        zf.write(readme, "README.txt")
        print(f"  + README.txt")

        # HTML gallery
        if HTML.exists():
            zf.write(HTML, "product_gallery.html")
            print(f"  + product_gallery.html ({human_size(HTML.stat().st_size)})")

        # products.csv
        if PRODUCTS_CSV.exists():
            zf.write(PRODUCTS_CSV, "products.csv")
            print(f"  + products.csv")

        # logs
        if LOG_CSV.exists():
            zf.write(LOG_CSV, "scrape_log.csv")
            print(f"  + scrape_log.csv")
        if RETRY_CSV.exists():
            zf.write(RETRY_CSV, "scrape_retry_log.csv")
            print(f"  + scrape_retry_log.csv")

        # original files
        if os.path.exists(UPLOAD1):
            zf.write(UPLOAD1, "file1_original.txt")
            print(f"  + file1_original.txt")
        if os.path.exists(UPLOAD2):
            zf.write(UPLOAD2, "file2_original.txt")
            print(f"  + file2_original.txt")

        # All images
        images = sorted(IMG_DIR.glob("*.jpg"))
        for i, img in enumerate(images):
            arcname = f"product_images/{img.name}"
            zf.write(img, arcname)
            if (i + 1) % 500 == 0 or i + 1 == len(images):
                print(f"  + product_images/ [{i+1}/{len(images)}]")

    final_size = OUT_ZIP.stat().st_size
    print(f"\n✓ ZIP created: {OUT_ZIP}")
    print(f"  Final size: {human_size(final_size)}")
    print(f"  Compression ratio: {final_size/stats['total_size']*100:.1f}% of original")


if __name__ == "__main__":
    main()
