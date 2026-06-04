from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PDF_DIR = Path("data/pdfs")
DEFAULT_MD_DIR = Path("data/markdown")
DEFAULT_DB_PATH = Path("data/audit.db")


@dataclass
class Paths:
    pdf_dir: Path = DEFAULT_PDF_DIR
    markdown_dir: Path = DEFAULT_MD_DIR
    db_path: Path = DEFAULT_DB_PATH

    def resolve(self, base: Path | None = None) -> Paths:
        root = base or Path.cwd()
        return Paths(
            pdf_dir=(root / self.pdf_dir).resolve(),
            markdown_dir=(root / self.markdown_dir).resolve(),
            db_path=(root / self.db_path).resolve(),
        )


@dataclass
class FieldPattern:
    """Etiqueta en BD y expresión regular (con grupo de captura)."""

    key: str
    pattern: str
    flags: int = 0


@dataclass
class ExtractorConfig:
    """Patrones genéricos (solo si se pasa explícitamente al parser)."""

    student_fields: list[FieldPattern] = field(
        default_factory=lambda: [
            FieldPattern(
                "full_name",
                r"(?:nombre(?:\s+del\s+estudiante)?|estudiante|alumno(?:\(a\))?)\s*[:\-]\s*(.+)",
                flags=2,  # re.IGNORECASE
            ),
            FieldPattern(
                "student_id",
                r"(?:matr[ií]cula|carn[eé]|c[eé]dula|id(?:\s+estudiante)?)\s*[:\-#]?\s*([A-Z0-9\-]+)",
                flags=2,
            ),
            FieldPattern(
                "program",
                r"(?:carrera|programa|plan\s+de\s+estudios)\s*[:\-]\s*(.+)",
                flags=2,
            ),
            FieldPattern(
                "faculty",
                r"(?:facultad|escuela|departamento)\s*[:\-]\s*(.+)",
                flags=2,
            ),
            FieldPattern(
                "gpa",
                r"(?:gpa|promedio|índice\s+acad[eé]mico|promedio\s+general)\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)",
                flags=2,
            ),
        ]
    )
    course_code_pattern: str = r"^[A-Z]{2,4}\s?\d{3,4}[A-Z]?$"
    grade_pattern: str = r"^(?:A\+?|B\+?|C\+?|D|F|NP|AP|EX|[0-9]+(?:[.,][0-9]+)?)$"
