from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PDF_DIR = Path("data/pdfs")


def get_params_db_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        base = Path(config_home)
    else:
        base = Path.home() / ".config"
    params_dir = base / "academic-audit"
    return params_dir / "parameters.db"
DEFAULT_MD_DIR = Path("data/markdown")
DEFAULT_INSCRIPCION_DIR = Path("data/inscripcion")
DEFAULT_INSCRIPCION_MD_DIR = Path("data/markdown-inscripcion")
DEFAULT_DB_PATH = Path("data/audit.db")
DEFAULT_REPORT_DIR = Path("reports")


@dataclass
class Paths:
    pdf_dir: Path = DEFAULT_PDF_DIR
    markdown_dir: Path = DEFAULT_MD_DIR
    inscripcion_dir: Path = DEFAULT_INSCRIPCION_DIR
    inscripcion_md_dir: Path = DEFAULT_INSCRIPCION_MD_DIR
    db_path: Path | None = None
    report_dir: Path = DEFAULT_REPORT_DIR

    def resolve(self, base: Path | None = None) -> Paths:
        root = base or Path.cwd()
        return Paths(
            pdf_dir=(root / self.pdf_dir).resolve(),
            markdown_dir=(root / self.markdown_dir).resolve(),
            inscripcion_dir=(root / self.inscripcion_dir).resolve(),
            inscripcion_md_dir=(root / self.inscripcion_md_dir).resolve(),
            db_path=(root / self.db_path).resolve() if self.db_path else None,
            report_dir=(root / self.report_dir).resolve(),
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
