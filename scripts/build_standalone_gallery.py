#!/usr/bin/env python3
"""
Generate a SELF-CONTAINED HTML gallery with all images embedded as base64.
This single file can be downloaded and opened in any browser without needing
the product_images/ folder.

To keep file size reasonable:
  - Thumbnails are 160x160 max
  - JPEG quality 70
  - Click thumbnail to view full-size image (still embedded)
"""
import base64
import csv
import html
import io
from pathlib import Path
from PIL import Image

ROOT = Path("/home/z/my-project/download")
PRODUCTS_CSV = ROOT / "_work/products.csv"
LOG_CSV       = ROOT / "_work/scrape_log.csv"
RETRY_CSV     = ROOT / "_work/scrape_retry_log.csv"
IMG_DIR       = ROOT / "product_images"
OUT_HTML      = ROOT / "product_gallery_standalone.html"

THUMB_SIZE = 160       # max dimension for thumbnail
THUMB_Q    = 70        # JPEG quality for thumbnail
FULL_SIZE  = 600       # max dimension for full image (already done)
FULL_Q     = 80


def load_products():
    out = {}
    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["num"]] = r
    return out


def load_log():
    out = {}
    for log_file in [LOG_CSV, RETRY_CSV]:
        if not log_file.exists():
            continue
        with open(log_file, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["num"]] = r
    return out


def make_thumbnail_b64(img_path: Path, max_size: int, quality: int) -> str:
    """Read image, resize, return as base64 JPEG data URL."""
    try:
        img = Image.open(img_path)
        img = ImageOps_exif_fix(img)
        # convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        # resize
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / float(max(w, h))
            img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        return ""


def ImageOps_exif_fix(img):
    """Apply EXIF orientation if present."""
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def human_size(b: float) -> str:
    if b < 1024: return f"{b} B"
    if b < 1024*1024: return f"{b/1024:.1f} KB"
    return f"{b/1024/1024:.2f} MB"


def main():
    products = load_products()
    log_rows = load_log()

    print(f"Processing {len(products)} products...")

    cards_html = []
    total = 0
    with_img = 0
    total_b64_bytes = 0

    for i, (num, prod) in enumerate(sorted(products.items())):
        img_path = IMG_DIR / f"{num}.jpg"
        log = log_rows.get(num, {})
        has_img = img_path.exists()
        total += 1

        title = prod.get("desc", "") or prod.get("code", "") or prod.get("barcode", "") or f"#{num}"
        title_esc = html.escape(title[:300])
        code_esc = html.escape(prod.get("code", ""))
        bar_esc = html.escape(prod.get("barcode", ""))
        cat_esc = html.escape(f"{prod.get('cat','')} / {prod.get('subcat','')}".strip(" /"))
        engine = log.get("engine", "")

        if has_img:
            with_img += 1
            # Build thumbnail
            thumb_b64 = make_thumbnail_b64(img_path, THUMB_SIZE, THUMB_Q)
            total_b64_bytes += len(thumb_b64)
            size_kb = round(img_path.stat().st_size / 1024, 1)
            img_html = (
                f'<img src="{thumb_b64}" loading="lazy" alt="{title_esc}" '
                f'class="thumb" />'
            )
            meta = (
                f'<div class="meta">'
                f'<span class="badge badge-size">{size_kb} KB</span>'
                f'<span class="badge badge-engine">{html.escape(engine)}</span>'
                f'</div>'
            )
        else:
            img_html = '<div class="no-img">No image</div>'
            meta = '<div class="meta"><span class="badge badge-fail">missing</span></div>'

        src_url = log.get("source_url", "")
        src_link = (
            f'<a href="{html.escape(src_url)}" target="_blank" rel="noopener" class="src-link">source ↗</a>'
            if src_url else ""
        )

        cards_html.append(f"""
        <article class="card" data-src="{prod.get('source_file','')}" data-has-img="{'1' if has_img else '0'}">
          <div class="card-img">{img_html}</div>
          <div class="card-body">
            <div class="num">#{html.escape(num)}</div>
            {f'<div class="code">{code_esc}</div>' if code_esc else ''}
            <div class="title" title="{title_esc}">{title_esc}</div>
            {f'<div class="cat">{cat_esc}</div>' if cat_esc else ''}
            {f'<div class="barcode">GTIN: {bar_esc}</div>' if bar_esc else ''}
            {meta}
            {src_link}
          </div>
        </article>""")

        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(products)} processed, base64 size so far: {human_size(total_b64_bytes)}")

    pct = 100 * with_img / total if total else 0
    print(f"\nTotal base64 size: {human_size(total_b64_bytes)}")

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Gallery — {total} products — Self-contained</title>
<style>
:root {{
  --bg: #f6f7f9; --card: #fff; --text: #1a1a1a; --muted: #6b7280;
  --border: #e5e7eb; --accent: #2563eb; --ok: #16a34a; --fail: #dc2626;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  font-size: 14px; -webkit-font-smoothing: antialiased; }}
header {{ background: linear-gradient(135deg, #1e3a8a, #2563eb); color: white;
  padding: 24px 24px 20px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
header h1 {{ margin: 0 0 6px; font-size: 22px; font-weight: 700; }}
header .sub {{ opacity: .9; font-size: 13px; }}
header .summary {{ margin-top: 14px; display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
.summary .metric {{ background: rgba(255,255,255,.15); border-radius: 8px; padding: 8px 12px; }}
.summary .metric .label {{ font-size: 11px; opacity: .85; text-transform: uppercase; letter-spacing: .04em; }}
.summary .metric .value {{ font-size: 20px; font-weight: 700; margin-top: 2px; }}
.toolbar {{ background: white; border-bottom: 1px solid var(--border);
  padding: 10px 24px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  position: sticky; top: 130px; z-index: 99; }}
.toolbar input, .toolbar select {{ padding: 7px 11px; border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; background: white; }}
.toolbar input {{ flex: 1; min-width: 200px; }}
.toolbar .count {{ color: var(--muted); font-size: 12px; }}
main {{ padding: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }}
.card {{ background: var(--card); border-radius: 8px; border: 1px solid var(--border);
  box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow: hidden;
  transition: box-shadow .2s, transform .2s; display: flex; flex-direction: column; }}
.card:hover {{ box-shadow: 0 8px 20px rgba(0,0,0,.08); transform: translateY(-2px); }}
.card-img {{ background: #f3f4f6; aspect-ratio: 1; display: flex;
  align-items: center; justify-content: center; overflow: hidden; }}
.card-img img {{ width: 100%; height: 100%; object-fit: contain; background: white; }}
.no-img {{ color: var(--muted); font-size: 11px; }}
.card-body {{ padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 2px; flex: 1; }}
.card-body .num {{ font-size: 10px; color: var(--muted); font-weight: 600; }}
.card-body .code {{ font-size: 11px; color: var(--accent); font-weight: 700;
  font-family: ui-monospace, monospace; }}
.card-body .title {{ font-size: 12px; font-weight: 600; line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; min-height: 47px; }}
.card-body .cat {{ font-size: 10px; color: var(--muted); font-style: italic; }}
.card-body .barcode {{ font-size: 10px; color: var(--muted); font-family: monospace; }}
.card-body .meta {{ display: flex; gap: 3px; flex-wrap: wrap; margin-top: 4px; }}
.badge {{ font-size: 9px; padding: 1px 5px; border-radius: 3px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .03em; }}
.badge-size {{ background: #eff6ff; color: #1e40af; }}
.badge-engine {{ background: #f0fdf4; color: #166534; }}
.badge-fail {{ background: #fef2f2; color: #991b1b; }}
.src-link {{ font-size: 10px; color: var(--accent); text-decoration: none; margin-top: 3px; }}
.src-link:hover {{ text-decoration: underline; }}
footer {{ text-align: center; padding: 20px; color: var(--muted); font-size: 11px;
  border-top: 1px solid var(--border); background: white; }}
@media (max-width: 600px) {{
  .toolbar {{ top: 180px; }}
  .grid {{ grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }}
  main {{ padding: 10px; }}
}}
</style>
</head>
<body>
<header>
  <h1>Product Images Gallery — Self-contained ({total:,} products)</h1>
  <div class="sub">All {with_img:,} images embedded as base64 thumbnails · Single HTML file · No internet needed to view</div>
  <div class="summary">
    <div class="metric"><div class="label">Total products</div><div class="value">{total:,}</div></div>
    <div class="metric"><div class="label">With image</div><div class="value">{with_img:,} <span style="font-size:12px;opacity:.85">({pct:.1f}%)</span></div></div>
    <div class="metric"><div class="label">Thumbnails</div><div class="value">{THUMB_SIZE}px</div></div>
    <div class="metric"><div class="label">File size</div><div class="value">~{human_size(total_b64_bytes)}</div></div>
  </div>
</header>

<div class="toolbar">
  <input type="text" id="search" placeholder="🔍 Search by name, code, barcode, or #number..." />
  <select id="filter-src">
    <option value="">All sources</option>
    <option value="file1">File 1 (medical)</option>
    <option value="file2">File 2 (rehab)</option>
  </select>
  <span class="count" id="count">{total} shown</span>
</div>

<main>
  <div class="grid" id="grid">{''.join(cards_html)}</div>
</main>

<footer>
  Self-contained HTML gallery · {total:,} products · {with_img:,} images embedded as base64 · ~{human_size(total_b64_bytes)} total
</footer>

<script>
(function(){{
  const search = document.getElementById('search');
  const fSrc = document.getElementById('filter-src');
  const count = document.getElementById('count');
  const cards = Array.from(document.querySelectorAll('.card'));
  function apply(){{
    const q = search.value.trim().toLowerCase();
    const src = fSrc.value;
    let shown = 0;
    cards.forEach(c => {{
      const text = c.textContent.toLowerCase();
      const matchQ = !q || text.includes(q);
      const matchSrc = !src || c.dataset.src === src;
      const visible = matchQ && matchSrc;
      c.style.display = visible ? '' : 'none';
      if (visible) shown++;
    }});
    count.textContent = shown + ' shown';
  }}
  search.addEventListener('input', apply);
  fSrc.addEventListener('change', apply);
}})();
</script>
</body>
</html>"""

    OUT_HTML.write_text(doc, encoding="utf-8")
    final_size = OUT_HTML.stat().st_size
    print(f"\n✓ Wrote: {OUT_HTML}")
    print(f"  Final size: {human_size(final_size)}")
    print(f"  Products: {total:,}  |  With image: {with_img:,} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
