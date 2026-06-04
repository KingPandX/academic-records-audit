from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

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


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

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
