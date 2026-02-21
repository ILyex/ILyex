# Importation Relevé Compteur Universelle

تم تطوير نسخة جديدة بواجهة قريبة من التصميم المطلوب (Dashboard) مع دعم:
- استيراد: CSV / JSON / XLSX / EXL
- تصدير: CSV / XLSX
- توحيد القراءات في مخطط عالمي

## تشغيل الواجهة
```bash
python3 importation_releve_compteur_universelle.py --serve --host 0.0.0.0 --port 5000
```
افتح:
`http://localhost:5000`

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
