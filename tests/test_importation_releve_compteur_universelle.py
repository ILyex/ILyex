import json
from pathlib import Path

from importation_releve_compteur_universelle import (
    _rows_from_xlsx_bytes,
    _write_xlsx_bytes,
    build_parser,
    infer_mapping_from_headers,
    run,
)


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
    content = output_path.read_text(encoding="utf-8")
    assert "id_compteur,id_client,valeur_releve,date_releve,unite,systeme_source" in content


def test_xlsx_roundtrip() -> None:
    content = _write_xlsx_bytes(
        [
            {
                "id_compteur": "M-9",
                "id_client": "C-9",
                "valeur_releve": "88.100",
                "date_releve": "2026-02-02",
                "unite": "kWh",
                "systeme_source": "SYS_X",
            }
        ]
    )
    rows = list(_rows_from_xlsx_bytes(content))
    assert rows[0]["id_compteur"] == "M-9"


def test_infer_mapping() -> None:
    mapping = infer_mapping_from_headers(["id_compteur", "id_client", "valeur_releve", "date_releve"])
    assert mapping.meter_id == "id_compteur"
    assert mapping.customer_id == "id_client"


def test_parser_desktop_flag() -> None:
    args = build_parser().parse_args(["--desktop", "--port", "5050"])
    assert args.desktop is True
    assert args.port == 5050
