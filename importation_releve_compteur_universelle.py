#!/usr/bin/env python3
"""Importation Releve Compteur Universelle.

Un outil CLI pour normaliser des releves compteurs depuis des sources CSV/JSON
vers un format universel unique.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

UNIVERSAL_FIELDS = [
    "meter_id",
    "customer_id",
    "reading_value",
    "reading_date",
    "unit",
    "source_system",
]


@dataclass
class Mapping:
    meter_id: str
    customer_id: str
    reading_value: str
    reading_date: str
    unit: str = ""
    source_system: str = ""
    date_format: str = "%Y-%m-%d"


class ValidationError(ValueError):
    """Erreur de validation sur une ligne de releve."""


def load_mapping(path: Path) -> Mapping:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Mapping(
        meter_id=data["meter_id"],
        customer_id=data["customer_id"],
        reading_value=data["reading_value"],
        reading_date=data["reading_date"],
        unit=data.get("unit", ""),
        source_system=data.get("source_system", ""),
        date_format=data.get("date_format", "%Y-%m-%d"),
    )


def read_rows(path: Path, source_format: str) -> Iterable[dict[str, Any]]:
    if source_format == "csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            yield from reader
        return

    if source_format == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            items = payload.get("readings", [])
        else:
            items = payload
        if not isinstance(items, list):
            raise ValidationError("Le JSON doit contenir une liste de releves.")
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("Chaque releve JSON doit etre un objet.")
            yield item
        return

    raise ValidationError(f"Format source non supporte: {source_format}")


def normalize_row(row: dict[str, Any], mapping: Mapping, default_source: str) -> dict[str, str]:
    def pick(field: str) -> str:
        if not field:
            return ""
        value = row.get(field)
        return "" if value is None else str(value).strip()

    meter_id = pick(mapping.meter_id)
    customer_id = pick(mapping.customer_id)
    raw_value = pick(mapping.reading_value)
    raw_date = pick(mapping.reading_date)
    unit = pick(mapping.unit) if mapping.unit else "kWh"
    source_system = pick(mapping.source_system) if mapping.source_system else default_source

    if not meter_id:
        raise ValidationError("meter_id vide")
    if not customer_id:
        raise ValidationError("customer_id vide")

    try:
        reading_value = float(raw_value)
    except ValueError as exc:
        raise ValidationError(f"reading_value invalide: {raw_value}") from exc

    try:
        parsed_date = dt.datetime.strptime(raw_date, mapping.date_format).date()
    except ValueError as exc:
        raise ValidationError(
            f"reading_date invalide: {raw_date} (format attendu {mapping.date_format})"
        ) from exc

    return {
        "meter_id": meter_id,
        "customer_id": customer_id,
        "reading_value": f"{reading_value:.3f}",
        "reading_date": parsed_date.isoformat(),
        "unit": unit,
        "source_system": source_system,
    }


def write_universal_csv(rows: Iterable[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=UNIVERSAL_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(input_path: Path, output_path: Path, source_format: str, mapping_path: Path, source_name: str) -> tuple[int, int]:
    mapping = load_mapping(mapping_path)
    normalized: list[dict[str, str]] = []
    total = 0

    for total, row in enumerate(read_rows(input_path, source_format), start=1):
        normalized.append(normalize_row(row, mapping, source_name))

    write_universal_csv(normalized, output_path)
    return total, len(normalized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importation Releve Compteur Universelle - normalise des releves vers CSV universel"
    )
    parser.add_argument("--input", required=True, type=Path, help="Fichier source CSV ou JSON")
    parser.add_argument("--output", required=True, type=Path, help="Fichier CSV universel en sortie")
    parser.add_argument("--format", choices=["csv", "json"], required=True, help="Format du fichier source")
    parser.add_argument("--mapping", required=True, type=Path, help="Mapping JSON des champs source")
    parser.add_argument("--source-name", default="unknown", help="Nom du systeme source")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        total, imported = run(args.input, args.output, args.format, args.mapping, args.source_name)
    except ValidationError as exc:
        raise SystemExit(f"Erreur d'import: {exc}")

    print(f"Import termine: {imported}/{total} releves normalises vers {args.output}")


if __name__ == "__main__":
    main()
