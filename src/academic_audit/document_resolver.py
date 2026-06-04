from __future__ import annotations

import sqlite3
from pathlib import Path


def normalize_path(path: Path | str) -> str:
    return str(Path(path).expanduser().resolve())


def resolve_source_pdf(md_path: Path, pdf_dir: Path | None) -> str:
    """Ubica el PDF original a partir del .md (mismo nombre base en pdf_dir)."""
    stem = md_path.stem
    if pdf_dir and pdf_dir.is_dir():
        matches = sorted(pdf_dir.rglob(f"{stem}.pdf"))
        matches.extend(sorted(pdf_dir.rglob(f"{stem}.PDF")))
        if matches:
            return normalize_path(matches[0])
    return normalize_path((pdf_dir or md_path.parent) / f"{stem}.pdf")


def find_document_id(
    conn: sqlite3.Connection,
    md_path: Path,
    pdf_dir: Path | None = None,
) -> int | None:
    """Busca el documento ya registrado para este markdown o su PDF."""
    md_key = normalize_path(md_path)
    row = conn.execute(
        "SELECT id FROM documents WHERE markdown_path = ?",
        (md_key,),
    ).fetchone()
    if row:
        return int(row["id"])

    filename = f"{md_path.stem}.pdf"
    row = conn.execute(
        """
        SELECT id FROM documents
        WHERE filename = ?
           OR source_pdf LIKE ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (filename, f"%/{filename}"),
    ).fetchone()
    if row:
        return int(row["id"])

    if pdf_dir:
        source_pdf = resolve_source_pdf(md_path, pdf_dir)
        row = conn.execute(
            "SELECT id FROM documents WHERE source_pdf = ?",
            (source_pdf,),
        ).fetchone()
        if row:
            return int(row["id"])

    return None
