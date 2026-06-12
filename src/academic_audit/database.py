from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from academic_audit.config import get_params_db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_pdf TEXT NOT NULL UNIQUE,
    markdown_path TEXT,
    filename TEXT NOT NULL,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL UNIQUE,
    surnames TEXT,
    given_names TEXT,
    full_name TEXT,
    student_id TEXT,
    identity_document TEXT,
    program TEXT,
    study_plan_period INTEGER,
    periods_completed INTEGER,
    nucleus TEXT,
    academic_index REAL,
    issue_date TEXT,
    faculty TEXT,
    gpa REAL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    student_id TEXT,
    period TEXT,
    semester TEXT,
    code TEXT,
    name TEXT,
    grade TEXT,
    credits INTEGER,
    points INTEGER,
    observation TEXT,
    course_type TEXT,
    year TEXT,
    row_order INTEGER,
    source_line TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS academic_index_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    uc_cumulative INTEGER,
    points_cumulative INTEGER,
    index_value REAL,
    row_order INTEGER,
    source_line TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    field_key TEXT NOT NULL,
    field_value TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE (document_id, field_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_markdown_path
    ON documents(markdown_path) WHERE markdown_path IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_courses_document ON courses(document_id);
CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
CREATE INDEX IF NOT EXISTS idx_fields_document ON document_fields(document_id);
CREATE INDEX IF NOT EXISTS idx_index_snapshots_document ON academic_index_snapshots(document_id);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_pdf TEXT NOT NULL UNIQUE,
    markdown_path TEXT,
    filename TEXT NOT NULL,
    content_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    processed_at TEXT NOT NULL DEFAULT (datetime('now')),
    identity_document TEXT UNIQUE,
    full_name TEXT,
    period TEXT,
    program TEXT
);

CREATE TABLE IF NOT EXISTS enrollment_subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enrollment_id INTEGER NOT NULL,
    code TEXT,
    name TEXT NOT NULL,
    section TEXT,
    teacher TEXT,
    row_order INTEGER,
    FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_enrollments_identity ON enrollments(identity_document);
CREATE INDEX IF NOT EXISTS idx_enrollment_subjects_enrollment ON enrollment_subjects(enrollment_id);
"""

# Columnas añadidas tras la versión inicial del esquema
_STUDENT_COLUMNS = (
    ("surnames", "TEXT"),
    ("given_names", "TEXT"),
    ("identity_document", "TEXT"),
    ("study_plan_period", "INTEGER"),
    ("periods_completed", "INTEGER"),
    ("nucleus", "TEXT"),
    ("academic_index", "REAL"),
    ("issue_date", "TEXT"),
)

_COURSE_COLUMNS = (
    ("points", "INTEGER"),
    ("observation", "TEXT"),
    ("course_type", "TEXT"),
    ("student_id", "TEXT"),
)

_ENROLLMENT_COLUMNS = (
    ("identity_document", "TEXT"),
    ("full_name", "TEXT"),
    ("period", "TEXT"),
    ("program", "TEXT"),
)


PARAMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS parameters (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plan_subjects (
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    credits INTEGER,
    semester TEXT,
    program TEXT NOT NULL,
    subject_type TEXT NOT NULL DEFAULT 'obligatoria',
    PRIMARY KEY (code, program)
);

CREATE TABLE IF NOT EXISTS plan_prerequisites (
    subject_code TEXT NOT NULL,
    prereq_code TEXT NOT NULL,
    program TEXT NOT NULL,
    PRIMARY KEY (subject_code, prereq_code, program)
);
"""


class Database:
    def __init__(self, path: Path | None = None, *, memory: bool | None = None) -> None:
        if memory is None:
            memory = path is None
        self._memory = memory
        self._temp_path: Path | None = None
        self._params_path: Path | None = None

        if memory:
            fd, tmp = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            self._temp_path = self.path = Path(tmp)
        else:
            assert path is not None
            self.path = path
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def params_path(self) -> Path:
        if self._params_path is None:
            p = get_params_db_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            self._params_path = p
        return self._params_path

    @contextmanager
    def _params_connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.params_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(PARAMS_SCHEMA)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        if self._temp_path is not None:
            try:
                self._temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._temp_path = None

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_columns(conn)

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        existing_students = {
            row[1] for row in conn.execute("PRAGMA table_info(students)")
        }
        for name, col_type in _STUDENT_COLUMNS:
            if name not in existing_students:
                conn.execute(f"ALTER TABLE students ADD COLUMN {name} {col_type}")

        existing_courses = {
            row[1] for row in conn.execute("PRAGMA table_info(courses)")
        }
        for name, col_type in _COURSE_COLUMNS:
            if name not in existing_courses:
                conn.execute(f"ALTER TABLE courses ADD COLUMN {name} {col_type}")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_courses_student ON courses(student_id)"
        )

        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_markdown_path
            ON documents(markdown_path) WHERE markdown_path IS NOT NULL
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS academic_index_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                uc_cumulative INTEGER,
                points_cumulative INTEGER,
                index_value REAL,
                row_order INTEGER,
                source_line TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_pdf TEXT NOT NULL UNIQUE,
                markdown_path TEXT,
                filename TEXT NOT NULL,
                content_hash TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                processed_at TEXT NOT NULL DEFAULT (datetime('now')),
                identity_document TEXT UNIQUE,
                full_name TEXT,
                period TEXT,
                program TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS enrollment_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enrollment_id INTEGER NOT NULL,
                code TEXT,
                name TEXT NOT NULL,
                section TEXT,
                teacher TEXT,
                row_order INTEGER,
                FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE
            )
            """
        )

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_enrollments_identity ON enrollments(identity_document)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_enrollment_subjects_enrollment ON enrollment_subjects(enrollment_id)"
        )

        existing_enrollments = {
            row[1] for row in conn.execute("PRAGMA table_info(enrollments)")
        }
        for name, col_type in _ENROLLMENT_COLUMNS:
            if name not in existing_enrollments:
                conn.execute(f"ALTER TABLE enrollments ADD COLUMN {name} {col_type}")

    def upsert_document(
        self,
        *,
        source_pdf: str,
        filename: str,
        content_hash: str | None,
        status: str,
        markdown_path: str | None = None,
        error_message: str | None = None,
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (source_pdf, filename, content_hash, status, markdown_path, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET
                    filename = excluded.filename,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    markdown_path = excluded.markdown_path,
                    error_message = excluded.error_message,
                    processed_at = datetime('now')
                """,
                (source_pdf, filename, content_hash, status, markdown_path, error_message),
            )
            row = conn.execute(
                "SELECT id FROM documents WHERE source_pdf = ?", (source_pdf,)
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def ensure_document_for_markdown(
        self,
        md_path: Path,
        pdf_dir: Path | None = None,
        *,
        status: str = "extracted",
    ) -> int:
        """Vincula un .md al documento correcto (nunca crea duplicados por ruta errónea)."""
        from academic_audit.document_resolver import (
            find_document_id,
            normalize_path,
            resolve_source_pdf,
        )

        md_key = normalize_path(md_path)
        filename = f"{md_path.stem}.pdf"
        source_pdf = resolve_source_pdf(md_path, pdf_dir)

        with self.connect() as conn:
            existing_id = find_document_id(conn, md_path, pdf_dir)

            if existing_id is not None:
                conn.execute(
                    """
                    UPDATE documents
                    SET source_pdf = ?, filename = ?, markdown_path = ?,
                        status = ?, processed_at = datetime('now')
                    WHERE id = ?
                    """,
                    (source_pdf, filename, md_key, status, existing_id),
                )
                return existing_id

            conn.execute(
                """
                INSERT INTO documents (source_pdf, filename, markdown_path, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET
                    filename = excluded.filename,
                    markdown_path = excluded.markdown_path,
                    status = excluded.status,
                    processed_at = datetime('now')
                """,
                (source_pdf, filename, md_key, status),
            )
            row = conn.execute(
                "SELECT id FROM documents WHERE source_pdf = ?", (source_pdf,)
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def save_extraction(
        self,
        document_id: int,
        student: dict[str, Any],
        courses: list[dict[str, Any]],
        extra_fields: dict[str, str],
        index_snapshots: list[dict[str, Any]] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM students WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM courses WHERE document_id = ?", (document_id,))
            conn.execute(
                "DELETE FROM document_fields WHERE document_id = ?", (document_id,)
            )
            conn.execute(
                "DELETE FROM academic_index_snapshots WHERE document_id = ?",
                (document_id,),
            )

            conn.execute(
                """
                INSERT INTO students (
                    document_id, surnames, given_names, full_name, student_id,
                    identity_document, program, study_plan_period, periods_completed,
                    nucleus, academic_index, issue_date, faculty, gpa
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    student.get("surnames"),
                    student.get("given_names"),
                    student.get("full_name"),
                    student.get("student_id"),
                    student.get("identity_document"),
                    student.get("program"),
                    student.get("study_plan_period"),
                    student.get("periods_completed"),
                    student.get("nucleus"),
                    student.get("academic_index"),
                    student.get("issue_date"),
                    student.get("faculty"),
                    student.get("gpa"),
                ),
            )

            student_id = student.get("student_id")

            for order, course in enumerate(courses, start=1):
                credits = course.get("credits")
                points = course.get("points")
                conn.execute(
                    """
                    INSERT INTO courses (
                        document_id, student_id, period, semester, code, name, grade,
                        credits, points, observation, course_type, year,
                        row_order, source_line
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        student_id,
                        course.get("period"),
                        course.get("semester"),
                        course.get("code"),
                        course.get("name"),
                        course.get("grade"),
                        int(credits) if credits is not None else None,
                        int(points) if points is not None else None,
                        course.get("observation"),
                        course.get("course_type"),
                        course.get("year"),
                        order,
                        course.get("source_line"),
                    ),
                )

            for order, snapshot in enumerate(index_snapshots or [], start=1):
                conn.execute(
                    """
                    INSERT INTO academic_index_snapshots (
                        document_id, uc_cumulative, points_cumulative,
                        index_value, row_order, source_line
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        snapshot.get("uc_cumulative"),
                        snapshot.get("points_cumulative"),
                        snapshot.get("index_value"),
                        order,
                        snapshot.get("source_line"),
                    ),
                )

            for key, value in extra_fields.items():
                conn.execute(
                    """
                    INSERT INTO document_fields (document_id, field_key, field_value)
                    VALUES (?, ?, ?)
                    """,
                    (document_id, key, str(value)),
                )

    def upsert_enrollment_document(
        self,
        *,
        source_pdf: str,
        filename: str,
        content_hash: str | None,
        status: str,
        markdown_path: str | None = None,
        error_message: str | None = None,
    ) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO enrollments (source_pdf, filename, content_hash, status, markdown_path, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_pdf) DO UPDATE SET
                    filename = excluded.filename,
                    content_hash = excluded.content_hash,
                    status = excluded.status,
                    markdown_path = excluded.markdown_path,
                    error_message = excluded.error_message,
                    processed_at = datetime('now')
                """,
                (source_pdf, filename, content_hash, status, markdown_path, error_message),
            )
            row = conn.execute(
                "SELECT id FROM enrollments WHERE source_pdf = ?", (source_pdf,)
            ).fetchone()
            assert row is not None
            return int(row["id"])

    def save_enrollment(
        self,
        enrollment_id: int,
        *,
        identity_document: str | None = None,
        full_name: str | None = None,
        period: str | None = None,
        program: str | None = None,
        subjects: list[dict[str, Any]] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE enrollments
                SET identity_document = ?, full_name = ?, period = ?, program = ?
                WHERE id = ?
                """,
                (identity_document, full_name, period, program, enrollment_id),
            )

            conn.execute(
                "DELETE FROM enrollment_subjects WHERE enrollment_id = ?",
                (enrollment_id,),
            )

            for order, subject in enumerate(subjects or [], start=1):
                conn.execute(
                    """
                    INSERT INTO enrollment_subjects (enrollment_id, code, name, section, teacher, row_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        enrollment_id,
                        subject.get("code"),
                        subject.get("name"),
                        subject.get("section"),
                        subject.get("teacher"),
                        order,
                    ),
                )

    def set_parameter(
        self,
        key: str,
        value: str,
        description: str | None = None,
    ) -> None:
        with self._params_connect() as conn:
            conn.execute(
                """
                INSERT INTO parameters (key, value, description)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    description = COALESCE(excluded.description, parameters.description),
                    updated_at = datetime('now')
                """,
                (key, value, description),
            )

    def get_parameter(self, key: str) -> str | None:
        with self._params_connect() as conn:
            row = conn.execute(
                "SELECT value FROM parameters WHERE key = ?", (key,)
            ).fetchone()
            return str(row["value"]) if row else None

    def get_all_parameters(self) -> list[dict[str, Any]]:
        with self._params_connect() as conn:
            rows = conn.execute(
                "SELECT key, value, description, updated_at FROM parameters ORDER BY key"
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_parameter(self, key: str) -> bool:
        with self._params_connect() as conn:
            cur = conn.execute("DELETE FROM parameters WHERE key = ?", (key,))
            return cur.rowcount > 0

    def clear_plan(self, program: str) -> None:
        with self._params_connect() as conn:
            conn.execute(
                "DELETE FROM plan_prerequisites WHERE program = ?", (program,)
            )
            conn.execute(
                "DELETE FROM plan_subjects WHERE program = ?", (program,)
            )

    def import_plan_subjects(
        self, subjects: list[dict[str, Any]], prerequisites: list[dict[str, str]]
    ) -> None:
        with self._params_connect() as conn:
            for subj in subjects:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO plan_subjects
                        (code, name, credits, semester, program, subject_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        subj["code"],
                        subj["name"],
                        subj.get("credits"),
                        subj.get("semester"),
                        subj["program"],
                        subj.get("subject_type", "obligatoria"),
                    ),
                )
            for prereq in prerequisites:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO plan_prerequisites
                        (subject_code, prereq_code, program)
                    VALUES (?, ?, ?)
                    """,
                    (prereq["subject_code"], prereq["prereq_code"], prereq["program"]),
                )

    def get_plan_subjects(self, program: str) -> list[dict[str, Any]]:
        with self._params_connect() as conn:
            rows = conn.execute(
                """
                SELECT code, name, credits, semester, program, subject_type
                FROM plan_subjects
                WHERE program = ?
                ORDER BY semester, code
                """,
                (program,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_prerequisites(self, code: str, program: str) -> list[str]:
        with self._params_connect() as conn:
            rows = conn.execute(
                """
                SELECT prereq_code FROM plan_prerequisites
                WHERE subject_code = ? AND program = ?
                """,
                (code, program),
            ).fetchall()
            return [row["prereq_code"] for row in rows]

    def get_all_programs(self) -> list[str]:
        with self._params_connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT program FROM plan_subjects ORDER BY program"
            ).fetchall()
            return [row["program"] for row in rows]
