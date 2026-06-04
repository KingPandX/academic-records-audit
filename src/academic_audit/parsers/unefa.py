from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_RE_SKIP = re.compile(
    r"^(?:rep[uú]blica|ministerio|viceministerio|universidad|polit[eé]cnica|"
    r"u\.n\.e\.f\.a|record acad[eé]mico|per[ií]odo\s+sem|p[aá]gina\s+\d|"
    r"total\s+asignaturas|total\s+u\.c\.|totales\s+u\.c\.|observaciones:|"
    r"leyenda:|revisado|firma|nota:|jefe de|decano|va sin enmiendas|"
    r"^-{3,}$|^\|[-\s:|]+\|$)",
    re.IGNORECASE,
)
_RE_INDEX_ROW = re.compile(
    r"[ií]ndice\s+acad[eé]mico",
    re.IGNORECASE,
)
_RE_INDEX_VALUES = re.compile(
    r"(\d+)\s+(\d+)\s+IA\s+([\d.,]+)",
    re.IGNORECASE,
)
_RE_APELLIDOS = re.compile(
    r"Apellidos:\s*(.+?)\s+Matricula:\s*([\d\-]+)",
    re.IGNORECASE,
)
_RE_NOMBRES = re.compile(
    r"Nombres:\s*(.+?)\s+Per[ií]odo Acad[eé]mico seg[uú]n Plan de Estudio:\s*(\d+)",
    re.IGNORECASE,
)
_RE_DOCUMENTO = re.compile(
    r"Documento de Identidad:\s*([A-Z]?-?\d+)\s+"
    r"Per[ií]odo Acad[eé]mico Cursados:\s*(\d+)",
    re.IGNORECASE,
)
_RE_CARRERA = re.compile(r"Carrera:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_NUCLEO = re.compile(r"N[UÚ]CLEO:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_INDICE_FINAL = re.compile(
    r"[ÍI]ndice acad[eé]mico:\s*([\d.,]+)",
    re.IGNORECASE,
)
_RE_FECHA = re.compile(r"Fecha de emisi[oó]n:\s*([\d\-/]+)", re.IGNORECASE)
_RE_TOTAL_CURSADAS = re.compile(
    r"Total asignaturas cursadas:\s*(\d+)", re.IGNORECASE
)
_RE_TOTAL_APROBADAS = re.compile(
    r"Total asignaturas aprobadas:\s*(\d+)", re.IGNORECASE
)
_RE_UC_CURSADAS = re.compile(r"Total u\.c\. cursadas:\s*(\d+)", re.IGNORECASE)
_RE_UC_APROBADAS = re.compile(
    r"Total u\.c\. aprobadas:\s*(\d+)(?:\s+Total|$)", re.IGNORECASE
)
_RE_UC_SIN_EQUIV = re.compile(
    r"Total u\.c\. aprobadas sin equivalencias, acreditaci[oó]n:\s*(\d+)",
    re.IGNORECASE,
)
_RE_CINU = re.compile(
    r"^(\d-\d{4})\s+(CINU\d{4})\s+(.+?)\s+(APROB[OÓ]|REPROB[OÓ])\s*$",
    re.IGNORECASE,
)
_RE_COURSE_START = re.compile(
    r"^(\d-\d{4})\s+(\d{2})\s+((?:[A-Z]{2,4}-\d{2,5})|(?:CINU\d{4}))\s+",
    re.IGNORECASE,
)
_RE_NUMERIC_TAIL = re.compile(
    r"^(.+?)\s+(\d{2})\s+(\d+)\s+(\d+)\s*(REPITI[OÓ]|REPROB[OÓ]|APROB[OÓ])?\s*$",
    re.IGNORECASE,
)
_RE_STATUS_TAIL = re.compile(
    r"^(.+?)\s+(APROB[OÓ]|REPROB[OÓ])\s*$",
    re.IGNORECASE,
)
_RE_STATUS_ONLY = re.compile(r"^(APROB[OÓ]|REPROB[OÓ])\s*$", re.IGNORECASE)


@dataclass
class ParsedTranscript:
    student: dict[str, Any] = field(default_factory=dict)
    courses: list[dict[str, Any]] = field(default_factory=list)
    extra_fields: dict[str, str] = field(default_factory=dict)
    index_snapshots: list[dict[str, Any]] = field(default_factory=list)


class UnefaTranscriptParser:
    """Parser para records académicos UNEFA (formato estándar de referencia)."""

    def parse(self, markdown: str) -> ParsedTranscript:
        text = markdown.replace("\r\n", "\n")
        student, extra = self._extract_student(text)
        index_snapshots = self._extract_index_snapshots(text)
        courses = self._extract_courses(text)
        return ParsedTranscript(
            student=student,
            courses=courses,
            extra_fields=extra,
            index_snapshots=index_snapshots,
        )

    def _extract_student(self, text: str) -> tuple[dict[str, Any], dict[str, str]]:
        student: dict[str, Any] = {}
        extra: dict[str, str] = {}

        if m := _RE_APELLIDOS.search(text):
            student["surnames"] = m.group(1).strip()
            student["student_id"] = m.group(2).strip()

        if m := _RE_NOMBRES.search(text):
            student["given_names"] = m.group(1).strip()
            student["study_plan_period"] = int(m.group(2))

        if m := _RE_DOCUMENTO.search(text):
            student["identity_document"] = m.group(1).strip()
            student["periods_completed"] = int(m.group(2))

        if m := _RE_CARRERA.search(text):
            student["program"] = m.group(1).strip()

        if m := _RE_NUCLEO.search(text):
            student["nucleus"] = m.group(1).strip()

        if m := _RE_INDICE_FINAL.search(text):
            student["academic_index"] = _to_float(m.group(1))

        if m := _RE_FECHA.search(text):
            student["issue_date"] = m.group(1).strip()

        if student.get("surnames") and student.get("given_names"):
            student["full_name"] = (
                f"{student['surnames']}, {student['given_names']}"
            )

        if m := _RE_TOTAL_CURSADAS.search(text):
            extra["total_courses_taken"] = m.group(1)
        if m := _RE_TOTAL_APROBADAS.search(text):
            extra["total_courses_passed"] = m.group(1)
        if m := _RE_UC_CURSADAS.search(text):
            extra["total_uc_taken"] = m.group(1)
        if m := _RE_UC_APROBADAS.search(text):
            extra["total_uc_passed"] = m.group(1)
        if m := _RE_UC_SIN_EQUIV.search(text):
            extra["total_uc_passed_no_equivalency"] = m.group(1)

        return student, extra

    def _extract_index_snapshots(self, text: str) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = _normalize_line(raw_line)
            if not line or not _RE_INDEX_ROW.search(line):
                continue
            m = _RE_INDEX_VALUES.search(line)
            if not m:
                continue
            snapshots.append(
                {
                    "uc_cumulative": int(m.group(1)),
                    "points_cumulative": int(m.group(2)),
                    "index_value": _to_float(m.group(3)),
                    "source_line": raw_line.strip(),
                }
            )
        return snapshots

    def _extract_courses(self, text: str) -> list[dict[str, Any]]:
        courses: list[dict[str, Any]] = []
        lines = [_normalize_line(ln) for ln in text.splitlines()]
        i = 0

        while i < len(lines):
            line = lines[i]
            if not line or _should_skip(line):
                i += 1
                continue

            if _RE_INDEX_ROW.search(line):
                i += 1
                continue

            course = self._parse_cinu(line)
            if course:
                courses.append(course)
                i += 1
                continue

            course, consumed = self._parse_course_line(line, lines, i)
            if course:
                courses.append(course)
            i += consumed

        return courses

    def _parse_cinu(self, line: str) -> dict[str, Any] | None:
        m = _RE_CINU.match(line)
        if not m:
            return None
        period, code, name, status = m.groups()
        return {
            "period": period,
            "semester": None,
            "code": code.upper(),
            "name": name.strip(),
            "grade": status.upper(),
            "credits": None,
            "points": None,
            "observation": status.upper(),
            "course_type": "cinu",
            "source_line": line,
        }

    def _parse_course_line(
        self, line: str, lines: list[str], index: int
    ) -> tuple[dict[str, Any] | None, int]:
        m = _RE_COURSE_START.match(line)
        if not m:
            return None, 1

        period, semester, code = m.groups()
        remainder = line[m.end() :].strip()
        observation: str | None = None

        if not remainder and index + 1 < len(lines):
            nxt = lines[index + 1]
            if _RE_STATUS_ONLY.match(nxt):
                remainder = ""
                grade_line = nxt
                return self._build_course(
                    period,
                    semester,
                    code,
                    _infer_name_from_code(code),
                    grade_line.upper(),
                    None,
                    None,
                    grade_line.upper(),
                    lines[index],
                ), 2

        if not remainder:
            return None, 1

        grade: str | None = None
        credits: int | None = None
        points: int | None = None
        name = remainder

        tail = _RE_NUMERIC_TAIL.match(remainder)
        if tail:
            name, grade, credits_s, points_s, obs = tail.groups()
            credits = int(credits_s)
            points = int(points_s)
            observation = obs.upper() if obs else None
        else:
            status_tail = _RE_STATUS_TAIL.match(remainder)
            if status_tail:
                name, grade = status_tail.groups()
                grade = grade.upper()
                observation = grade
            elif index + 1 < len(lines) and _RE_STATUS_ONLY.match(lines[index + 1]):
                grade = lines[index + 1].upper()
                observation = grade
                return self._build_course(
                    period,
                    semester,
                    code,
                    name.strip(),
                    grade,
                    None,
                    None,
                    observation,
                    lines[index],
                ), 2

        return self._build_course(
            period,
            semester,
            code,
            name.strip(),
            grade,
            credits,
            points,
            observation,
            line,
        ), 1

    def _build_course(
        self,
        period: str,
        semester: str,
        code: str,
        name: str,
        grade: str | None,
        credits: int | None,
        points: int | None,
        observation: str | None,
        source_line: str,
    ) -> dict[str, Any]:
        year = period.split("-", 1)[-1] if "-" in period else None
        return {
            "period": period,
            "semester": semester,
            "year": year,
            "code": code.upper(),
            "name": name,
            "grade": grade,
            "credits": credits,
            "points": points,
            "observation": observation,
            "course_type": "regular",
            "source_line": source_line,
        }


def parse_unefa_transcript(markdown: str) -> ParsedTranscript:
    return UnefaTranscriptParser().parse(markdown)


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""

    if stripped.startswith("|"):
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        cells = [
            c
            for c in cells
            if c and not re.fullmatch(r"[-:]+", c.replace(" ", ""))
        ]
        stripped = " ".join(cells)

    return re.sub(r"\s+", " ", stripped).strip()


def _should_skip(line: str) -> bool:
    if _RE_SKIP.search(line):
        return True
    if re.match(r"^Apellidos:", line, re.IGNORECASE):
        return True
    if re.match(r"^Nombres:", line, re.IGNORECASE):
        return True
    if re.match(r"^Documento de Identidad:", line, re.IGNORECASE):
        return True
    if re.match(r"^Carrera:", line, re.IGNORECASE):
        return True
    if re.match(r"^Dr\.\s*\(a\)", line, re.IGNORECASE):
        return True
    return False


def _to_float(value: str) -> float:
    return float(value.replace(",", "."))


def _infer_name_from_code(code: str) -> str:
    return code
