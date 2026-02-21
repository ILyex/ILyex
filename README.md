# Importation Relevé Compteur Universelle

نسخة نهائية لتشغيل برنامج **Importation Relevé Compteur Universelle** على ويندوز كملف تنفيذي `.exe`.

## للمستخدم النهائي (Windows)
بعد بناء البرنامج ستحصل على:
- `ImportationReleveCompteurUniverselle.exe`

تشغيله يكون مباشرة بالنقر المزدوج، وسيفتح الواجهة تلقائياً في المتصفح على:
- `http://127.0.0.1:5000`

> لا تحتاج تشغيل ملفات Python أو التعامل مع ملفات برمجية.

## الميزات
- استيراد: `CSV / JSON / XLSX / EXL`
- تصدير: `CSV / XLSX`
- واجهة Dashboard
- Mapping قابل للتعديل
- تحقق من صحة البيانات قبل التطبيع

## بناء EXE محلياً (على Windows)
```bat
build_windows_exe.bat
```
الناتج:
- `dist\ImportationReleveCompteurUniverselle.exe`

## بناء EXE عبر GitHub Actions
تم إضافة Workflow جاهز:
- `.github/workflows/build-windows-exe.yml`

بعد تشغيله (workflow_dispatch) حمّل Artifact:
- `ImportationReleveCompteurUniverselle-exe`

## تشغيل يدوي (للمطور)
### وضع الواجهة
```bash
python3 importation_releve_compteur_universelle.py --desktop --host 127.0.0.1 --port 5000
```

### وضع CLI
```bash
python3 importation_releve_compteur_universelle.py \
  --input examples/readings.csv \
  --output output/universal_readings.xlsx \
  --format csv \
  --mapping examples/mapping_csv.json \
  --source-name ERP_GLOBAL
```

## الاختبارات
```bash
python3 -m pytest -q
```
