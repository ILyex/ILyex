import json
from pathlib import Path

from importation_releve_compteur_universelle import _rows_from_xlsx_bytes, _write_xlsx_bytes, run


def test_run_csv_to_universal(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    mapping_path = tmp_path / "mapping.json"
    output_path = tmp_path / "output.csv"

    input_path.write_text(
        "Compteur,Client,Valeur,Date,Unite,Systeme\nM-1,C-1,100.5,01/01/2026,kWh,SYS_A\n",
        encoding="utf-8",
    )
    mapping_path.write_text(
        json.dumps(
            {
                "meter_id": "Compteur",
                "customer_id": "Client",
                "reading_value": "Valeur",
                "reading_date": "Date",
                "unit": "Unite",
                "source_system": "Systeme",
                "date_format": "%d/%m/%Y",
            }
        ),
        encoding="utf-8",
    )

    total, imported = run(input_path, output_path, "csv", mapping_path, "fallback")
    assert total == imported == 1
    assert "M-1,C-1,100.500,2026-01-01,kWh,SYS_A" in output_path.read_text(encoding="utf-8")


def test_xlsx_roundtrip() -> None:
    content = _write_xlsx_bytes(
        [
            {
                "meter_id": "M-9",
                "customer_id": "C-9",
                "reading_value": "88.100",
                "reading_date": "2026-02-02",
                "unit": "kWh",
                "source_system": "SYS_X",
            }
        ]
    )
    rows = list(_rows_from_xlsx_bytes(content))
    assert rows[0]["meter_id"] == "M-9"
    assert rows[0]["source_system"] == "SYS_X"
