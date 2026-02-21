from pathlib import Path

from importation_releve_compteur_universelle import run


def test_run_csv_to_universal(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    mapping_path = tmp_path / "mapping.json"
    output_path = tmp_path / "output.csv"

    input_path.write_text(
        "Compteur,Client,Valeur,Date,Unite,Systeme\n"
        "M-1,C-1,100.5,01/01/2026,kWh,SYS_A\n",
        encoding="utf-8",
    )

    mapping_path.write_text(
        '{"meter_id":"Compteur","customer_id":"Client","reading_value":"Valeur",'
        '"reading_date":"Date","unit":"Unite","source_system":"Systeme","date_format":"%d/%m/%Y"}',
        encoding="utf-8",
    )

    total, imported = run(input_path, output_path, "csv", mapping_path, "fallback")

    assert total == 1
    assert imported == 1
    content = output_path.read_text(encoding="utf-8")
    assert "meter_id,customer_id,reading_value,reading_date,unit,source_system" in content
    assert "M-1,C-1,100.500,2026-01-01,kWh,SYS_A" in content
