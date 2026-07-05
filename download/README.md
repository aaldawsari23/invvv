# PT Inventory Analyzer + Product Images

## Quick Start (Netlify)

### Option 1: Drag & Drop Deploy
1. Go to https://app.netlify.com/drop
2. Drag the **entire folder** (this directory) into the page
3. Netlify will publish it instantly — you get a URL like `https://random-name.netlify.app`

### Option 2: Connect to GitHub
1. Push this folder to a GitHub repo (e.g., `aaldawsari23/invvv`)
2. In Netlify dashboard → "Add new site" → "Import from Git"
3. Choose your repo. Build settings:
   - **Build command:** (leave empty)
   - **Publish directory:** `.` (the root)
4. Click "Deploy site"

## What's Inside

| Path | Purpose |
|------|---------|
| `index.html` | The PT Inventory Analyzer page (modified to display product images) |
| `product_index.json` | Lookup index of 4,498 products (codes, barcodes, descriptions) |
| `product_images/` | 4,498 product images named `<num>.jpg` (~37 KB each, ~174 MB total) |
| `netlify.toml` | Netlify configuration (caching, headers) |
| `README.md` | This file |
| `pt-inventory-gold-mobile-final.html` | Original HTML (backup) |

## How Image Matching Works

When the analyzer renders a product card, it tries to find a matching image:

1. **Exact code match** — If the item's `sku`/`code` matches one of our 812 product codes (e.g., `MGE30003`), the image is shown.
2. **Exact barcode match** — If the item has an 8+ digit barcode matching our 4,497 barcodes, the image is shown.
3. **Fuzzy description match** — Falls back to token-overlap matching against 4,498 product descriptions. Requires at least 2 matching tokens to avoid false positives.

If no match is found, the card renders normally without an image (graceful degradation).

## Usage

1. Open `index.html` in a browser (or visit the Netlify URL)
2. Upload an Excel/CSV/TSV/TXT/JSON inventory file
3. The analyzer will:
   - Parse the file
   - Score & classify each item (PT / Review / Non-PT)
   - Display cards with images (when a match is found)
4. Use filters, search, and sort to drill into results
5. Export to CSV/JSON/HTML

## Tech Notes

- 100% client-side — no server, no API keys, no database
- Product images are JPEG, max 600px, ~37 KB average
- Total site weight: ~176 MB (one-time load, then cached by Netlify CDN forever)
- The `product_index.json` is loaded asynchronously on page load — doesn't block the UI

## Re-Scraping Images (Optional)

The scraping scripts are in the `scripts/` folder of the source project. They use:
- Bing Image Search (primary, 83% of images)
- DuckDuckGo Images (fallback)
- Google/Yandex/Brave (last resort)

Re-run with: `python3 scripts/scrape_images.py` (resumes automatically — skips already-scraped products).
