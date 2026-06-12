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


class EligibilityReport(ReportWriter):
    filename = "elegibilidad.csv"

    @property
    def columns(self) -> list[str]:
        return [
            "identity_document", "full_name", "program",
            "student_id", "periodo_actual", "indice_academico",
            "periodos_cursados", "materias_a_inscribir",
            "prelaciones_incumplidas", "violaciones_art118",
            "elegibilidad", "observaciones",
        ]

    def query_data(self, db: Database) -> list[dict[str, Any]]:
        from academic_audit.eligibility import evaluate_student

        current_period = db.get_parameter("periodo_actual") or ""

        with db.connect() as conn:
            enrollments = conn.execute(
                """
                SELECT DISTINCT e.identity_document, e.period
                FROM enrollments e
                WHERE e.identity_document IS NOT NULL
                ORDER BY e.identity_document
                """
            ).fetchall()

        if not enrollments:
            with db.connect() as conn:
                students = conn.execute(
                    """
                    SELECT DISTINCT s.identity_document
                    FROM students s
                    WHERE s.identity_document IS NOT NULL
                    """
                ).fetchall()
            identities = [row["identity_document"] for row in students]
        else:
            identities = [row["identity_document"] for row in enrollments]

        results: list[dict[str, Any]] = []
        for id_doc in identities:
            result = evaluate_student(db, id_doc, current_period)
            if result is None:
                continue

            inscribir = "; ".join(result["enrollment_subjects"]) if result["enrollment_subjects"] else ""
            prelaciones = "; ".join(result["prereq_issues"])
            art118 = "; ".join(result["article_118_violations"])

            observaciones: list[str] = []
            if prelaciones:
                observaciones.append(f"Prelaciones: {prelaciones}")
            if art118:
                observaciones.append(f"Art.118: {art118}")
            if not result["is_eligible"] and not observaciones:
                observaciones.append("No cumple requisitos")

            results.append(
                {
                    "identity_document": result["identity_document"],
                    "full_name": result["full_name"],
                    "program": result["program"],
                    "student_id": result["student_id"],
                    "periodo_actual": result["current_period"],
                    "indice_academico": result["academic_index"],
                    "periodos_cursados": result["periods_completed"],
                    "materias_a_inscribir": inscribir,
                    "prelaciones_incumplidas": prelaciones,
                    "violaciones_art118": art118,
                    "elegibilidad": "APTO" if result["is_eligible"] else "NO APTO",
                    "observaciones": " | ".join(observaciones),
                }
            )

        return results


REGISTRY: dict[str, type[ReportWriter]] = {
    "student_courses": StudentCoursesReport,
    "eligibility": EligibilityReport,
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
