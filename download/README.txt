PRODUCT IMAGES PACKAGE
======================
Generated: 2026-07-05 00:59

CONTENTS
--------
  product_images/         - 4498 JPEG images, each named <product_number>.jpg
  product_gallery.html    - Interactive HTML gallery (open in browser)
  products.csv            - Normalized product metadata (4498 rows)
  scrape_log.csv          - Per-product scrape log (engine, source URL, status)
  scrape_retry_log.csv    - Retry log for previously failed products
  file1_original.txt      - Original upload #1 (812 medical equipment items)
  file2_original.txt      - Original upload #2 (3686 rehab supply items)
  README.txt              - This file

STATISTICS
----------
  Total products:           4,498
  Successfully scraped:     4,498 (100.0%)
  Total images size:        164.42 MB
  Average image size:       37.4 KB

  Images found via:
    - bing: 3750 images
    - cache: 652 images
    - duckduckgo: 74 images

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
