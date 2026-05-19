from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedRow:
    wa_id: str
    name: Optional[str]
    custom_vars: dict
    raw_index: int


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    errors: list[dict]
    detected_columns: list[str]
    total_lines: int


def _normalize_phone(raw: str) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"\D", "", str(raw))
    if not cleaned:
        return None
    if len(cleaned) < 10 or len(cleaned) > 15:
        return None
    if not cleaned.startswith("55") and len(cleaned) in (10, 11):
        cleaned = "55" + cleaned
    return cleaned


def _detect_phone_column(header: list[str]) -> Optional[str]:
    candidates = ["telefone", "celular", "whatsapp", "phone", "wa_id", "numero", "número"]
    for col in header:
        if col.strip().lower() in candidates:
            return col
    return None


def _detect_name_column(header: list[str]) -> Optional[str]:
    candidates = ["nome", "name", "primeiro_nome", "first_name", "contato"]
    for col in header:
        if col.strip().lower() in candidates:
            return col
    return None


def parse_csv_bytes(raw: bytes, max_rows: int = 50000) -> ParseResult:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        class _Default(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = _Default()

    buf = io.StringIO(text)
    reader = csv.DictReader(buf, dialect=dialect)
    header = reader.fieldnames or []
    phone_col = _detect_phone_column(header)
    name_col = _detect_name_column(header)

    rows: list[ParsedRow] = []
    errors: list[dict] = []
    total = 0

    if not phone_col:
        return ParseResult(
            rows=[],
            errors=[{"line": 0, "reason": "coluna de telefone não encontrada (esperado: telefone, celular, whatsapp, phone, wa_id)"}],
            detected_columns=header,
            total_lines=0,
        )

    for idx, raw_row in enumerate(reader, start=2):
        total += 1
        if total > max_rows:
            errors.append({"line": idx, "reason": f"limite de {max_rows} linhas excedido — arquivo truncado"})
            break

        phone_raw = raw_row.get(phone_col) or ""
        wa_id = _normalize_phone(phone_raw)
        if not wa_id:
            errors.append({"line": idx, "reason": f"telefone inválido: '{phone_raw}'"})
            continue

        name = (raw_row.get(name_col) or "").strip() if name_col else None
        custom = {
            k: v for k, v in raw_row.items()
            if k not in (phone_col, name_col) and (v or "").strip()
        }
        rows.append(ParsedRow(wa_id=wa_id, name=name or None, custom_vars=custom, raw_index=idx))

    return ParseResult(
        rows=rows,
        errors=errors,
        detected_columns=header,
        total_lines=total,
    )
