#!/usr/bin/env python3
"""
Generate a professional HTML gallery showing all scraped product images.
Reads:
  - /home/z/my-project/download/_work/products.csv  (product metadata)
  - /home/z/my-project/download/_work/scrape_log.csv (scrape results)
  - /home/z/my-project/download/product_images/*.jpg (image files)
Writes:
  - /home/z/my-project/download/product_gallery.html
"""
import csv
import html
import os
from pathlib import Path

ROOT = Path("/home/z/my-project/download")
PRODUCTS_CSV = ROOT / "_work/products.csv"
LOG_CSV       = ROOT / "_work/scrape_log.csv"
IMG_DIR       = ROOT / "product_images"
OUT_HTML      = ROOT / "product_gallery.html"


def load_products():
    out = {}
    if not PRODUCTS_CSV.exists():
        return out
    with open(PRODUCTS_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["num"]] = r
    return out


def load_log():
    """Returns dict num -> log row (latest one wins)."""
    out = {}
    if not LOG_CSV.exists():
        return out
    with open(LOG_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["num"]] = r
    return out


def human_size(b: float) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f} KB"
    return f"{b/1024/1024:.2f} MB"


def main():
    products = load_products()
    log_rows = load_log()

    # Build a unified list of cards
    cards = []
    for num, prod in products.items():
        log = log_rows.get(num, {})
        img_path = IMG_DIR / f"{num}.jpg"
        has_img = img_path.exists()
        size = img_path.stat().st_size if has_img else 0
        cards.append({
            "num":      num,
            "code":     prod.get("code", ""),
            "barcode":  prod.get("barcode", ""),
            "desc":     prod.get("desc", ""),
            "cat":      prod.get("cat", ""),
            "subcat":   prod.get("subcat", ""),
            "src":      prod.get("source_file", ""),
            "has_img":  has_img,
            "img_path": f"product_images/{num}.jpg" if has_img else "",
            "size":     size,
            "engine":   log.get("engine", ""),
            "source_url": log.get("source_url", ""),
            "query":    log.get("query", ""),
        })

    total = len(cards)
    with_img = sum(1 for c in cards if c["has_img"])
    without_img = total - with_img
    total_size = sum(c["size"] for c in cards)

    # Group by source file for stats
    by_src = {}
    for c in cards:
        s = c["src"] or "unknown"
        d = by_src.setdefault(s, {"total": 0, "ok": 0})
        d["total"] += 1
        if c["has_img"]:
            d["ok"] += 1

    # Group by category for stats
    by_cat = {}
    for c in cards:
        cat = c["cat"] or "(no category)"
        d = by_cat.setdefault(cat, {"total": 0, "ok": 0})
        d["total"] += 1
        if c["has_img"]:
            d["ok"] += 1

    # Group by engine
    by_engine = {}
    for c in cards:
        if c["has_img"]:
            e = c["engine"] or "unknown"
            by_engine[e] = by_engine.get(e, 0) + 1

    # ----- HTML -----
    cards_html = []
    for c in cards:
        title = c["desc"] or c["code"] or c["barcode"] or f"Product #{c['num']}"
        title_esc = html.escape(title[:300])
        code_esc = html.escape(c["code"])
        bar_esc  = html.escape(c["barcode"])
        cat_esc  = html.escape(f"{c['cat']} / {c['subcat']}".strip(" /"))

        if c["has_img"]:
            img_tag = (
                f'<img src="{c["img_path"]}" loading="lazy" '
                f'alt="{title_esc}" '
                f'onerror="this.onerror=null;this.src=\'data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22300%22><rect fill=%22%23eee%22 width=%22300%22 height=%22300%22/><text x=%22150%22 y=%22150%22 font-family=%22Arial%22 font-size=%2216%22 fill=%22%23999%22 text-anchor=%22middle%22>Image not available</text></svg>\';this.parentNode.classList.add(\'no-img\')" />'
            )
            size_str = human_size(c["size"])
            engine_badge = (
                f'<span class="badge badge-engine">{html.escape(c["engine"])}</span>'
                if c["engine"] else ""
            )
            img_meta = (
                f'<div class="meta">'
                f'<span class="badge badge-size">{size_str}</span>'
                f'{engine_badge}'
                f'</div>'
            )
        else:
            img_tag = (
                '<div class="no-img-placeholder">'
                '<svg width="64" height="64" viewBox="0 0 24 24" fill="none" '
                'stroke="currentColor" stroke-width="1.5">'
                '<rect x="3" y="3" width="18" height="18" rx="2"/>'
                '<circle cx="8.5" cy="8.5" r="1.5"/>'
                '<path d="M21 15l-5-5L5 21"/>'
                '</svg>'
                '<span>Image not available</span>'
                '</div>'
            )
            img_meta = '<div class="meta"><span class="badge badge-fail">not found</span></div>'

        # Source URL link
        src_link = ""
        if c["source_url"]:
            src_link = (
                f'<a href="{html.escape(c["source_url"])}" target="_blank" rel="noopener" '
                f'class="src-link" title="Open source URL">source ↗</a>'
            )

        cards_html.append(f"""
        <article class="card{' has-img' if c['has_img'] else ' no-img'}" data-cat="{html.escape(c['cat'] or '')}" data-src="{c['src']}" data-has-img="{'1' if c['has_img'] else '0'}">
          <div class="card-img">
            {img_tag}
          </div>
          <div class="card-body">
            <div class="num">#{html.escape(c['num'])}</div>
            {f'<div class="code">{code_esc}</div>' if code_esc else ''}
            <div class="title" title="{title_esc}">{title_esc}</div>
            {f'<div class="cat">{cat_esc}</div>' if cat_esc else ''}
            {f'<div class="barcode">GTIN: {bar_esc}</div>' if bar_esc else ''}
            {img_meta}
            {src_link}
          </div>
        </article>""")

    # Source stats
    src_stats_html = "".join(
        f'<div class="stat-pill"><strong>{html.escape(s)}</strong>: '
        f'<span class="ok">{d["ok"]}</span>/<span class="tot">{d["total"]}</span> '
        f'({100*d["ok"]/d["total"]:.1f}%)</div>'
        for s, d in sorted(by_src.items())
    )

    # Category stats
    cat_stats_html = "".join(
        f'<div class="stat-pill"><strong>{html.escape(cat)}</strong>: '
        f'<span class="ok">{d["ok"]}</span>/<span class="tot">{d["total"]}</span></div>'
        for cat, d in sorted(by_cat.items(), key=lambda x: -x[1]["total"])
    )

    # Engine stats
    eng_stats_html = "".join(
        f'<div class="stat-pill"><strong>{html.escape(e)}</strong>: {n}</div>'
        for e, n in sorted(by_engine.items(), key=lambda x: -x[1])
    )

    pct = 100 * with_img / total if total else 0

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Product Images Gallery — {total} products</title>
<style>
:root {{
  --bg: #f6f7f9;
  --card: #ffffff;
  --text: #1a1a1a;
  --muted: #6b7280;
  --border: #e5e7eb;
  --accent: #2563eb;
  --ok: #16a34a;
  --warn: #d97706;
  --fail: #dc2626;
  --shadow: 0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
  --shadow-hover: 0 10px 25px rgba(0,0,0,.08), 0 4px 10px rgba(0,0,0,.04);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}
header {{
  background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
  color: white;
  padding: 32px 24px 24px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,.1);
}}
header h1 {{ margin: 0 0 8px; font-size: 24px; font-weight: 700; }}
header .sub {{ opacity: .9; font-size: 14px; }}
header .summary {{
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}}
.summary .metric {{
  background: rgba(255,255,255,.15);
  border-radius: 8px;
  padding: 10px 14px;
}}
.summary .metric .label {{ font-size: 11px; opacity: .85; text-transform: uppercase; letter-spacing: .05em; }}
.summary .metric .value {{ font-size: 22px; font-weight: 700; margin-top: 2px; }}
.summary .metric .value .pct {{ font-size: 13px; opacity: .85; font-weight: 400; }}

.toolbar {{
  background: white;
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  position: sticky;
  top: 145px;
  z-index: 99;
}}
.toolbar input, .toolbar select {{
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  background: white;
}}
.toolbar input {{ flex: 1; min-width: 220px; }}
.toolbar input:focus, .toolbar select:focus {{ outline: 2px solid var(--accent); outline-offset: -1px; }}
.toolbar .count {{ color: var(--muted); font-size: 13px; }}

.stats-row {{
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}}
.stats-row h3 {{
  width: 100%;
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
}}
.stat-pill {{
  background: var(--bg);
  border-radius: 16px;
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid var(--border);
}}
.stat-pill .ok {{ color: var(--ok); font-weight: 600; }}
.stat-pill .tot {{ color: var(--muted); }}

main {{
  padding: 24px;
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}}
.card {{
  background: var(--card);
  border-radius: 10px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  overflow: hidden;
  transition: box-shadow .2s, transform .2s;
  display: flex;
  flex-direction: column;
}}
.card:hover {{
  box-shadow: var(--shadow-hover);
  transform: translateY(-2px);
}}
.card.no-img {{ opacity: .85; }}
.card-img {{
  position: relative;
  background: #f3f4f6;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}}
.card-img img {{
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: white;
  transition: transform .3s;
}}
.card:hover .card-img img {{ transform: scale(1.04); }}
.card.no-img .card-img img {{ display: none; }}
.no-img-placeholder {{
  color: var(--muted);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}}
.card-body {{
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}}
.card-body .num {{
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}}
.card-body .code {{
  font-size: 12px;
  color: var(--accent);
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}}
.card-body .title {{
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 53px;
}}
.card-body .cat {{
  font-size: 11px;
  color: var(--muted);
  font-style: italic;
}}
.card-body .barcode {{
  font-size: 11px;
  color: var(--muted);
  font-family: ui-monospace, monospace;
}}
.card-body .meta {{
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}}
.badge {{
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .03em;
}}
.badge-size  {{ background: #eff6ff; color: #1e40af; }}
.badge-engine {{ background: #f0fdf4; color: #166534; }}
.badge-fail  {{ background: #fef2f2; color: #991b1b; }}
.src-link {{
  font-size: 11px;
  color: var(--accent);
  text-decoration: none;
  margin-top: 4px;
  align-self: flex-start;
}}
.src-link:hover {{ text-decoration: underline; }}

footer {{
  text-align: center;
  padding: 24px;
  color: var(--muted);
  font-size: 12px;
  border-top: 1px solid var(--border);
  background: white;
}}

@media (max-width: 600px) {{
  .toolbar {{ top: 200px; }}
  .grid {{ grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }}
  main {{ padding: 12px; }}
  header {{ padding: 20px 16px 16px; }}
}}
</style>
</head>
<body>

<header>
  <h1>Product Images Gallery</h1>
  <div class="sub">Scraped product images — multi-engine (Bing + DuckDuckGo + Google + Yandex + Brave), no API, free</div>
  <div class="summary">
    <div class="metric">
      <div class="label">Total products</div>
      <div class="value">{total:,}</div>
    </div>
    <div class="metric">
      <div class="label">Images found</div>
      <div class="value">{with_img:,} <span class="pct">({pct:.1f}%)</span></div>
    </div>
    <div class="metric">
      <div class="label">Not found</div>
      <div class="value">{without_img:,} <span class="pct">({100-pct:.1f}%)</span></div>
    </div>
    <div class="metric">
      <div class="label">Total images size</div>
      <div class="value">{human_size(total_size)}</div>
    </div>
  </div>
</header>

<div class="toolbar">
  <input type="text" id="search" placeholder="🔍 Search by name, code, barcode, or number..." />
  <select id="filter-src">
    <option value="">All sources</option>
    <option value="file1">File 1 (medical equipment)</option>
    <option value="file2">File 2 (rehab supplies)</option>
  </select>
  <select id="filter-img">
    <option value="">All</option>
    <option value="1">With image</option>
    <option value="0">Without image</option>
  </select>
  <span class="count" id="count">{total} shown</span>
</div>

<div class="stats-row">
  <h3>By source</h3>
  {src_stats_html}
</div>

<div class="stats-row">
  <h3>By engine (successful images)</h3>
  {eng_stats_html}
</div>

<main>
  <div class="grid" id="grid">
    {''.join(cards_html)}
  </div>
</main>

<footer>
  Generated from {total} product records · {with_img} images ({pct:.1f}%) · Total {human_size(total_size)}
</footer>

<script>
(function(){{
  const search = document.getElementById('search');
  const fSrc = document.getElementById('filter-src');
  const fImg = document.getElementById('filter-img');
  const count = document.getElementById('count');
  const cards = Array.from(document.querySelectorAll('.card'));

  function apply(){{
    const q = search.value.trim().toLowerCase();
    const src = fSrc.value;
    const img = fImg.value;
    let shown = 0;
    cards.forEach(c => {{
      const num = c.querySelector('.num').textContent.toLowerCase();
      const code = (c.querySelector('.code')||{{}}).textContent || '';
      const title = (c.querySelector('.title')||{{}}).textContent || '';
      const barcode = (c.querySelector('.barcode')||{{}}).textContent || '';
      const text = (num + ' ' + code + ' ' + title + ' ' + barcode).toLowerCase();
      const matchQ = !q || text.includes(q);
      const matchSrc = !src || c.dataset.src === src;
      const matchImg = !img || c.dataset.hasImg === img;
      const visible = matchQ && matchSrc && matchImg;
      c.style.display = visible ? '' : 'none';
      if (visible) shown++;
    }});
    count.textContent = shown + ' shown';
  }}
  search.addEventListener('input', apply);
  fSrc.addEventListener('change', apply);
  fImg.addEventListener('change', apply);
}})();
</script>

</body>
</html>
"""

    OUT_HTML.write_text(doc, encoding="utf-8")
    print(f"Wrote {OUT_HTML} ({OUT_HTML.stat().st_size:,} bytes)")
    print(f"  Total products: {total}")
    print(f"  With image:     {with_img} ({pct:.1f}%)")
    print(f"  Without image:  {without_img}")
    print(f"  Total size:     {human_size(total_size)}")


if __name__ == "__main__":
    main()
