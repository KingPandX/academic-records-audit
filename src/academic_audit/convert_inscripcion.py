from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from markitdown import MarkItDown

from academic_audit.database import Database

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    pdf_path: Path
    markdown_path: Path | None
    success: bool
    error: str | None = None


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_pdfs(pdf_dir: Path, recursive: bool = True) -> list[Path]:
    if not pdf_dir.exists():
        return []
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(pdf_dir.glob(pattern))


def convert_pdf(pdf_path: Path, output_dir: Path, converter: MarkItDown | None = None) -> ConversionResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{pdf_path.stem}.md"
    md = converter or MarkItDown()

    try:
        result = md.convert(pdf_path)
        text = result.text_content or ""
        md_path.write_text(text, encoding="utf-8")
        logger.info("Convertido: %s → %s (%d caracteres)", pdf_path.name, md_path.name, len(text))
        return ConversionResult(pdf_path=pdf_path, markdown_path=md_path, success=True)
    except Exception as exc:
        logger.exception("Error al convertir %s", pdf_path)
        return ConversionResult(
            pdf_path=pdf_path,
            markdown_path=None,
            success=False,
            error=str(exc),
        )


def convert_inscripcion_folder(
    pdf_dir: Path,
    markdown_dir: Path,
    db: Database,
    *,
    recursive: bool = True,
    workers: int = 3,
) -> list[ConversionResult]:
    db.init_schema()
    pdfs = discover_pdfs(pdf_dir, recursive=recursive)
    if not pdfs:
        logger.warning("No se encontraron PDFs de inscripción en %s", pdf_dir)
        return []

    converter = MarkItDown()
    hashes: dict[int, str] = {}
    results: list[ConversionResult | None] = [None] * len(pdfs)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, pdf_path in enumerate(pdfs):
            hashes[i] = _file_hash(pdf_path)
            futures[executor.submit(convert_pdf, pdf_path, markdown_dir, converter)] = i

        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()

    for i, outcome in enumerate(results):
        assert outcome is not None
        pdf_path = pdfs[i]
        content_hash = hashes[i]

        if outcome.success and outcome.markdown_path:
            db.upsert_enrollment_document(
                source_pdf=str(pdf_path.resolve()),
                filename=pdf_path.name,
                content_hash=content_hash,
                status="converted",
                markdown_path=str(outcome.markdown_path.resolve()),
            )
        else:
            db.upsert_enrollment_document(
                source_pdf=str(pdf_path.resolve()),
                filename=pdf_path.name,
                content_hash=content_hash,
                status="conversion_failed",
                error_message=outcome.error,
            )

    ok = sum(1 for r in results if r and r.success)
    logger.info("Conversión de inscripciones terminada: %d/%d exitosos", ok, len(results))
    return results  # type: ignore[return-value]
