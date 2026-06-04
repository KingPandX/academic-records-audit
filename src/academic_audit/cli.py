from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from academic_audit import __version__
from academic_audit.config import Paths
from academic_audit.convert import convert_folder
from academic_audit.database import Database
from academic_audit.extract import extract_folder
from academic_audit.pipeline import run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="academic-audit",
        description="Convierte expedientes PDF a Markdown y extrae datos a SQLite.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Salida detallada"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Directorio base para rutas relativas (por defecto: cwd)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--pdf-dir", type=Path, default=Paths().pdf_dir, help="Carpeta con PDFs"
    )
    common.add_argument(
        "--md-dir",
        type=Path,
        default=Paths().markdown_dir,
        help="Carpeta de salida Markdown",
    )
    common.add_argument(
        "--db", type=Path, default=Paths().db_path, help="Archivo SQLite"
    )
    common.add_argument(
        "--no-recursive",
        action="store_true",
        help="No buscar en subcarpetas",
    )

    sub.add_parser(
        "convert",
        parents=[common],
        help="Solo convertir PDF → Markdown",
    )
    sub.add_parser(
        "extract",
        parents=[common],
        help="Solo extraer Markdown → SQLite",
    )
    sub.add_parser(
        "run",
        parents=[common],
        help="Pipeline completo: convertir y extraer",
    )

    sub.add_parser("init-db", parents=[common], help="Crear esquema SQLite")

    sub.add_parser("version", help="Mostrar versión")
    return parser


def _paths_from_args(args: argparse.Namespace) -> Paths:
    base = args.base_dir.resolve()
    return Paths(
        pdf_dir=base / args.pdf_dir,
        markdown_dir=base / args.md_dir,
        db_path=base / args.db,
    ).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "init-db":
        paths = _paths_from_args(args)
        Database(paths.db_path).init_schema()
        print(f"Base de datos inicializada: {paths.db_path}")
        return 0

    paths = _paths_from_args(args)
    recursive = not args.no_recursive
    db = Database(paths.db_path)

    if args.command == "convert":
        convert_folder(paths.pdf_dir, paths.markdown_dir, db, recursive=recursive)
        return 0

    if args.command == "extract":
        extract_folder(
            paths.markdown_dir,
            db,
            pdf_dir=paths.pdf_dir,
            recursive=recursive,
        )
        return 0

    if args.command == "run":
        run_pipeline(paths, recursive=recursive)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
