#!/usr/bin/env python3
"""Importation Relevé Compteur Universelle."""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import io
import json
import sys
import threading
import webbrowser
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

UNIVERSAL_FIELDS = ["id_compteur", "id_client", "valeur_releve", "date_releve", "unite", "systeme_source"]
WEB_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "web"
SUPPORTED_IMPORT_EXTENSIONS = {"csv", "tsv", "txt", "json", "xlsx", "exl"}

DEFAULT_MAPPING = {
    "meter_id": "Compteur",
    "customer_id": "Client",
    "reading_value": "Valeur",
    "reading_date": "Date",
    "unit": "Unite",
    "source_system": "Systeme",
    "date_format": "%d/%m/%Y",
}

HEADER_ALIASES = {
    "meter_id": ["Compteur", "meter_id", "id_compteur", "compteur", "meter"],
    "customer_id": ["Client", "customer_id", "id_client", "client", "customer"],
    "reading_value": ["Valeur", "reading_value", "valeur_releve", "value", "consommation"],
    "reading_date": ["Date", "reading_date", "date_releve", "date"],
    "unit": ["Unite", "unit", "unite", "uom"],
    "source_system": ["Systeme", "source_system", "systeme_source", "source"],
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


def infer_mapping_from_headers(headers: Iterable[str]) -> Mapping:
    normalized = {h.strip().lower(): h for h in headers if h and str(h).strip()}

    def pick(key: str) -> str:
        for alias in HEADER_ALIASES[key]:
            hit = normalized.get(alias.lower())
            if hit:
                return hit
        return ""

    inferred = {
        "meter_id": pick("meter_id"),
        "customer_id": pick("customer_id"),
        "reading_value": pick("reading_value"),
        "reading_date": pick("reading_date"),
        "unit": pick("unit"),
        "source_system": pick("source_system"),
        "date_format": "%d/%m/%Y",
    }
    for required in ["meter_id", "customer_id", "reading_value", "reading_date"]:
        if not inferred[required]:
            raise ValidationError(f"Impossible de mapper automatiquement le champ: {required}")
    return mapping_from_dict(inferred)


def load_mapping(path: Path) -> Mapping:
    return mapping_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _rows_from_delimited_text(text: str, delimiter: str | None = None) -> Iterable[dict[str, Any]]:
    if delimiter is None:
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","
    yield from csv.DictReader(io.StringIO(text), delimiter=delimiter)


def _excel_col(index: int) -> str:
    out = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _rows_from_xlsx_bytes(payload: bytes) -> Iterable[dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            for si in root.findall("a:si", ns):
                shared_strings.append("".join(t.text or "" for t in si.findall(".//a:t", ns)))

        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        matrix: list[list[str]] = []

        for row in sheet.findall(".//a:sheetData/a:row", ns):
            cells_by_index: dict[int, str] = {}
            max_index = 0
            for cell in row.findall("a:c", ns):
                ref = cell.attrib.get("r", "A1")
                letters = "".join(ch for ch in ref if ch.isalpha())
                column_idx = 0
                for ch in letters:
                    column_idx = (column_idx * 26) + (ord(ch.upper()) - 64)
                max_index = max(max_index, column_idx)
                cell_type = cell.attrib.get("t")
                value_node = cell.find("a:v", ns)
                value = ""

                if cell_type == "inlineStr":
                    inline_node = cell.find("a:is/a:t", ns)
                    value = "" if inline_node is None else (inline_node.text or "")
                elif value_node is not None:
                    raw = value_node.text or ""
                    if cell_type == "s" and raw.isdigit():
                        idx = int(raw)
                        value = shared_strings[idx] if idx < len(shared_strings) else ""
                    else:
                        value = raw
                cells_by_index[column_idx] = value

            matrix.append([cells_by_index.get(i, "") for i in range(1, max_index + 1)])

    if not matrix:
        return
    headers = [h.strip() for h in matrix[0]]
    for line in matrix[1:]:
        yield {headers[i]: line[i] if i < len(line) else "" for i in range(len(headers))}


def read_rows(path: Path, source_format: str) -> Iterable[dict[str, Any]]:
    if source_format in {"csv", "txt"}:
        yield from _rows_from_delimited_text(path.read_text(encoding="utf-8"))
        return
    if source_format == "tsv":
        yield from _rows_from_delimited_text(path.read_text(encoding="utf-8"), delimiter="\t")
        return
    if source_format == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("readings", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValidationError("Le JSON doit contenir une liste")
        for item in items:
            if not isinstance(item, dict):
                raise ValidationError("Chaque releve JSON doit etre un objet")
            yield item
        return
    if source_format in {"xlsx", "exl"}:
        yield from _rows_from_xlsx_bytes(path.read_bytes())
        return
    raise ValidationError(f"Format source non supporte: {source_format}")


def normalize_row(row: dict[str, Any], mapping: Mapping, default_source: str) -> dict[str, str]:
    def pick(field: str) -> str:
        value = row.get(field) if field else ""
        return "" if value is None else str(value).strip()

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

    parsed_date = None
    for candidate in [mapping.date_format, "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
        try:
            parsed_date = dt.datetime.strptime(raw_date, candidate).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        raise ValidationError(f"reading_date invalide: {raw_date}")

    return {
        "id_compteur": meter_id,
        "id_client": customer_id,
        "valeur_releve": f"{reading_value:.3f}",
        "date_releve": parsed_date.isoformat(),
        "unite": unit,
        "systeme_source": source_system,
    }


def normalize_rows(rows: Iterable[dict[str, Any]], mapping: Mapping, source_name: str) -> list[dict[str, str]]:
    return [normalize_row(row, mapping, source_name) for row in rows]


def _write_csv_bytes(rows: Iterable[dict[str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=UNIVERSAL_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _write_xlsx_bytes(rows: list[dict[str, str]]) -> bytes:
    def xml_cell(ref: str, value: str) -> str:
        escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'

    all_rows = [UNIVERSAL_FIELDS] + [[row[k] for k in UNIVERSAL_FIELDS] for row in rows]
    row_nodes: list[str] = []
    for row_idx, row_values in enumerate(all_rows, start=1):
        cells = "".join(
            xml_cell(f"{_excel_col(col_idx)}{row_idx}", str(value)) for col_idx, value in enumerate(row_values, start=1)
        )
        row_nodes.append(f'<row r="{row_idx}">{cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(row_nodes)}</sheetData></worksheet>"
    )

    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="UniversalReadings" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/styles.xml",
            '<?xml version="1.0"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf xfId="0"/></cellXfs>'
            '</styleSheet>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return result.getvalue()


def write_universal(rows: list[dict[str, str]], output_path: Path, output_format: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "csv":
        output_path.write_bytes(_write_csv_bytes(rows))
        return
    if output_format in {"xlsx", "exl"}:
        output_path.write_bytes(_write_xlsx_bytes(rows))
        return
    raise ValidationError(f"Format sortie non supporte: {output_format}")


def run(input_path: Path, output_path: Path, source_format: str, mapping_path: Path, source_name: str) -> tuple[int, int]:
    mapping = load_mapping(mapping_path)
    normalized = normalize_rows(read_rows(input_path, source_format), mapping, source_name)
    output_format = output_path.suffix.lower().lstrip(".") or "csv"
    write_universal(normalized, output_path, output_format)
    return len(normalized), len(normalized)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        route = "/index.html" if self.path == "/" else self.path
        file_path = WEB_DIR / route.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        mime = {".html": "text/html", ".css": "text/css", ".js": "application/javascript"}.get(
            file_path.suffix, "application/octet-stream"
        )
        data = file_path.read_bytes()
        if file_path.name == "index.html":
            data = data.replace(b"__DEFAULT_MAPPING__", json.dumps(DEFAULT_MAPPING, ensure_ascii=False, indent=2).encode("utf-8"))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/api/import":
            self._handle_import(body)
            return
        if self.path == "/api/export":
            self._handle_export(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_import(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            filename = payload["filename"]
            file_bytes = base64.b64decode(payload["content_base64"])
            source_name = payload.get("source_name", "unknown")
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext not in SUPPORTED_IMPORT_EXTENSIONS:
                raise ValidationError("Extension non supportée")

            if ext in {"csv", "txt"}:
                raw_rows = list(_rows_from_delimited_text(file_bytes.decode("utf-8")))
            elif ext == "tsv":
                raw_rows = list(_rows_from_delimited_text(file_bytes.decode("utf-8"), delimiter="\t"))
            elif ext in {"xlsx", "exl"}:
                raw_rows = list(_rows_from_xlsx_bytes(file_bytes))
            else:
                jpayload = json.loads(file_bytes.decode("utf-8"))
                raw_rows = jpayload.get("readings", []) if isinstance(jpayload, dict) else jpayload

            if not raw_rows:
                raise ValidationError("Aucune ligne détectée dans le fichier")

            supplied_mapping = payload.get("mapping")
            if supplied_mapping and str(supplied_mapping).strip() not in {"", "{}"}:
                mapping = mapping_from_dict(supplied_mapping)
            else:
                mapping = infer_mapping_from_headers(raw_rows[0].keys())

            normalized = normalize_rows(raw_rows, mapping, source_name)
            self._send_json({"rows": normalized, "count": len(normalized), "detected_mapping": mapping.__dict__})
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)

    def _handle_export(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            rows = payload.get("rows", [])
            fmt = str(payload.get("format", "csv")).lower()

            if fmt == "csv":
                data, filename = _write_csv_bytes(rows), "universal_readings.csv"
            elif fmt in {"xlsx", "exl"}:
                data, filename = _write_xlsx_bytes(rows), "universal_readings.xlsx"
            else:
                raise ValidationError("Format export non supporté")

            self._send_json({"filename": filename, "content_base64": base64.b64encode(data).decode("ascii")})
        except Exception as exc:
            self._send_json({"error": str(exc)}, 400)


def start_server(host: str, port: int) -> None:
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def run_desktop(host: str, port: int) -> None:
    url_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{url_host}:{port}"
    thread = threading.Thread(target=start_server, args=(host, port), daemon=True)
    thread.start()
    webbrowser.open(url)
    thread.join()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importation Releve Compteur Universelle")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["csv", "tsv", "txt", "json", "xlsx", "exl"])
    parser.add_argument("--mapping", type=Path)
    parser.add_argument("--source-name", default="unknown")
    parser.add_argument("--serve", action="store_true", help="Run web server")
    parser.add_argument("--desktop", action="store_true", help="Run in desktop mode and auto-open browser")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if len(sys.argv) == 1:
        run_desktop("127.0.0.1", 5000)
        return
    if args.desktop:
        run_desktop(args.host, args.port)
        return
    if args.serve:
        start_server(args.host, args.port)
        return
    if not all([args.input, args.output, args.format, args.mapping]):
        raise SystemExit("CLI requires --input --output --format --mapping")
    total, imported = run(args.input, args.output, args.format, args.mapping, args.source_name)
    print(f"Import termine: {imported}/{total} releves")


if __name__ == "__main__":
    main()
