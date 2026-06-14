from __future__ import annotations

import sqlite3
from pathlib import Path

from academic_audit.database import Database
from academic_audit.document_resolver import find_document_id, normalize_path


def test_ensure_document_links_markdown_to_pdf(tmp_path: Path) -> None:
    pdf_dir = tmp_path / "pdfs"
    md_dir = tmp_path / "markdown"
    pdf_dir.mkdir()
    md_dir.mkdir()

    pdf = pdf_dir / "estudiante-123.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    md = md_dir / "estudiante-123.md"
    md.write_text("# record", encoding="utf-8")

    db = Database(tmp_path / "test.db")
    db.init_schema()

    # Simula conversión previa
    db.upsert_document(
        source_pdf=str(pdf.resolve()),
        filename=pdf.name,
        content_hash="abc",
        status="converted",
        markdown_path=str(md.resolve()),
    )

    doc_id = db.ensure_document_for_markdown(md, pdf_dir=pdf_dir)
    assert doc_id == 1

    with db.connect() as conn:
        row = conn.execute(
            "SELECT source_pdf, markdown_path FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        assert row is not None
        assert row["source_pdf"] == normalize_path(pdf)
        assert row["markdown_path"] == normalize_path(md)


def test_find_document_by_filename_when_markdown_path_differs(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            source_pdf TEXT NOT NULL UNIQUE,
            markdown_path TEXT,
            filename TEXT NOT NULL,
            status TEXT DEFAULT 'converted'
        );
        """
    )
    conn.execute(
        """
        INSERT INTO documents (source_pdf, filename, markdown_path, status)
        VALUES (?, ?, NULL, 'converted')
        """,
        ("/data/pdfs/alumno.pdf", "alumno.pdf"),
    )
    conn.commit()

    md = Path("/data/markdown/alumno.md")
    doc_id = find_document_id(conn, md, Path("/data/pdfs"))
    assert doc_id == 1
    conn.close()
