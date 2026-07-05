# 🏥 PT Inventory Analyzer + Product Images

مشروع متكامل لتحليل جرد المعدات الطبية مع عرض صور المنتجات المطابقة تلقائياً.

## 📦 المحتويات

| المسار | الوصف |
|--------|-------|
| `download/index.html` | صفحة PT Inventory Analyzer (معدّلة لعرض الصور) |
| `download/product_index.json` | فهرس 4,498 منتج (أكواد + باركود + أوصاف) |
| `download/product_images/` | 4,498 صورة منتج بأسماء `<num>.jpg` (~37KB للصورة) |
| `download/product_gallery.html` | معرض صور تفاعلي لكل المنتجات |
| `download/product_gallery_standalone.html` | معرض مستقل (يحتوي كل الصور مدمجة) |
| `download/README.md` | تعليمات التشغيل على Netlify |
| `scripts/` | سكربتات الـ scraping والمعالجة (Python) |
| `pt-inventory-gold-mobile-final.html` | النسخة الأصلية للصفحة (احتياطية) |

## 🚀 التشغيل السريع

### 1. فتح مباشر (Local)
```bash
# افتح ملف HTML مباشرة في المتصفح
open download/index.html        # macOS
xdg-open download/index.html    # Linux
start download/index.html       # Windows
```

### 2. نشر على Netlify
1. اذهب إلى https://app.netlify.com/drop
2. اسحب مجلد `download/` كاملاً
3. تحصل على URL فوري مثل `https://random-name.netlify.app`

### 3. نشر على GitHub Pages
```bash
git push origin main
# في إعدادات GitHub: Settings → Pages → Branch: main → /download
```

## 🎯 كيف تعمل مطابقة الصور

عند تحليل كل منتج في الصفحة، تتم المطابقة بثلاث طرق (بالتسلسل):

1. **مطابقة الكود** — 812 منتج بكود فريد (مثل `MGE30003`)
2. **مطابقة الباركود** — 4,497 منتج بباركود 13 رقم
3. **مطابقة تشابه الوصف** — يتطلب تطابق كلمتين على الأقل لتفادي الأخطاء

إذا لم يوجد تطابق، البطاقة تظهر بدون صورة (مرونة كاملة).

## 📊 إحصائيات

- **المنتجات الإجمالية:** 4,498
- **الصور المُجمَّعة:** 4,498 (100%)
- **متوسط حجم الصورة:** 37 KB
- **الحجم الإجمالي للصور:** 174 MB
- **محركات البحث المستخدمة:** Bing (83%) + DuckDuckGo + Google + Yandex + Brave

## 🔧 سكربتات الـ Scraping

```bash
# 1. تحليل ملفات المنتجات
python3 scripts/parse_products.py

# 2. تشغيل الـ scraper (مع دعم الاستئناف)
python3 scripts/scrape_images.py --workers 6

# 3. إعادة محاولة الفاشل
python3 scripts/retry_failed.py

# 4. بناء فهرس المنتجات
python3 scripts/build_product_index.py

# 5. بناء صفحة HTML gallery
python3 scripts/build_gallery.py
python3 scripts/build_standalone_gallery.py
```

كل السكربتات **بدون API ومجانية** بالكامل.

## 🛠️ التقنيات

- **Frontend:** HTML/CSS/JavaScript (vanilla, no framework)
- **Backend:** لا يوجد (client-side only)
- **Scraping:** Python + requests + BeautifulSoup + Pillow
- **Hosting:** Netlify / GitHub Pages (static)
- **No API keys required** — كل شيء مجاني

## 📝 الترخيص

استخدام شخصي/تجاري — الصور من مصادر عامة على الإنترنت.
