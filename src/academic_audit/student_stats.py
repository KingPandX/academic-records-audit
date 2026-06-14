from __future__ import annotations

from collections import defaultdict
from typing import Any

from academic_audit.database import Database

SEMESTER_LABELS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
MAX_SEMESTER = len(SEMESTER_LABELS)


def get_student_info(db: Database, identity_document: str) -> dict[str, Any] | None:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.student_id, s.identity_document, s.full_name, s.program,
                   s.academic_index, s.periods_completed, s.study_plan_period
            FROM students s
            WHERE s.identity_document = ?
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (identity_document,),
        ).fetchone()
        return dict(row) if row else None


def get_enrolled_subjects(
    db: Database, identity_document: str, current_period: str
) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT es.code, es.name
            FROM enrollments e
            JOIN enrollment_subjects es ON es.enrollment_id = e.id
            WHERE e.identity_document = ? AND e.period = ?
            ORDER BY es.row_order
            """,
            (identity_document, current_period),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_courses(
    db: Database, identity_document: str,
) -> list[dict[str, Any]]:
    with db.connect() as conn:
        latest = conn.execute(
            """
            SELECT period FROM courses
            WHERE identity_document = ? AND period IS NOT NULL
            ORDER BY
                CAST(SUBSTR(period, INSTR(period, '-') + 1) AS INTEGER) DESC,
                CAST(SUBSTR(period, 1, INSTR(period, '-') - 1) AS INTEGER) DESC
            LIMIT 1
            """,
            (identity_document,),
        ).fetchone()
        if not latest:
            return []
        rows = conn.execute(
            """
            SELECT code, name, semester
            FROM courses
            WHERE identity_document = ? AND period = ?
            ORDER BY row_order
            """,
            (identity_document, latest["period"]),
        ).fetchall()
        return [dict(r) for r in rows]


def _map_subject_to_semester(
    code: str, code_to_semester: dict[str, int]
) -> int | None:
    code = code.strip().upper()
    if not code:
        return None

    if code.startswith("CINU") or "CINU" in code:
        return 0

    if code in code_to_semester:
        return code_to_semester[code]

    for plan_code, sem in code_to_semester.items():
        if code.startswith(plan_code) or plan_code.startswith(code):
            return sem

    return None


def _check_repeated_failed(
    db: Database, identity_document: str, enrolled_subjects: list[dict[str, Any]]
) -> bool:
    from academic_audit.eligibility import _is_failed

    enrolled_codes = {
        s.get("code", "").strip().upper()
        for s in enrolled_subjects if s.get("code")
    }
    if not enrolled_codes:
        return False

    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT code, grade, observation FROM courses
            WHERE identity_document = ?
            """,
            (identity_document,),
        ).fetchall()

    for row in rows:
        code = (row["code"] or "").strip().upper()
        if code in enrolled_codes:
            course = {"grade": row["grade"] or "", "observation": row["observation"] or ""}
            if _is_failed(course):
                return True
    return False


def classify_student(
    db: Database, identity_document: str, current_period: str
) -> dict[str, Any] | None:
    student = get_student_info(db, identity_document)
    if not student:
        return None

    program = student.get("program", "")
    expected_semester = (
        student.get("study_plan_period")
        or student.get("periods_completed", 0)
        or 0
    )

    subjects = get_enrolled_subjects(db, identity_document, current_period)
    if not subjects:
        subjects = get_latest_courses(db, identity_document)
    if not subjects:
        return {
            "identity_document": identity_document,
            "full_name": student.get("full_name", ""),
            "program": program,
            "expected_semester": expected_semester,
            "effective_semester": 0,
            "clasificacion": "sin_datos",
        }

    plan_subjects = db.get_plan_subjects(program)
    code_to_semester: dict[str, int] = {}
    for s in plan_subjects:
        sem = s.get("semester")
        if sem is not None:
            try:
                code_to_semester[s["code"]] = int(sem)
            except (ValueError, TypeError):
                pass

    subject_semesters: list[int] = []
    for subj in subjects:
        code = subj.get("code", "")
        sem = _map_subject_to_semester(code, code_to_semester)
        if sem is not None:
            subject_semesters.append(sem)

    if not subject_semesters:
        return {
            "identity_document": identity_document,
            "full_name": student.get("full_name", ""),
            "program": program,
            "expected_semester": expected_semester,
            "effective_semester": 0,
            "clasificacion": "sin_datos",
        }

    effective_semester = max(subject_semesters)

    if effective_semester < expected_semester:
        clasificacion = "desfasado"
    elif _check_repeated_failed(db, identity_document, subjects):
        clasificacion = "repitiente"
    else:
        clasificacion = "regular"

    return {
        "identity_document": identity_document,
        "full_name": student.get("full_name", ""),
        "program": program,
        "expected_semester": expected_semester,
        "effective_semester": effective_semester,
        "clasificacion": clasificacion,
    }


def compute_stats_pivot(
    db: Database, current_period: str
) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT identity_document FROM students WHERE identity_document IS NOT NULL"
        ).fetchall()
    identities = [r["identity_document"] for r in rows]

    results: list[dict[str, Any]] = []
    for id_doc in identities:
        result = classify_student(db, id_doc, current_period)
        if result and result.get("clasificacion") not in ("sin_datos",):
            results.append(result)

    pivot: dict[tuple[str, str], list[int]] = defaultdict(
        lambda: [0] * MAX_SEMESTER
    )

    for r in results:
        key = (r["program"], r["clasificacion"])
        sem = r["effective_semester"]
        idx = sem - 1 if sem > 0 else 0
        if 0 <= idx < MAX_SEMESTER:
            pivot[key][idx] += 1

    output: list[dict[str, Any]] = []
    programs = sorted({k[0] for k in pivot})

    for prog in programs:
        for tipo in ("regular", "repitiente", "desfasado"):
            key = (prog, tipo)
            counts = pivot.get(key, [0] * MAX_SEMESTER)
            row: dict[str, Any] = {
                "Carrera": prog,
                "Tipo": tipo.capitalize(),
            }
            for i, label in enumerate(SEMESTER_LABELS):
                row[label] = counts[i]
            output.append(row)

    return output
