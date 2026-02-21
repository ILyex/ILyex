#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

UNIVERSAL_FIELDS = ["meter_id", "customer_id", "reading_value", "reading_date", "unit", "source_system"]
WEB_DIR = Path(__file__).parent / "web"

DEFAULT_MAPPING = {
    "meter_id": "Compteur",
    "customer_id": "Client",
    "reading_value": "Valeur",
    "reading_date": "Date",
    "unit": "Unite",
    "source_system": "Systeme",
    "date_format": "%d/%m/%Y",
}


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
    pass


def mapping_from_dict(data: dict[str, Any]) -> Mapping:
    return Mapping(
        meter_id=data["meter_id"],
        customer_id=data["customer_id"],
        reading_value=data["reading_value"],
        reading_date=data["reading_date"],
        unit=data.get("unit", ""),
        source_system=data.get("source_system", ""),
        date_format=data.get("date_format", "%Y-%m-%d"),
    )


def load_mapping(path: Path) -> Mapping:
    return mapping_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _rows_from_csv_text(text: str) -> Iterable[dict[str, Any]]:
    yield from csv.DictReader(io.StringIO(text))


def _excel_col(index: int) -> str:
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _rows_from_xlsx_bytes(payload: bytes) -> Iterable[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall("a:si", ns):
                text = "".join(t.text or "" for t in si.findall(".//a:t", ns))
                shared.append(text)

        sheet = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        matrix: list[list[str]] = []
        for row in sheet.findall(".//a:sheetData/a:row", ns):
            cells = {}
            max_idx = 0
            for c in row.findall("a:c", ns):
                ref = c.attrib.get("r", "A1")
                letters = "".join(ch for ch in ref if ch.isalpha())
                idx = 0
                for ch in letters:
                    idx = idx * 26 + (ord(ch.upper()) - 64)
                max_idx = max(max_idx, idx)
                value = ""
                t = c.attrib.get("t")
                v = c.find("a:v", ns)
                if t == "inlineStr":
                    n = c.find("a:is/a:t", ns)
                    value = "" if n is None else (n.text or "")
                elif v is not None:
                    raw = v.text or ""
                    if t == "s" and raw.isdigit():
                        value = shared[int(raw)] if int(raw) < len(shared) else ""
                    else:
                        value = raw
                cells[idx] = value
            line = [cells.get(i, "") for i in range(1, max_idx + 1)]
            matrix.append(line)

    if not matrix:
        return
    headers = [h.strip() for h in matrix[0]]
    for line in matrix[1:]:
        yield {headers[i]: line[i] if i < len(line) else "" for i in range(len(headers))}


def read_rows(path: Path, source_format: str) -> Iterable[dict[str, Any]]:
    if source_format == "csv":
        yield from _rows_from_csv_text(path.read_text(encoding="utf-8"))
    elif source_format == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("readings", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValidationError("Le JSON doit contenir une liste")
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("Chaque releve JSON doit etre un objet")
            yield item
    elif source_format in {"xlsx", "exl"}:
        yield from _rows_from_xlsx_bytes(path.read_bytes())
    else:
        raise ValidationError(f"Format source non supporte: {source_format}")


def normalize_row(row: dict[str, Any], mapping: Mapping, default_source: str) -> dict[str, str]:
    def pick(field: str) -> str:
        val = row.get(field) if field else ""
        return "" if val is None else str(val).strip()

    meter_id = pick(mapping.meter_id)
    customer_id = pick(mapping.customer_id)
    raw_value = pick(mapping.reading_value)
    raw_date = pick(mapping.reading_date)
    unit = pick(mapping.unit) if mapping.unit else "kWh"
    source_system = pick(mapping.source_system) if mapping.source_system else default_source

    if not meter_id or not customer_id:
        raise ValidationError("meter_id/customer_id vide")
    try:
        reading_value = float(raw_value)
    except ValueError as exc:
        raise ValidationError(f"reading_value invalide: {raw_value}") from exc
    try:
        parsed_date = dt.datetime.strptime(raw_date, mapping.date_format).date()
    except ValueError as exc:
        raise ValidationError(f"reading_date invalide: {raw_date}") from exc

    return {
        "meter_id": meter_id,
        "customer_id": customer_id,
        "reading_value": f"{reading_value:.3f}",
        "reading_date": parsed_date.isoformat(),
        "unit": unit,
        "source_system": source_system,
    }


def normalize_rows(rows: Iterable[dict[str, Any]], mapping: Mapping, source_name: str) -> list[dict[str, str]]:
    return [normalize_row(r, mapping, source_name) for r in rows]


def _write_csv_bytes(rows: Iterable[dict[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=UNIVERSAL_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _write_xlsx_bytes(rows: list[dict[str, str]]) -> bytes:
    def cell(ref: str, value: str) -> str:
        esc = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<c r="{ref}" t="inlineStr"><is><t>{esc}</t></is></c>'

    all_rows = [UNIVERSAL_FIELDS] + [[r[k] for k in UNIVERSAL_FIELDS] for r in rows]
    rows_xml = []
    for i, line in enumerate(all_rows, start=1):
        cells = "".join(cell(f"{_excel_col(j)}{i}", str(v)) for j, v in enumerate(line, start=1))
        rows_xml.append(f'<row r="{i}">{cells}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows_xml)}</sheetData></worksheet>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="UniversalReadings" sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        zf.writestr("xl/styles.xml", '<?xml version="1.0"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf xfId="0"/></cellXfs></styleSheet>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buf.getvalue()


def write_universal(rows: list[dict[str, str]], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        output_path.write_bytes(_write_csv_bytes(rows))
    elif output_format in {"xlsx", "exl"}:
        output_path.write_bytes(_write_xlsx_bytes(rows))
    else:
        raise ValidationError(f"Format sortie non supporte: {output_format}")


def run(input_path: Path, output_path: Path, source_format: str, mapping_path: Path, source_name: str) -> tuple[int, int]:
    mapping = load_mapping(mapping_path)
    normalized = normalize_rows(read_rows(input_path, source_format), mapping, source_name)
    write_universal(normalized, output_path, output_path.suffix.lower().lstrip(".") or "csv")
    return len(normalized), len(normalized)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        route = "/index.html" if self.path == "/" else self.path
        file_path = WEB_DIR / route.lstrip("/")
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = "text/html" if file_path.suffix == ".html" else "text/css" if file_path.suffix == ".css" else "application/javascript"
        data = file_path.read_bytes()
        if file_path.name == "index.html":
            data = data.replace(b"__DEFAULT_MAPPING__", json.dumps(DEFAULT_MAPPING, ensure_ascii=False, indent=2).encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        if self.path == "/api/import":
            payload = json.loads(body.decode("utf-8"))
            name = payload["filename"]
            file_bytes = base64.b64decode(payload["content_base64"])
            ext = Path(name).suffix.lower().lstrip(".")
            mapping = mapping_from_dict(payload.get("mapping") or DEFAULT_MAPPING)
            source_name = payload.get("source_name", "unknown")
            if ext == "csv":
                rows = _rows_from_csv_text(file_bytes.decode("utf-8"))
            elif ext in {"xlsx", "exl"}:
                rows = _rows_from_xlsx_bytes(file_bytes)
            elif ext == "json":
                p = json.loads(file_bytes.decode("utf-8"))
                rows = p.get("readings", []) if isinstance(p, dict) else p
            else:
                self._send_json({"error": "Extension non supportée"}, 400)
                return
            try:
                normalized = normalize_rows(rows, mapping, source_name)
            except Exception as exc:
                self._send_json({"error": str(exc)}, 400)
                return
            self._send_json({"rows": normalized, "count": len(normalized)})
            return

        if self.path == "/api/export":
            payload = json.loads(body.decode("utf-8"))
            rows = payload.get("rows", [])
            fmt = payload.get("format", "csv")
            data = _write_csv_bytes(rows) if fmt == "csv" else _write_xlsx_bytes(rows)
            b64 = base64.b64encode(data).decode("ascii")
            filename = "universal_readings.csv" if fmt == "csv" else "universal_readings.xlsx"
            self._send_json({"filename": filename, "content_base64": b64})
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Importation Releve Compteur Universelle")
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--format", choices=["csv", "json", "xlsx", "exl"])
    p.add_argument("--mapping", type=Path)
    p.add_argument("--source-name", default="unknown")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.serve:
        ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
        return
    if not all([args.input, args.output, args.format, args.mapping]):
        raise SystemExit("CLI requires --input --output --format --mapping")
    total, imported = run(args.input, args.output, args.format, args.mapping, args.source_name)
    print(f"Import termine: {imported}/{total} releves")


if __name__ == "__main__":
    main()
