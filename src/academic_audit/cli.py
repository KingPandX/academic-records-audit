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
        "--db", type=Path, default=None, help="Archivo SQLite (persistir datos en disco)"
    )
    common.add_argument(
        "--inscripcion-dir",
        type=Path,
        default=Paths().inscripcion_dir,
        help="Carpeta con PDFs de inscripción",
    )
    common.add_argument(
        "--inscripcion-md-dir",
        type=Path,
        default=Paths().inscripcion_md_dir,
        help="Carpeta de salida Markdown de inscripción",
    )
    common.add_argument(
        "--report",
        action="store_true",
        help="Generar reporte CSV al finalizar",
    )
    common.add_argument(
        "--report-dir",
        type=Path,
        default=Paths().report_dir,
        help="Directorio de salida para reportes",
    )
    common.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Hilos paralelos para conversión PDF (default: 3)",
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

    # ---  subcomando param  ---
    param_parser = sub.add_parser(
        "param",
        help="Gestionar parámetros persistentes del sistema",
    )
    param_sub = param_parser.add_subparsers(dest="param_action", required=True)

    p_set = param_sub.add_parser("set", help="Crear o actualizar un parámetro")
    p_set.add_argument("key", help="Nombre del parámetro")
    p_set.add_argument("value", help="Valor del parámetro")
    p_set.add_argument("--description", help="Descripción del parámetro")

    p_get = param_sub.add_parser("get", help="Obtener el valor de un parámetro")
    p_get.add_argument("key", help="Nombre del parámetro")

    p_list = param_sub.add_parser("list", help="Listar todos los parámetros")

    p_delete = param_sub.add_parser("delete", help="Eliminar un parámetro")
    p_delete.add_argument("key", help="Nombre del parámetro")

    # ---  subcomando plan  ---
    plan_parser = sub.add_parser(
        "plan",
        help="Gestionar planes de estudio (pensum)",
    )
    plan_sub = plan_parser.add_subparsers(dest="plan_action", required=True)

    plan_import = plan_sub.add_parser("import", help="Importar plan de estudio desde XLS")
    plan_import.add_argument("file", type=Path, help="Archivo .xls del pensum")

    plan_list = plan_sub.add_parser("list", help="Listar programas importados")
    plan_list.add_argument("--program", help="Filtrar por programa")

    # ---  subcomando gui  ---
    gui_parser = sub.add_parser(
        "gui",
        help="Interfaz gráfica (Gradio)",
    )
    gui_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Base de datos SQLite a utilizar",
    )
    gui_parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Puerto para la interfaz web (default: 7860)",
    )

    # ---  subcomando serve  ---
    serve_parser = sub.add_parser(
        "serve",
        help="Interfaz web (FastAPI)",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Puerto (default: 8000)",
    )
    serve_parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Base de datos SQLite a utilizar",
    )

    return parser


def _paths_from_args(args: argparse.Namespace) -> Paths:
    base = args.base_dir.resolve()
    return Paths(
        pdf_dir=base / args.pdf_dir,
        markdown_dir=base / args.md_dir,
        inscripcion_dir=base / args.inscripcion_dir,
        inscripcion_md_dir=base / args.inscripcion_md_dir,
        db_path=base / args.db if args.db is not None else None,
        report_dir=base / args.report_dir,
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

    if args.command == "param":
        db = Database()
        try:
            if args.param_action == "set":
                db.set_parameter(args.key, args.value, args.description)
                print(f"Parámetro '{args.key}' = '{args.value}' guardado.")
            elif args.param_action == "get":
                value = db.get_parameter(args.key)
                if value is not None:
                    print(value)
                else:
                    print(f"Parámetro '{args.key}' no encontrado.")
                    return 1
            elif args.param_action == "list":
                params = db.get_all_parameters()
                if params:
                    for p in params:
                        desc = f" — {p['description']}" if p["description"] else ""
                        print(f"{p['key']} = {p['value']}{desc}")
                else:
                    print("No hay parámetros configurados.")
            elif args.param_action == "delete":
                if db.delete_parameter(args.key):
                    print(f"Parámetro '{args.key}' eliminado.")
                else:
                    print(f"Parámetro '{args.key}' no encontrado.")
                    return 1
        finally:
            db.close()
        return 0

    if args.command == "plan":
        from academic_audit.study_plan import parse_xls

        db = Database()
        try:
            if args.plan_action == "import":
                results = parse_xls(args.file)
                for prog in results:
                    db.clear_plan(prog["program"])
                    db.import_plan_subjects(prog["subjects"], prog["prerequisites"])
                    print(
                        f"Importado: {prog['program']} "
                        f"({len(prog['subjects'])} materias, "
                        f"{len(prog['prerequisites'])} prelaciones)"
                    )
                print(f"\nTotal: {len(results)} programas importados.")
            elif args.plan_action == "list":
                if args.program:
                    programs = [args.program]
                else:
                    programs = db.get_all_programs()
                if not programs:
                    print("No hay planes de estudio importados.")
                    return 0
                for prog in programs:
                    subjects = db.get_plan_subjects(prog)
                    if not subjects:
                        print(f"{prog}: (no encontrado)")
                        continue
                    prereq_count = sum(
                        len(db.get_prerequisites(s["code"], prog))
                        for s in subjects
                    )
                    print(f"{prog}: {len(subjects)} materias, {prereq_count} prelaciones")
        finally:
            db.close()
        return 0

    if args.command == "init-db":
        if args.db is None:
            print("init-db no es necesario en modo memoria (--db para persistir)")
            return 0
        paths = _paths_from_args(args)
        Database(paths.db_path, memory=False).init_schema()
        print(f"Base de datos inicializada: {paths.db_path}")
        return 0

    if args.command == "gui":
        from academic_audit.gui import launch

        launch(db_path=args.db, port=args.port)
        return 0

    if args.command == "serve":
        from academic_audit.web.app import run

        run(host=args.host, port=args.port, db_path=args.db)
        return 0

    paths = _paths_from_args(args)
    memory = args.db is None
    recursive = not args.no_recursive
    workers = args.workers
    db = Database(paths.db_path, memory=memory)

    try:
        if args.command == "convert":
            convert_folder(
                paths.pdf_dir, paths.markdown_dir, db,
                recursive=recursive, workers=workers,
            )
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
            run_pipeline(
                paths,
                recursive=recursive,
                memory=memory,
                workers=workers,
                report=args.report,
            )
            return 0
    finally:
        db.close()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
