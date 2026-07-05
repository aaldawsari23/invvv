# تحسين صور المنتجات

## ما تغير

تمت إضافة سكربت جديد:

```bash
scripts/scrape_images_trusted.py
```

الهدف منه تصحيح الصور بدون تخريب عشوائي:

- لا يقبل أول صورة تظهر من البحث.
- يعطي أولوية لمواقع طبية ومتاجر Rehab ومصنعين معروفين.
- يرفض Pinterest والسوشال ومواقع stock photos واللوقوهات والصور العامة.
- يطابق بالكود والباركود والوصف.
- لا يستبدل صورة موجودة إلا عند تشغيل `--replace`.
- إذا استبدل صورة قديمة، يحفظ نسخة احتياطية في:

```bash
download/product_images_old/
```

## التشغيل اليدوي الآمن محليًا

تثبيت المتطلبات:

```bash
pip install -r requirements-images.txt
```

تجربة بدون استبدال:

```bash
python scripts/scrape_images_trusted.py --limit 20 --dry-run
```

تدقيق مصادر الصور القديمة من اللوقات:

```bash
python scripts/scrape_images_trusted.py --audit-existing
```

استبدال منتجات محددة فقط:

```bash
python scripts/scrape_images_trusted.py --ids 24053,24054 --replace --workers 2 --min-score 62
python scripts/build_product_index.py
```

تشغيل دفعة صغيرة:

```bash
python scripts/scrape_images_trusted.py --limit 50 --replace --workers 3 --min-score 62
python scripts/build_product_index.py
```

## التشغيل من GitHub Actions

افتح:

```text
Actions → Refresh trusted product images → Run workflow
```

لأول تجربة استخدم:

```text
limit = 50
replace = false
min_score = 62
```

إذا اللوق ممتاز، شغل:

```text
replace = true
```

لا تشغل 4000 صورة كاملة من أول مرة. ابدأ بـ 50، ثم 200، ثم الكل.

## ملاحظة

إذا لم يوجد `download/_work/products.csv`، الـworkflow ينشئه تلقائيًا من `download/product_index.json` باستخدام:

```bash
scripts/product_index_to_products_csv.py
```
