# Importation Relevé Compteur Universelle

تم تطوير البرنامج بواجهة Dashboard قريبة من الشكل المطلوب مع دعم:
- استيراد: CSV / JSON / XLSX / EXL
- تصدير: CSV / XLSX
- توحيد القراءات في مخطط عالمي

## تشغيل البرنامج (نسخة Python)
```bash
python3 importation_releve_compteur_universelle.py --desktop --host 127.0.0.1 --port 5000
```

## إنشاء ملف `.exe` لويندوز
### خيار 1: محلياً على Windows
شغّل الملف:
```bat
build_windows_exe.bat
```
الناتج سيكون:
- `dist\ImportationReleveCompteurUniverselle.exe`

### خيار 2: عبر GitHub Actions
يوجد Workflow جاهز:
- `.github/workflows/build-windows-exe.yml`

بعد تشغيله، حمّل Artifact باسم:
- `ImportationReleveCompteurUniverselle-exe`

## تشغيل CLI
```bash
python3 importation_releve_compteur_universelle.py \
  --input examples/readings.csv \
  --output output/universal_readings.xlsx \
  --format csv \
  --mapping examples/mapping_csv.json \
  --source-name ERP_GLOBAL
```

## اختبار
```bash
python3 -m pytest -q
```
