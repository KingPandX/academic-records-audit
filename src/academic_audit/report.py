from __future__ import annotations

import csv
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from academic_audit.database import Database

logger = logging.getLogger(__name__)


class ReportWriter(ABC):
    @property
    @abstractmethod
    def filename(self) -> str: ...

    @property
    @abstractmethod
    def columns(self) -> list[str]: ...

    @abstractmethod
    def query_data(self, db: Database) -> list[dict[str, Any]]: ...

    def write(self, db: Database, output_dir: Path) -> Path:
        data = self.query_data(db)
        path = output_dir / self.filename
        output_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.columns)
            writer.writeheader()
            for row in data:
                writer.writerow(dict(row) if hasattr(row, "keys") else row)
        logger.info("Reporte generado: %s (%d filas)", path, len(data))
        return path


class StudentCoursesReport(ReportWriter):
    filename = "estudiantes-materias.csv"

    @property
    def columns(self) -> list[str]:
        return [
            "student_id", "identity_document", "full_name", "program",
            "period", "semester", "code", "name", "grade", "credits",
            "points", "observation", "course_type",
        ]

    def query_data(self, db: Database) -> list[dict[str, Any]]:
        with db.connect() as conn:
            return conn.execute("""
                SELECT s.student_id, s.identity_document, s.full_name, s.program,
                       c.period, c.semester, c.code, c.name, c.grade,
                       c.credits, c.points, c.observation, c.course_type
                FROM students s
                JOIN courses c ON c.document_id = s.document_id
                ORDER BY s.student_id,
                         CAST(SUBSTR(c.period, INSTR(c.period, '-') + 1) AS INTEGER),
                         CAST(SUBSTR(c.period, 1, INSTR(c.period, '-') - 1) AS INTEGER),
                         c.semester, c.row_order
            """).fetchall()


REGISTRY: dict[str, type[ReportWriter]] = {
    "student_courses": StudentCoursesReport,
}


def generate_reports(
    db: Database,
    output_dir: Path,
    report_names: list[str] | None = None,
) -> list[Path]:
    report_names = report_names or list(REGISTRY)
    paths: list[Path] = []
    for name in report_names:
        writer_cls = REGISTRY.get(name)
        if writer_cls is None:
            logger.warning("Reporte desconocido: %s (omitido)", name)
            continue
        path = writer_cls().write(db, output_dir)
        paths.append(path)
    return paths
