from __future__ import annotations

from typing import Any

from academic_audit.database import Database


def _is_passed(course: dict[str, Any]) -> bool:
    grade = course.get("grade", "")
    obs = course.get("observation", "")
    try:
        return int(grade) >= 10
    except (ValueError, TypeError):
        return grade.upper() == "APROBÓ" or obs.upper() == "APROBÓ"


def _is_failed(course: dict[str, Any]) -> bool:
    grade = course.get("grade", "")
    obs = course.get("observation", "")
    try:
        return int(grade) < 10
    except (ValueError, TypeError):
        return grade.upper() == "REPROBÓ" or obs.upper() == "REPROBÓ"


def get_student_courses(db: Database, identity_document: str) -> list[dict[str, Any]]:
    """Obtiene todas las materias cursadas por un estudiante desde los transcriptos."""
    with db.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT c.*
                FROM courses c
                JOIN students s ON c.document_id = s.document_id
                WHERE s.identity_document = ?
                """,
                (identity_document,),
            ).fetchall()
        ]


def get_student_info(db: Database, identity_document: str) -> dict[str, Any] | None:
    """Obtiene info del estudiante desde los transcriptos."""
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT s.student_id, s.identity_document, s.full_name, s.program,
                   s.academic_index, s.periods_completed
            FROM students s
            WHERE s.identity_document = ?
            ORDER BY s.id DESC
            LIMIT 1
            """,
            (identity_document,),
        ).fetchone()
        return dict(row) if row else None


def check_article_118a(courses: list[dict[str, Any]]) -> list[str]:
    """Art.118(a): Reprueba 3 veces una misma materia."""
    fail_count: dict[str, int] = {}
    for c in courses:
        if _is_failed(c):
            code = c.get("code", "")
            fail_count[code] = fail_count.get(code, 0) + 1
    violations = []
    for code, count in fail_count.items():
        if count >= 3:
            name = next(
                (c["name"] for c in courses if c["code"] == code),
                code,
            )
            violations.append(f"{name} ({code}): {count} repitencias")
    return violations


def check_article_118b(courses: list[dict[str, Any]]) -> list[str]:
    """Art.118(b): Reprueba >50% de las asignaturas inscritas en un período."""
    by_period: dict[str, list[dict[str, Any]]] = {}
    for c in courses:
        period = c.get("period", "")
        by_period.setdefault(period, []).append(c)

    violations = []
    for period, subjects in by_period.items():
        total = len(subjects)
        failed = sum(1 for s in subjects if _is_failed(s))
        if total > 0 and failed > total / 2:
            violations.append(
                f"Período {period}: {failed}/{total} materias reprobadas ({failed/total*100:.0f}%)"
            )
    return violations


TEG_KEYWORDS = ["TRABAJO ESPECIAL DE GRADO", "TESIS", "TRABAJO DE GRADO"]
PASANTIA_KEYWORDS = ["PASANTÍA", "PASANTIA", "PASANTÍAS", "PASANTIAS",
                     "PRÁCTICA PROFESIONAL", "PRACTICA PROFESIONAL"]


def _is_teg_or_practica(course: dict[str, Any]) -> bool:
    name = (course.get("name") or "").upper()
    for kw in TEG_KEYWORDS:
        if kw in name:
            return True
    for kw in PASANTIA_KEYWORDS:
        if kw in name:
            return True
    return False


def check_article_118c(courses: list[dict[str, Any]]) -> list[str]:
    """Art.118(c): Reprueba TEG o prácticas profesionales 2 períodos."""
    teg_practicas = [c for c in courses if _is_teg_or_practica(c)]
    if not teg_practicas:
        return []

    by_code: dict[str, list[str]] = {}
    for c in teg_practicas:
        if _is_failed(c):
            code = c.get("code", "")
            period = c.get("period", "")
            by_code.setdefault(code, []).append(period)

    violations = []
    for code, periods in by_code.items():
        unique_periods = set(periods)
        if len(unique_periods) >= 2:
            name = next(
                (c["name"] for c in teg_practicas if c["code"] == code),
                code,
            )
            violations.append(
                f"{name} ({code}): reprobada en {len(unique_periods)} períodos"
            )
    return violations


def check_prerequisites(
    subject_code: str,
    subject_name: str,
    student_courses: list[dict[str, Any]],
    prereq_codes: list[str],
) -> str:
    """Verifica si el estudiante cumple las prelaciones de una materia."""
    if not prereq_codes:
        return ""

    passed_codes = {c["code"] for c in student_courses if _is_passed(c)}
    missing: list[str] = []
    for prereq in prereq_codes:
        if prereq not in passed_codes:
            missing.append(prereq)

    if missing:
        return f"Faltan: {', '.join(missing)}"
    return ""


def check_article_118(courses: list[dict[str, Any]]) -> list[str]:
    """Ejecuta todas las validaciones del Artículo 118."""
    violations: list[str] = []
    violations.extend(check_article_118a(courses))
    violations.extend(check_article_118b(courses))
    violations.extend(check_article_118c(courses))
    return violations


def evaluate_student(
    db: Database,
    identity_document: str,
    current_period: str,
) -> dict[str, Any] | None:
    """Evalúa la elegibilidad completa de un estudiante."""
    student = get_student_info(db, identity_document)
    if not student:
        return None

    program = student.get("program", "")
    courses = get_student_courses(db, identity_document)

    art118 = check_article_118(courses)
    is_apt = len(art118) == 0

    with db.connect() as conn:
        enrollment_row = conn.execute(
            """
            SELECT id, period FROM enrollments
            WHERE identity_document = ?
            ORDER BY
                CASE WHEN period = ? THEN 0 ELSE 1 END,
                id DESC
            LIMIT 1
            """,
            (identity_document, current_period),
        ).fetchone()
        enrollment_subjects: list[dict[str, Any]] = []
        prereq_issues: list[str] = []
        if enrollment_row:
            rows = conn.execute(
                """
                SELECT code, name FROM enrollment_subjects
                WHERE enrollment_id = ?
                ORDER BY row_order
                """,
                (enrollment_row["id"],),
            ).fetchall()
            enrollment_subjects = [dict(r) for r in rows]

            for subj in enrollment_subjects:
                prereq_codes = db.get_prerequisites(subj["code"], program)
                issue = check_prerequisites(
                    subj["code"], subj["name"], courses, prereq_codes
                )
                if issue:
                    prereq_issues.append(f"{subj['name']} ({subj['code']}): {issue}")
                    is_apt = False

    return {
        "identity_document": identity_document,
        "full_name": student.get("full_name", ""),
        "program": program,
        "student_id": student.get("student_id", ""),
        "academic_index": student.get("academic_index"),
        "periods_completed": student.get("periods_completed", ""),
        "current_period": current_period,
        "enrollment_subjects": [s["name"] for s in enrollment_subjects],
        "prereq_issues": prereq_issues,
        "article_118_violations": art118,
        "is_eligible": is_apt,
    }
