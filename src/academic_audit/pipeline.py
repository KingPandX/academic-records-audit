from __future__ import annotations

import logging
from pathlib import Path

from academic_audit.config import ExtractorConfig, Paths
from academic_audit.convert import convert_folder
from academic_audit.database import Database
from academic_audit.extract import extract_folder

logger = logging.getLogger(__name__)


def run_pipeline(
    paths: Paths,
    *,
    recursive: bool = True,
    config: ExtractorConfig | None = None,
) -> None:
    paths = paths.resolve()
    paths.pdf_dir.mkdir(parents=True, exist_ok=True)
    paths.markdown_dir.mkdir(parents=True, exist_ok=True)

    db = Database(paths.db_path)
    logger.info("PDFs: %s", paths.pdf_dir)
    logger.info("Markdown: %s", paths.markdown_dir)
    logger.info("Base de datos: %s", paths.db_path)

    convert_folder(paths.pdf_dir, paths.markdown_dir, db, recursive=recursive)
    extract_folder(
        paths.markdown_dir,
        db,
        pdf_dir=paths.pdf_dir,
        recursive=recursive,
        config=config,
    )
