from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedRow:
    # E4a: linha pode ter só telefone, só e-mail ou os dois (nunca nenhum).
    wa_id: Optional[str]
    name: Optional[str]
    custom_vars: dict
    raw_index: int
    email: Optional[str] = None


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


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(raw: str) -> Optional[str]:
    v = (raw or "").strip().lower()
    if not v or len(v) > 255 or not _EMAIL_RE.match(v):
        return None
    return v


def _detect_email_column(header: list[str]) -> Optional[str]:
    candidates = ["email", "e-mail", "mail", "correio"]
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
    email_col = _detect_email_column(header)

    rows: list[ParsedRow] = []
    errors: list[dict] = []
    total = 0

    if not phone_col and not email_col:
        return ParseResult(
            rows=[],
            errors=[{"line": 0, "reason": "coluna de telefone ou e-mail não encontrada (esperado: telefone, celular, whatsapp, phone, wa_id, email, e-mail)"}],
            detected_columns=header,
            total_lines=0,
        )

    for idx, raw_row in enumerate(reader, start=2):
        total += 1
        if total > max_rows:
            errors.append({"line": idx, "reason": f"limite de {max_rows} linhas excedido — arquivo truncado"})
            break

        phone_raw = (raw_row.get(phone_col) or "") if phone_col else ""
        email_raw = (raw_row.get(email_col) or "") if email_col else ""
        wa_id = _normalize_phone(phone_raw)
        email = _normalize_email(email_raw)
        if not wa_id and not email:
            if phone_col and email_col:
                reason = f"telefone e e-mail inválidos: '{phone_raw}' / '{email_raw}'"
            elif phone_col:
                reason = f"telefone inválido: '{phone_raw}'"
            else:
                reason = f"e-mail inválido: '{email_raw}'"
            errors.append({"line": idx, "reason": reason})
            continue

        name = (raw_row.get(name_col) or "").strip() if name_col else None
        custom = {
            k: v for k, v in raw_row.items()
            if k not in (phone_col, name_col, email_col) and (v or "").strip()
        }
        rows.append(ParsedRow(wa_id=wa_id, name=name or None, custom_vars=custom, raw_index=idx, email=email))

    return ParseResult(
        rows=rows,
        errors=errors,
        detected_columns=header,
        total_lines=total,
    )
