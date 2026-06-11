from __future__ import annotations

import logging
from pathlib import Path

from academic_audit.database import Database
from academic_audit.parsers.inscripcion import parse_enrollment

logger = logging.getLogger(__name__)


def discover_markdown(md_dir: Path, recursive: bool = True) -> list[Path]:
    if not md_dir.exists():
        return []
    pattern = "**/*.md" if recursive else "*.md"
    return sorted(md_dir.glob(pattern))


def _resolve_source_pdf(md_path: Path, pdf_dir: Path | None) -> str:
    stem = md_path.stem
    if pdf_dir and pdf_dir.is_dir():
        matches = sorted(pdf_dir.rglob(f"{stem}.pdf"))
        matches.extend(sorted(pdf_dir.rglob(f"{stem}.PDF")))
        if matches:
            return str(matches[0].resolve())
    return str((pdf_dir or md_path.parent / f"{stem}.pdf").resolve())


def extract_markdown_file(
    md_path: Path,
    db: Database,
    *,
    pdf_dir: Path | None = None,
) -> int:
    text = md_path.read_text(encoding="utf-8")
    parsed = parse_enrollment(text)

    source_pdf = _resolve_source_pdf(md_path, pdf_dir)
    filename = f"{md_path.stem}.pdf"
    md_key = str(md_path.resolve())

    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM enrollments WHERE source_pdf = ?",
            (source_pdf,),
        ).fetchone()

        if row is not None:
            enrollment_id = int(row["id"])
            conn.execute(
                """
                UPDATE enrollments
                SET markdown_path = ?, status = 'extracted', processed_at = datetime('now')
                WHERE id = ?
                """,
                (md_key, enrollment_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO enrollments (source_pdf, filename, markdown_path, status)
                VALUES (?, ?, ?, 'extracted')
                """,
                (source_pdf, filename, md_key),
            )
            row = conn.execute(
                "SELECT id FROM enrollments WHERE source_pdf = ?",
                (source_pdf,),
            ).fetchone()
            assert row is not None
            enrollment_id = int(row["id"])

    db.save_enrollment(
        enrollment_id,
        identity_document=parsed.identity_document,
        full_name=parsed.full_name,
        period=parsed.period,
        program=parsed.program,
        subjects=parsed.subjects,
    )

    logger.info(
        "Extraído inscripción %s → enrollment_id=%d (%s): %d materias",
        md_path.name,
        enrollment_id,
        parsed.identity_document or "?",
        len(parsed.subjects),
    )
    return enrollment_id


def extract_inscripcion_folder(
    markdown_dir: Path,
    db: Database,
    *,
    pdf_dir: Path | None = None,
    recursive: bool = True,
) -> list[int]:
    db.init_schema()
    files = discover_markdown(markdown_dir, recursive=recursive)
    if not files:
        logger.warning("No se encontraron archivos .md de inscripción en %s", markdown_dir)
        return []

    ids: list[int] = []
    for md_path in files:
        doc_id = extract_markdown_file(md_path, db, pdf_dir=pdf_dir)
        ids.append(doc_id)

    logger.info("Extracción de inscripciones terminada: %d documentos", len(ids))
    return ids
