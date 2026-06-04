from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from academic_audit.config import ExtractorConfig, FieldPattern

_RE_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_RE_TABLE_SEP = re.compile(r"^\|[\s\-:|]+\|$")


@dataclass
class ParsedTranscript:
    student: dict[str, Any] = field(default_factory=dict)
    courses: list[dict[str, Any]] = field(default_factory=list)
    extra_fields: dict[str, str] = field(default_factory=dict)
    index_snapshots: list[dict[str, Any]] = field(default_factory=list)


class TranscriptParser:
    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self.config = config or ExtractorConfig()
        self._course_code = re.compile(
            self.config.course_code_pattern, re.IGNORECASE
        )
        self._grade = re.compile(self.config.grade_pattern, re.IGNORECASE)

    def parse(self, markdown: str) -> ParsedTranscript:
        text = markdown.replace("\r\n", "\n")
        student, extra = self._extract_student_fields(text)
        table_courses = self._extract_from_tables(text)
        line_courses = self._extract_from_lines(text)
        courses = _merge_courses(table_courses, line_courses)
        return ParsedTranscript(student=student, courses=courses, extra_fields=extra)

    def _extract_student_fields(self, text: str) -> tuple[dict[str, Any], dict[str, str]]:
        student: dict[str, Any] = {}
        extra: dict[str, str] = {}
        lines = text.splitlines()

        for fp in self.config.student_fields:
            compiled = re.compile(fp.pattern, fp.flags)
            for line in lines:
                match = compiled.search(line.strip())
                if not match:
                    continue
                value = match.group(1).strip()
                if fp.key == "gpa":
                    value = value.replace(",", ".")
                    try:
                        student[fp.key] = float(value)
                    except ValueError:
                        extra[fp.key] = value
                elif fp.key in student and student[fp.key]:
                    extra[fp.key] = value
                else:
                    student[fp.key] = value
                break

        return student, extra

    def _extract_from_tables(self, text: str) -> list[dict[str, Any]]:
        courses: list[dict[str, Any]] = []
        lines = text.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not _RE_TABLE_ROW.match(line):
                i += 1
                continue

            header_cells = _split_table_row(line)
            i += 1
            if i < len(lines) and _RE_TABLE_SEP.match(lines[i].strip()):
                i += 1

            col_map = _map_columns(header_cells)
            if not col_map:
                i += 1
                continue

            while i < len(lines) and _RE_TABLE_ROW.match(lines[i].strip()):
                row_cells = _split_table_row(lines[i].strip())
                course = _row_to_course(row_cells, col_map, self._course_code, self._grade)
                if course:
                    courses.append(course)
                i += 1

        return courses

    def _extract_from_lines(self, text: str) -> list[dict[str, Any]]:
        courses: list[dict[str, Any]] = []
        period_re = re.compile(
            r"(?:semestre|periodo|período)\s*[:\-]?\s*(\d{4}[\-\s]?[12]?|[12]\s*/\s*\d{4})",
            re.IGNORECASE,
        )

        current_period: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or _RE_TABLE_ROW.match(line):
                continue

            period_match = period_re.search(line)
            if period_match:
                current_period["period"] = period_match.group(1).strip()
                year_match = re.search(r"(\d{4})", current_period["period"])
                if year_match:
                    current_period["year"] = year_match.group(1)
                continue

            course = _parse_course_line(line, self._course_code, self._grade)
            if course:
                course.update(current_period)
                course["source_line"] = line
                courses.append(course)

        return courses


def parse_transcript(markdown: str, config: ExtractorConfig | None = None) -> ParsedTranscript:
    """Usa el parser UNEFA por defecto (formato estándar de la universidad)."""
    if config is not None:
        return TranscriptParser(config).parse(markdown)

    from academic_audit.parsers.unefa import parse_unefa_transcript

    result = parse_unefa_transcript(markdown)
    return ParsedTranscript(
        student=result.student,
        courses=result.courses,
        extra_fields=result.extra_fields,
        index_snapshots=result.index_snapshots,
    )


def _merge_courses(
    primary: list[dict[str, Any]], secondary: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, str | None, str | None]] = set()
    merged: list[dict[str, Any]] = []

    for course in primary + secondary:
        key = (course.get("code"), course.get("name"), course.get("grade"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(course)

    return merged


def _split_table_row(line: str) -> list[str]:
    inner = line.strip().strip("|")
    return [cell.strip() for cell in inner.split("|")]


def _normalize_label(text: str) -> str:
    lowered = text.lower().strip()
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(ch) != "Mn"
    )


def _map_columns(headers: list[str]) -> dict[str, int]:
    normalized = [_normalize_label(h) for h in headers]
    aliases: dict[str, list[str]] = {
        "code": ["codigo", "clave", "code", "sigla"],
        "name": ["asignatura", "materia", "nombre", "curso", "descripcion"],
        "credits": ["creditos", "cr", "credit", "uv", "unidades"],
        "grade": ["calificacion", "nota", "grade", "grado"],
        "semester": ["semestre", "semester"],
        "year": ["año", "ano", "year"],
        "period": ["periodo", "período", "term"],
    }
    col_map: dict[str, int] = {}
    for key, names in aliases.items():
        for idx, header in enumerate(normalized):
            if any(alias in header for alias in names):
                col_map[key] = idx
                break
    return col_map


def _row_to_course(
    cells: list[str],
    col_map: dict[str, int],
    course_code_re: re.Pattern[str],
    grade_re: re.Pattern[str],
) -> dict[str, Any] | None:
    if not cells:
        return None

    def cell(key: str) -> str | None:
        idx = col_map.get(key)
        if idx is None or idx >= len(cells):
            return None
        return cells[idx] or None

    if col_map:
        code = cell("code")
        name = cell("name")
        credits_raw = cell("credits")
        grade = cell("grade")
        if not code and not name:
            return None
        course: dict[str, Any] = {
            "code": code,
            "name": name,
            "grade": grade,
            "semester": cell("semester"),
            "year": cell("year"),
            "period": cell("period"),
            "source_line": " | ".join(cells),
        }
        if credits_raw:
            try:
                course["credits"] = float(credits_raw.replace(",", "."))
            except ValueError:
                pass
        return course

    return _parse_course_line(" ".join(cells), course_code_re, grade_re)


def _parse_course_line(
    line: str,
    course_code_re: re.Pattern[str],
    grade_re: re.Pattern[str],
) -> dict[str, Any] | None:
    tokens = line.split()
    if len(tokens) < 3:
        return None

    code_idx = None
    for i, token in enumerate(tokens):
        if course_code_re.match(token):
            code_idx = i
            break

    if code_idx is None:
        return None

    code = tokens[code_idx]
    grade = tokens[-1] if grade_re.match(tokens[-1]) else None
    middle = tokens[code_idx + 1 : -1 if grade else len(tokens)]
    credits = None
    name_parts: list[str] = []

    for part in middle:
        normalized = part.replace(",", ".")
        if re.match(r"^\d+(\.\d+)?$", normalized):
            credits = float(normalized)
        else:
            name_parts.append(part)

    if not name_parts and not credits:
        return None

    return {
        "code": code,
        "name": " ".join(name_parts) if name_parts else None,
        "credits": credits,
        "grade": grade,
        "source_line": line,
    }
