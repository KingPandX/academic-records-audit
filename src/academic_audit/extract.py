from __future__ import annotations

import logging
from pathlib import Path

from academic_audit.config import ExtractorConfig
from academic_audit.database import Database
from academic_audit.parsers import parse_transcript

logger = logging.getLogger(__name__)


def discover_markdown(md_dir: Path, recursive: bool = True) -> list[Path]:
    if not md_dir.exists():
        return []
    pattern = "**/*.md" if recursive else "*.md"
    return sorted(md_dir.glob(pattern))


def extract_markdown_file(
    md_path: Path,
    db: Database,
    *,
    pdf_dir: Path | None = None,
    config: ExtractorConfig | None = None,
) -> int:
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_transcript(text, config)

    document_id = db.ensure_document_for_markdown(
        md_path, pdf_dir=pdf_dir, status="extracted"
    )

    db.save_extraction(
        document_id,
        student=parsed.student,
        courses=parsed.courses,
        extra_fields=parsed.extra_fields,
        index_snapshots=parsed.index_snapshots,
    )

    matricula = parsed.student.get("student_id", "?")
    logger.info(
        "Extraído %s → document_id=%d (matrícula %s): %d cursos",
        md_path.name,
        document_id,
        matricula,
        len(parsed.courses),
    )
    return document_id


def extract_folder(
    markdown_dir: Path,
    db: Database,
    *,
    pdf_dir: Path | None = None,
    recursive: bool = True,
    config: ExtractorConfig | None = None,
) -> list[int]:
    db.init_schema()
    files = discover_markdown(markdown_dir, recursive=recursive)
    if not files:
        logger.warning("No se encontraron archivos .md en %s", markdown_dir)
        return []

    ids: list[int] = []
    for md_path in files:
        doc_id = extract_markdown_file(
            md_path, db, pdf_dir=pdf_dir, config=config
        )
        ids.append(doc_id)

    logger.info("Extracción terminada: %d documentos", len(ids))
    return ids
