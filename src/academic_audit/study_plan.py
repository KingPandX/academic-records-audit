from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import xlrd


def _clean_code(code: str) -> str:
    code = re.sub(r"\s+", "", code.strip()).upper()
    code = re.sub(r"^CO-", "", code)
    return code


def _is_valid_code(code: str) -> bool:
    return bool(re.match(r"^[A-Z0-9]{2,}-?\d{2,}[A-Z0-9]?$", code))


def _parse_prerequisites(raw: str) -> list[str]:
    if not raw or raw.strip() in ("-", "", "0"):
        return []
    raw = raw.strip().upper()
    parts = re.split(r"[,;\s/]+", raw)
    cleaned: list[str] = []
    for p in parts:
        p = _clean_code(p)
        if p and _is_valid_code(p):
            cleaned.append(p)
    return cleaned


TEG_KEYWORDS = [
    "TRABAJO ESPECIAL DE GRADO", "TRABAJO ESPECIAL", "TESIS",
    "TRABAJO DE GRADO",
]
PASANTIA_KEYWORDS = [
    "PASANTÍA", "PASANTIA", "PASANTÍAS", "PASANTIAS",
    "PASANTÍA PROFESIONAL", "PASANTIA PROFESIONAL",
    "PRÁCTICA PROFESIONAL", "PRACTICA PROFESIONAL",
]


def _determine_subject_type(subject_name: str) -> str:
    name = subject_name.upper().strip()
    for kw in TEG_KEYWORDS:
        if kw in name:
            return "teg"
    for kw in PASANTIA_KEYWORDS:
        if kw in name:
            return "practica"
    return "obligatoria"


def _extract_program(row3: list[str]) -> str:
    for cell in row3:
        if cell and ("INGENIER" in cell.upper() or "LICENCIATURA" in cell.upper() or "TSU" in cell.upper()):
            return cell.strip()
    return ""


_SHEET_PRIORITY = {
    "pas": 0, "pasantia": 0, "pasántia": 0,
    "teg": 1,
    "npas": 2, "n pas": 2,
    "nteg": 3, "n teg": 3,
}


def _sheet_priority(sheet_name: str) -> int:
    name = sheet_name.lower().strip()
    for key, pri in _SHEET_PRIORITY.items():
        if key in name:
            return pri
    return 99


def parse_xls(path: Path) -> list[dict[str, Any]]:
    wb = xlrd.open_workbook(str(path))
    programs_map: dict[str, list[dict[str, Any]]] = {}

    for sheet_name in wb.sheet_names():
        ws = wb.sheet_by_name(sheet_name)
        if ws.nrows < 6:
            continue

        row3 = [str(ws.cell_value(2, c)).strip() for c in range(ws.ncols)]
        program = _extract_program(row3)
        if not program:
            continue

        entry = {
            "program": program,
            "sheet_name": sheet_name,
            "subjects": [],
            "prerequisites": [],
        }
        current_semester = ""

        for r in range(5, ws.nrows):
            sem_cell = str(ws.cell_value(r, 1)).strip()
            code_cell = str(ws.cell_value(r, 2)).strip()
            name_cell = str(ws.cell_value(r, 3)).strip()
            credits_cell = str(ws.cell_value(r, 7)).strip()

            if not code_cell or not name_cell:
                continue

            if sem_cell and sem_cell not in ("", "SEMESTRE", "SEMESTRE "):
                current_semester = sem_cell.replace("º", "").strip()

            code = _clean_code(code_cell)
            if not code or not _is_valid_code(code):
                continue

            name = name_cell.upper().strip()
            try:
                credits = int(float(credits_cell)) if credits_cell else None
            except (ValueError, TypeError):
                credits = None

            subject_type = _determine_subject_type(name)

            entry["subjects"].append(
                {
                    "code": code,
                    "name": name,
                    "credits": credits,
                    "semester": current_semester,
                    "program": program,
                    "subject_type": subject_type,
                }
            )

            prereq_raw = str(ws.cell_value(r, 8)).strip()
            prereq_codes = _parse_prerequisites(prereq_raw)
            for prereq in prereq_codes:
                entry["prerequisites"].append(
                    {
                        "subject_code": code,
                        "prereq_code": prereq,
                        "program": program,
                    }
                )

        if entry["subjects"]:
            programs_map.setdefault(program, []).append(entry)

    result: list[dict[str, Any]] = []
    for program, entries in programs_map.items():
        entries.sort(key=lambda e: _sheet_priority(e["sheet_name"]))

        canonical = entries[0]
        seen_codes: set[str] = set()
        merged_subjects: list[dict[str, Any]] = []
        merged_prereqs: list[dict[str, str]] = []

        for entry in entries:
            for subj in entry["subjects"]:
                if subj["code"] not in seen_codes:
                    seen_codes.add(subj["code"])
                    merged_subjects.append(subj)

            seen_prereq: set[tuple[str, str]] = set()
            for pr in entry["prerequisites"]:
                key = (pr["subject_code"], pr["prereq_code"])
                if key not in seen_prereq:
                    seen_prereq.add(key)
                    merged_prereqs.append(pr)

        result.append(
            {
                "program": program,
                "canonical_sheet": canonical["sheet_name"],
                "subjects": merged_subjects,
                "prerequisites": merged_prereqs,
            }
        )

    return result
