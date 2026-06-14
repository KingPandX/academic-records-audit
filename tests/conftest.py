from __future__ import annotations

from pathlib import Path

import pytest

from academic_audit.database import PARAMS_SCHEMA, Database

PLAN_SUBJECTS = [
    {"code": "CINU101", "name": "CINU", "credits": 0, "semester": "0", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "MAT-101", "name": "MATEMÁTICA I", "credits": 4, "semester": "1", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "FIS-101", "name": "FÍSICA I", "credits": 4, "semester": "1", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "MAT-201", "name": "MATEMÁTICA II", "credits": 4, "semester": "2", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "FIS-201", "name": "FÍSICA II", "credits": 4, "semester": "2", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "MAT-301", "name": "MATEMÁTICA III", "credits": 4, "semester": "3", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "PRO-301", "name": "PROGRAMACIÓN I", "credits": 3, "semester": "3", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "MAT-401", "name": "MATEMÁTICA IV", "credits": 4, "semester": "4", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
    {"code": "PRO-401", "name": "PROGRAMACIÓN II", "credits": 3, "semester": "4", "program": "INGENIERÍA DE PRUEBA", "subject_type": "obligatoria"},
]

PLAN_PREREQUISITES = [
    {"subject_code": "MAT-201", "prereq_code": "MAT-101", "program": "INGENIERÍA DE PRUEBA"},
    {"subject_code": "FIS-201", "prereq_code": "FIS-101", "program": "INGENIERÍA DE PRUEBA"},
    {"subject_code": "MAT-301", "prereq_code": "MAT-201", "program": "INGENIERÍA DE PRUEBA"},
    {"subject_code": "MAT-401", "prereq_code": "MAT-301", "program": "INGENIERÍA DE PRUEBA"},
    {"subject_code": "PRO-401", "prereq_code": "PRO-301", "program": "INGENIERÍA DE PRUEBA"},
]


@pytest.fixture
def db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "audit.db")
    db.init_schema()
    db._params_path = tmp_path / "parameters.db"
    with db._params_connect() as conn:
        conn.executescript(PARAMS_SCHEMA)
    yield db
    db.close()


def seed_student(db: Database, *, identity_document: str = "V-123", program: str = "INGENIERÍA DE PRUEBA",
                 periods_completed: int = 2, study_plan_period: int | None = None,
                 full_name: str = "ESTUDIANTE, PRUEBA") -> int:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO documents (source_pdf, filename, status)
            VALUES (?, ?, 'extracted')
            """,
            (f"/pdfs/{identity_document}.pdf", f"{identity_document}.pdf"),
        )
        doc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO students (document_id, full_name, student_id, identity_document,
                                  program, periods_completed, study_plan_period)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, full_name, f"1-2021-{identity_document}", identity_document,
             program, periods_completed, study_plan_period),
        )
        return doc_id


def seed_course(db: Database, doc_id: int, *, code: str, name: str, semester: str,
                period: str = "1-2025", grade: str = "15", credits: int = 4, points: int = 60,
                identity_document: str = "V-123", course_type: str = "regular") -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO courses (document_id, student_id, period, semester, code, name,
                                 grade, credits, points, course_type, identity_document)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, f"1-2021-{identity_document}", period, semester, code, name,
             grade, credits, points, course_type, identity_document),
        )


def seed_enrollment(db: Database, *, identity_document: str = "V-123",
                    period: str = "1-2025", program: str = "INGENIERÍA DE PRUEBA",
                    full_name: str = "ESTUDIANTE, PRUEBA",
                    subjects: list[dict]) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO enrollments (source_pdf, filename, status, identity_document,
                                     full_name, period, program)
            VALUES (?, ?, 'extracted', ?, ?, ?, ?)
            """,
            (f"/pdfs/{identity_document}-insc.pdf", f"{identity_document}-insc.pdf",
             identity_document, full_name, period, program),
        )
        enroll_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        for i, subj in enumerate(subjects, start=1):
            conn.execute(
                """
                INSERT INTO enrollment_subjects (enrollment_id, code, name, row_order)
                VALUES (?, ?, ?, ?)
                """,
                (enroll_id, subj["code"], subj["name"], i),
            )


def seed_plan(db: Database, program: str = "INGENIERÍA DE PRUEBA",
              subjects: list[dict] | None = None,
              prereqs: list[dict] | None = None) -> None:
    subjects = subjects or PLAN_SUBJECTS
    prereqs = prereqs or PLAN_PREREQUISITES
    db.clear_plan(program)
    db.import_plan_subjects(subjects, prereqs)
