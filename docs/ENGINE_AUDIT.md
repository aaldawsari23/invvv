# PT Inventory Analyzer Audit

Branch: `production-clean`
Repo: `aaldawsari23/invvv`

## Files inspected

Active app files:

```text
download/index.html
download/analyzer-lite.css
download/analyzer-lite.js
```

Deployment should publish:

```text
download
```

A root `netlify.toml` was added because Netlify usually reads config from the repo root.

## Current capabilities

The current app supports multi-file upload, Excel parsing through SheetJS, CSV/TSV/TXT/JSON reading, basic header detection, code/barcode/description matching, decision tabs, filtering, mobile cards, and CSV export.

## Critical issue found

`download/product_index.json` was empty on `main`.

Impact:

- product reference matching does not load
- code/barcode/image matching becomes unavailable
- image workflow fallback can crash on JSON decode
- analyzer falls back to text classification only

Fix on this branch:

```text
download/product_index.json
```

was initialized as valid empty JSON. This prevents runtime failure, but it is not a real populated production index.

## Builder fixes

### `scripts/build_product_index.py`

Updated so products are included even when an image is missing. The old logic skipped any product without `product_images/<num>.jpg`, which is wrong for an analyzer. Image availability should not control whether a product can be matched.

### `scripts/product_index_to_products_csv.py`

Updated to handle missing, empty, or invalid `product_index.json` without crashing. It can write a header-only CSV as a safe fallback.

### `scripts/stage2_build_products_csv.py`

Added a stable Stage 2 wrapper command:

```bash
python scripts/stage2_build_products_csv.py
```

It validates row count, duplicate product numbers, missing descriptions, code coverage, and barcode coverage.

## Still missing

A real populated canonical file is still missing:

```text
download/_work/products.csv
```

Minimum columns:

```text
num,code,barcode,desc,cat,subcat,source_file
```

After restoring it, run:

```bash
python scripts/stage2_build_products_csv.py
python scripts/build_product_index.py
```

## Decision

This branch is safer than `main`, but it is not a final production release until the real product CSV is restored and `download/product_index.json` is rebuilt with real rows.
