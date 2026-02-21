# Importation Releve Compteur Universelle

Petit programme Python pour **importer et normaliser des releves compteurs** provenant de fichiers CSV/JSON vers un format universel unique.

## Fonctionnalites
- Import CSV ou JSON
- Mapping configurable des champs source
- Validation des valeurs et des dates
- Export vers CSV universel

## Utilisation
```bash
python3 importation_releve_compteur_universelle.py \
  --input examples/readings.csv \
  --output output/universal_readings.csv \
  --format csv \
  --mapping examples/mapping_csv.json \
  --source-name ERP_GLOBAL
```

## Format universel de sortie
Colonnes generees:
- `meter_id`
- `customer_id`
- `reading_value`
- `reading_date` (ISO `YYYY-MM-DD`)
- `unit`
- `source_system`

## Tests
```bash
python3 -m pytest -q
```
