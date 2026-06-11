from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_NORMALIZE_ACCENTS = str.maketrans(
    "áéíóúüñÁÉÍÓÚÜÑ",
    "aeiouunAEIOUUN",
)


def _normalize(text: str) -> str:
    return text.translate(_NORMALIZE_ACCENTS).lower().strip()


_COLUMN_MAP: dict[str, str] = {
    "codigo": "code",
    "asignatura": "name",
    "seccion": "section",
    "docente": "teacher",
    "profesor": "teacher",
}


@dataclass
class ParsedEnrollment:
    identity_document: str | None = None
    full_name: str | None = None
    period: str | None = None
    program: str | None = None
    subjects: list[dict[str, Any]] = field(default_factory=list)


def _is_separator(parts: list[str]) -> bool:
    return all(re.fullmatch(r"-+", p) for p in parts if p)


def parse_enrollment(text: str) -> ParsedEnrollment:
    result = ParsedEnrollment()

    lines = text.splitlines()

    result.full_name = _extract_field(
        lines,
        r"(?:estudiante|alumno)\s*[:\-]?\s*([^|]+)",
        re.IGNORECASE,
    )
    result.identity_document = _extract_identity(lines)
    result.period = _extract_field(
        lines,
        r"(?<![a-z])(?:per[ií]odo?|semestre|lapso|trimestre)\s*(?:academico?)?\s*[:\-]?\s*([\d\-/]+)",
        re.IGNORECASE,
    )
    result.program = _extract_field(
        lines,
        r"(?:carrera|programa|plan\s+de\s+estudios)\s*[:\-]\s*(.+)",
        re.IGNORECASE,
    )

    tables = _extract_tables(lines)
    if tables:
        result.subjects = tables[0]

    if not result.subjects:
        result.subjects = _extract_subject_lines(lines)

    return result


def _extract_identity(lines: list[str]) -> str | None:
    val = _extract_field(
        lines,
        r"(?:c[eé]dula)\s*\(?\s*[a-z]?\s*\)?\s*[:\-]?\s*([a-z0-9\-]+)",
        re.IGNORECASE,
    )
    if val:
        val = val.strip()
        if not val.startswith("V-"):
            val = "V-" + val
        return val

    val = _extract_field(
        lines,
        r"(?:documento\s+(?:de\s+)?identidad)\s*[:\-]?\s*([a-z0-9\-]+)",
        re.IGNORECASE,
    )
    return val


def _extract_field(lines: list[str], pattern: str, flags: int = 0) -> str | None:
    compiled = re.compile(pattern, flags)
    for line in lines:
        m = compiled.search(line)
        if m:
            val = m.group(1).strip()
            if val:
                return val
    return None


_SECTION_PATTERN = re.compile(
    r"\d{2,3}[A-Z]?-\d{4,5}-[A-Z]\d"
)


def _extract_subject_lines(lines: list[str]) -> list[dict[str, Any]]:
    in_subjects = False
    subjects: list[dict[str, Any]] = []

    for line in lines:
        stripped = line.strip()

        if re.search(r"cod\s*-?\s*asig.*asignaturas", stripped, re.IGNORECASE):
            in_subjects = True
            continue

        if re.search(r"horario\s+de\s+clases", stripped, re.IGNORECASE):
            in_subjects = False
            break

        if not in_subjects:
            continue

        m = re.match(
            r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(.+)$",
            stripped,
        )
        if not m:
            continue

        _, first_token, code, rest = m.groups()

        section_m = _SECTION_PATTERN.search(rest)
        if section_m:
            name = rest[: section_m.start()].strip()
            section = section_m.group()
            teacher = rest[section_m.end() :].strip()
        else:
            name = rest
            section = None
            teacher = None

        subjects.append({
            "code": code,
            "name": name,
            "section": section,
            "teacher": teacher,
        })

    return subjects


def _extract_tables(lines: list[str]) -> list[list[dict[str, Any]]]:
    tables: list[list[str]] = []
    current: list[str] | None = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            parts = [p.strip() for p in stripped.split("|")]
            parts = [p for p in parts if p]

            if _is_separator(parts):
                continue

            if len(parts) > 1:
                if current is None:
                    current = []
                current.append(parts)
            else:
                if current is not None:
                    tables.append(current)
                    current = None
        else:
            if current is not None:
                tables.append(current)
                current = None

    if current is not None:
        tables.append(current)

    result: list[list[dict[str, Any]]] = []
    for table in tables:
        if len(table) < 2:
            continue
        header = [_normalize(h) for h in table[0]]
        col_map: dict[int, str] = {}
        for i, col_name in enumerate(header):
            mapped = _COLUMN_MAP.get(col_name)
            if mapped:
                col_map[i] = mapped

        if not col_map:
            continue

        rows: list[dict[str, Any]] = []
        for data_row in table[1:]:
            row: dict[str, Any] = {}
            for i, value in enumerate(data_row):
                if i in col_map:
                    row[col_map[i]] = value
            if row:
                rows.append(row)
        result.append(rows)

    return result
