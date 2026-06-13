from __future__ import annotations

import logging
import queue
import threading
import warnings
from pathlib import Path
from typing import Any, Callable, Generator

warnings.filterwarnings("ignore", message=".*HTTP_422_UNPROCESSABLE_ENTITY.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="gradio")

_GUI_DB_PATH = Path.cwd() / "data" / "audit.db"

import gradio as gr

from academic_audit.config import Paths
from academic_audit.convert import convert_folder as _convert_folder
from academic_audit.database import Database
from academic_audit.eligibility import (
    evaluate_student,
)
from academic_audit.extract import extract_folder as _extract_folder
from academic_audit.pipeline import run_pipeline as _run_pipeline
from academic_audit.report import generate_reports as _generate_reports
from academic_audit.study_plan import parse_xls as _parse_xls

logger = logging.getLogger(__name__)

# ── helpers ──


def _resolve_path(val: str) -> Path | None:
    val = val.strip()
    if not val:
        return None
    p = Path(val)
    return p if p.is_absolute() else Path.cwd() / p


def _open_db() -> Database:
    _GUI_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = Database(_GUI_DB_PATH, memory=False)
    db.init_schema()
    return db


def _delete_db() -> str:
    try:
        if _GUI_DB_PATH.exists():
            size = _GUI_DB_PATH.stat().st_size
            _GUI_DB_PATH.unlink()
            return f"\U0001F5D1 Base de datos eliminada ({size:,} bytes): {_GUI_DB_PATH}"
        return f"\u2139\ufe0f La base de datos no existe: {_GUI_DB_PATH}"
    except Exception as e:
        logger.exception("Error eliminando BD")
        return f"\u274C Error al eliminar: {e}"


def _run_with_logs(
    desc: str,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Generator[str, None, None]:
    log_q: queue.Queue[str | None] = queue.Queue()

    class _QueueHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.setFormatter(logging.Formatter(
                "[%(asctime)s] %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            ))

        def emit(self, record: logging.LogRecord) -> None:
            log_q.put(self.format(record))

    handler = _QueueHandler()
    logging.getLogger().addHandler(handler)

    exc_info: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            fn(*args, **kwargs)
        except BaseException as e:
            logger.exception("Error en %s", desc)
            exc_info[0] = e
        finally:
            log_q.put(None)

    thread = threading.Thread(target=_worker, daemon=True, name=f"gui-{desc}")
    thread.start()

    lines: list[str] = []
    while thread.is_alive():
        try:
            msg = log_q.get(timeout=0.3)
            if msg is None:
                break
            lines.append(msg)
            yield "\n".join(lines[-300:])
        except queue.Empty:
            yield "\n".join(lines[-300:])

    while True:
        try:
            msg = log_q.get_nowait()
            if msg is None:
                break
            lines.append(msg)
        except queue.Empty:
            break

    if exc_info[0] is not None:
        lines.append(f"ERROR: {exc_info[0]}")
        yield "\n".join(lines[-300:])

    logging.getLogger().removeHandler(handler)
    yield "\n".join(lines[-300:])


# ── tab: pipeline ──


def _pipeline_tab() -> None:
    with gr.TabItem("Pipeline"):
        gr.Markdown("### Flujo principal de procesamiento de expedientes")
        with gr.Row():
            with gr.Column(scale=2):
                pdf_dir = gr.Textbox(
                    label="PDFs (expedientes)",
                    value=str(Paths.pdf_dir),
                )
                md_dir = gr.Textbox(
                    label="Markdown destino (expedientes)",
                    value=str(Paths.markdown_dir),
                )
                insc_dir = gr.Textbox(
                    label="PDFs (inscripción)",
                    value=str(Paths.inscripcion_dir),
                )
                insc_md_dir = gr.Textbox(
                    label="Markdown destino (inscripción)",
                    value=str(Paths.inscripcion_md_dir),
                )
                report_dir = gr.Textbox(
                    label="Directorio de reportes",
                    value=str(Paths.report_dir),
                )
                workers = gr.Slider(1, 8, value=3, step=1, label="Hilos paralelos")
            with gr.Column(scale=1):
                btn_convert = gr.Button("Convertir PDFs \u2192 Markdown", variant="primary")
                btn_extract = gr.Button("Extraer Markdown \u2192 SQLite", variant="primary")
                btn_pipeline = gr.Button("Pipeline completo", variant="primary", size="lg")
                btn_reports = gr.Button("Generar reportes CSV")
        log_box = gr.Textbox(label="Log", lines=20, max_lines=300, interactive=False)

        def _convert(*args: Any) -> Generator[str, None, None]:
            pdf, md, _, _, _, wk = args
            db = _open_db()
            yield from _run_with_logs(
                "convertir", _convert_folder,
                _resolve_path(pdf), _resolve_path(md), db,
                recursive=True, workers=int(wk),
            )
            db.close()

        def _extract(*args: Any) -> Generator[str, None, None]:
            _, md, _, _, _, _ = args
            db = _open_db()
            yield from _run_with_logs(
                "extraer", _extract_folder,
                _resolve_path(md), db,
                pdf_dir=_resolve_path(md) if md else None,
                recursive=True,
            )
            db.close()

        def _pipeline(*args: Any) -> Generator[str, None, None]:
            pdf, md, insc, insc_md, rp, wk = args
            paths = Paths(
                pdf_dir=_resolve_path(pdf) or Paths.pdf_dir,
                markdown_dir=_resolve_path(md) or Paths.markdown_dir,
                inscripcion_dir=_resolve_path(insc) or Paths.inscripcion_dir,
                inscripcion_md_dir=_resolve_path(insc_md) or Paths.inscripcion_md_dir,
                db_path=_GUI_DB_PATH,
                report_dir=_resolve_path(rp) or Paths.report_dir,
            )
            db = _open_db()
            yield from _run_with_logs(
                "pipeline", _run_pipeline, paths,
                recursive=True, memory=False, workers=int(wk), report=False,
            )
            db.close()

        def _reports(*args: Any) -> Generator[str, None, None]:
            _, _, _, _, rp, _ = args
            db = _open_db()
            yield from _run_with_logs(
                "reportes", _generate_reports, db,
                _resolve_path(rp) or Paths.report_dir,
            )
            db.close()

        btn_convert.click(
            fn=_convert,
            inputs=[pdf_dir, md_dir, insc_dir, insc_md_dir, report_dir, workers],
            outputs=log_box,
        )

        btn_extract.click(
            fn=_extract,
            inputs=[pdf_dir, md_dir, insc_dir, insc_md_dir, report_dir, workers],
            outputs=log_box,
        )

        btn_pipeline.click(
            fn=_pipeline,
            inputs=[pdf_dir, md_dir, insc_dir, insc_md_dir, report_dir, workers],
            outputs=log_box,
        )

        btn_reports.click(
            fn=_reports,
            inputs=[pdf_dir, md_dir, insc_dir, insc_md_dir, report_dir, workers],
            outputs=log_box,
        )


# ── tab: plan de estudios ──


def _study_plan_tab() -> None:
    with gr.TabItem("Plan de Estudios"):
        gr.Markdown("### Importar y consultar planes de estudio (pensum)")
        with gr.Row():
            xls_file = gr.File(label="Archivo .xls del pensum", file_types=[".xls"])
        with gr.Row():
            btn_import = gr.Button("Importar plan", variant="primary")
            btn_refresh_sp = gr.Button("Refrescar programas")
        program_drop = gr.Dropdown(label="Programa", interactive=True, allow_custom_value=True)
        subjects_table = gr.Dataframe(
            label="Materias del pensum",
            headers=["Código", "Nombre", "Créditos", "Semestre", "Tipo"],
            datatype=["str", "str", "number", "str", "str"],
            column_count=5,
        )
        prereq_table = gr.Dataframe(
            label="Prelaciones (materia seleccionada)",
            headers=["Materia", "Prelación"],
            datatype=["str", "str"],
            column_count=2,
        )
        log_sp = gr.Textbox(label="Log", lines=6, max_lines=30, interactive=False)

        def _do_import(file: Any) -> tuple[str, dict]:
            if file is None:
                return "Selecciona un archivo .xls", gr.update(choices=[], value=None)
            db = _open_db()
            try:
                results = _parse_xls(Path(file.name))
                for prog in results:
                    db.clear_plan(prog["program"])
                    db.import_plan_subjects(prog["subjects"], prog["prerequisites"])
                msg = f"{len(results)} programa(s) importado(s)."
                programs = db.get_all_programs()
                return msg, gr.update(choices=programs, value=programs[0] if programs else None)
            except Exception as e:
                return f"Error: {e}", gr.update(choices=[], value=None)
            finally:
                db.close()

        def _refresh_programs() -> dict:
            db = _open_db()
            try:
                programs = db.get_all_programs()
                return gr.update(choices=programs, value=programs[0] if programs else None)
            finally:
                db.close()

        def _on_program_select(prog: str) -> tuple[list[list[Any]], list[list[Any]]]:
            if not prog:
                return [], []
            db = _open_db()
            try:
                subjects = db.get_plan_subjects(prog)
                rows = [
                    [s["code"], s["name"], s["credits"] or 0, s["semester"] or "", s["subject_type"]]
                    for s in subjects
                ]
                prereq_rows = []
                for s in subjects:
                    prereqs = db.get_prerequisites(s["code"], prog)
                    for p in prereqs:
                        prereq_rows.append([s["code"], p])
                return rows, prereq_rows
            finally:
                db.close()

        btn_import.click(fn=_do_import, inputs=[xls_file], outputs=[log_sp, program_drop])
        btn_refresh_sp.click(fn=_refresh_programs, outputs=program_drop)
        program_drop.change(fn=_on_program_select, inputs=[program_drop], outputs=[subjects_table, prereq_table])


# ── tab: parámetros ──


def _parameters_tab() -> None:
    with gr.TabItem("Parámetros"):
        gr.Markdown("### Parámetros persistentes del sistema")
        param_table = gr.Dataframe(
            label="Parámetros",
            headers=["Clave", "Valor", "Descripción", "Actualizado"],
            datatype=["str", "str", "str", "str"],
            column_count=4,
        )
        with gr.Row():
            key_in = gr.Textbox(label="Clave", scale=1)
            val_in = gr.Textbox(label="Valor", scale=1)
            desc_in = gr.Textbox(label="Descripción", scale=2)
        with gr.Row():
            btn_set = gr.Button("Establecer / Actualizar", variant="primary")
            btn_delete = gr.Button("Eliminar", variant="stop")
            btn_refresh_pm = gr.Button("Refrescar")
        log_pm = gr.Textbox(label="Log", lines=4, max_lines=20, interactive=False)

        def _list_params() -> list[list[Any]]:
            db = _open_db()
            try:
                return [
                    [p["key"], p["value"], p["description"] or "", p.get("updated_at", "")]
                    for p in db.get_all_parameters()
                ]
            finally:
                db.close()

        def _set_param(key: str, val: str, desc: str) -> tuple[str, list[list[Any]]]:
            if not key.strip():
                return "La clave no puede estar vacía.", []
            db = _open_db()
            try:
                db.set_parameter(key.strip(), val.strip(), desc.strip() or None)
                rows = [
                    [p["key"], p["value"], p["description"] or "", p.get("updated_at", "")]
                    for p in db.get_all_parameters()
                ]
                return f"Parámetro '{key}' guardado.", rows
            finally:
                db.close()

        def _delete_param(key: str) -> tuple[str, list[list[Any]]]:
            if not key.strip():
                return "Indica la clave a eliminar.", []
            db = _open_db()
            try:
                if db.delete_parameter(key.strip()):
                    rows = [
                        [p["key"], p["value"], p["description"] or "", p.get("updated_at", "")]
                        for p in db.get_all_parameters()
                    ]
                    return f"Parámetro '{key}' eliminado.", rows
                return f"Parámetro '{key}' no encontrado.", []
            finally:
                db.close()

        btn_refresh_pm.click(_list_params, outputs=param_table)
        btn_set.click(_set_param, inputs=[key_in, val_in, desc_in], outputs=[log_pm, param_table])
        btn_delete.click(_delete_param, inputs=[key_in], outputs=[log_pm, param_table])


# ── tab: elegibilidad ──


def _eligibility_tab() -> None:
    with gr.TabItem("Elegibilidad"):
        gr.Markdown("### Evaluaci\u00f3n de elegibilidad (Art\u00edculo 118)")
        with gr.Row():
            identity_input = gr.Textbox(
                label="C\u00e9dula / Identidad del estudiante",
                placeholder="Ej: V-12345678 (con V- si aplica)",
                scale=3,
            )
            current_period = gr.Textbox(
                label="Per\u00edodo actual",
                placeholder="Ej: 1-2025",
                scale=1,
            )
        btn_evaluate = gr.Button("Evaluar estudiante", variant="primary", size="lg")
        with gr.Row():
            with gr.Column(scale=1):
                veredict = gr.Markdown("### \u23F3 Esperando evaluaci\u00f3n...")
                student_info = gr.Markdown("")
            with gr.Column(scale=2):
                courses_table = gr.Dataframe(
                    label="Materias cursadas",
                    headers=["Periodo", "Semestre", "C\u00f3digo", "Nombre", "Nota", "Cr\u00e9d.", "Obs."],
                    datatype=["str", "str", "str", "str", "str", "number", "str"],
                    column_count=7,
                )
        art118_output = gr.Markdown("")
        prereq_output = gr.Markdown("")

        def _evaluate(id_doc: str, per: str) -> tuple[str, str, list[list[Any]], str, str]:
            id_doc = id_doc.strip()
            per = per.strip()
            if not id_doc:
                return ("### \u26A0 Ingresa una c\u00e9dula de identidad", "", [], "", "")

            db = _open_db()
            try:
                with db.connect() as conn:
                    count = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()
                    total_students = count["c"] if count else 0

                if total_students == 0:
                    return (
                        "### \u26A0 Base de datos vac\u00eda",
                        "No hay estudiantes en la base de datos. "
                        "Ejecuta el **Pipeline completo** en la pesta\u00f1a **Pipeline** primero.",
                        [], "", "",
                    )

                result = evaluate_student(db, id_doc, per)
                if result is None:
                    return (
                        "### \u274C Estudiante no encontrado",
                        f"No se encontr\u00f3 un estudiante con c\u00e9dula **{id_doc}**.\n\n"
                        f"Verifica que la c\u00e9dula sea correcta. "
                        f"Hay **{total_students}** estudiantes registrados en la base de datos.",
                        [], "", "",
                    )

                badge = "\U0001F7E2 **APTO**" if result["is_eligible"] else "\U0001F534 **NO APTO**"
                s = result
                info = (
                    f"**{s['full_name']}**  \n"
                    f"C\u00e9dula: {s['identity_document']}  |  "
                    f"Matr\u00edcula: {s.get('student_id', '?')}  |  "
                    f"Programa: {s['program']}  \n"
                    f"\u00cdndice acad\u00e9mico: {s.get('academic_index', 'N/A')}  |  "
                    f"Per\u00edodos cursados: {s.get('periods_completed', '?')}"
                )

                from academic_audit.eligibility import get_student_courses
                courses = get_student_courses(db, id_doc)
                course_rows = [
                    [
                        c.get("period", ""),
                        c.get("semester", ""),
                        c.get("code", ""),
                        c.get("name", ""),
                        str(c.get("grade", "")),
                        c.get("credits") or "",
                        c.get("observation", ""),
                    ]
                    for c in courses
                ]

                art118 = result.get("article_118_violations", [])
                art118_text = "**Violaciones Art\u00edculo 118:**  \n" + (
                    "\n".join(f"- {v}" for v in art118) if art118 else "_Ninguna_"
                )

                prereq = result.get("prereq_issues", [])
                prereq_text = "**Prelaciones incumplidas:**  \n" + (
                    "\n".join(f"- {p}" for p in prereq) if prereq else "_Ninguna_"
                )

                return badge, info, course_rows, art118_text, prereq_text
            except Exception as e:
                logger.exception("Error evaluando estudiante")
                return (
                    f"### \u274C Error: {e}",
                    "Revisa la terminal para m\u00e1s detalles.",
                    [], "", "",
                )
            finally:
                db.close()

        btn_evaluate.click(
            fn=_evaluate,
            inputs=[identity_input, current_period],
            outputs=[veredict, student_info, courses_table, art118_output, prereq_output],
        )


# ── launch ──


def launch(db_path: str | None = None, port: int = 7860) -> None:
    global _GUI_DB_PATH
    if db_path:
        _GUI_DB_PATH = Path(db_path).resolve()
    _GUI_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    CUSTOM_CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&display=swap');

    * { box-sizing: border-box; }

    body, .gradio-container {
        font-family: 'Inter', -apple-system, sans-serif;
        background: #0d0d0f;
        color: #e8e8e4;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }

    .gradio-container {
        max-width: 1320px !important;
        margin: 0 auto;
        padding: 2.5rem 2rem !important;
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        letter-spacing: -0.022em;
        color: #f0f0ec;
    }

    /* ── HEADER ── */

    .header-section {
        padding: 2rem 2rem 1.75rem;
        margin-bottom: 2rem;
        background: #161618;
        border-radius: 16px;
        border: 1px solid #222226;
    }

    .app-header h1 {
        font-size: 1.65rem;
        font-weight: 650;
        color: #f0f0ec;
        margin: 0 0 0.35rem 0;
        letter-spacing: -0.025em;
        line-height: 1.2;
    }

    .app-header p {
        font-size: 0.9rem;
        color: #6b6b70;
        margin: 0;
        font-weight: 400;
    }

    /* ── TABS ── */

    .tabs {
        border: none !important;
        margin-bottom: 1.5rem;
    }

    .tab-nav {
        border-bottom: none !important;
        gap: 0.25rem !important;
        background: #161618;
        padding: 0.5rem;
        border-radius: 12px;
        border: 1px solid #222226;
        display: flex;
        flex-wrap: wrap;
    }

    .tab-nav button {
        font-family: 'Inter', sans-serif;
        font-size: 0.8125rem;
        font-weight: 500;
        color: #6b6b70;
        padding: 0.55rem 1.1rem;
        border: none !important;
        border-radius: 8px !important;
        background: transparent !important;
        transition: all 0.2s ease;
        cursor: pointer;
        white-space: nowrap;
    }

    .tab-nav button:hover {
        color: #e8e8e4;
        background: #222226 !important;
    }

    .tab-nav button.selected {
        color: #f0f0ec !important;
        background: #2a2a2e !important;
        font-weight: 550;
    }

    /* ── PANELS / CARDS ── */

    .panel, .gr-box, .gr-form, .gr-panel {
        border: 1px solid #222226 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
        background: #161618;
        padding: 1.25rem !important;
    }

    .gr-box:empty, .gr-panel:empty { display: none; }

    /* ── BUTTONS ── */

    button, .gr-button {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        font-size: 0.8125rem;
        border-radius: 8px !important;
        border: 1px solid #2a2a2e !important;
        background: #1a1a1e;
        color: #e8e8e4;
        padding: 0.5rem 1.1rem;
        transition: all 0.2s ease;
        cursor: pointer;
        line-height: 1.4;
    }

    button:hover, .gr-button:hover {
        background: #222226;
        border-color: #3a3a3e !important;
    }

    button:active, .gr-button:active {
        transform: scale(0.98);
    }

    .gr-button.primary, button.primary {
        background: #f0f0ec;
        color: #0d0d0f;
        border-color: #f0f0ec !important;
        font-weight: 550;
    }

    .gr-button.primary:hover, button.primary:hover {
        background: #ffffff;
        border-color: #ffffff !important;
    }

    .gr-button.stop, button.stop {
        background: #1a1a1e;
        color: #e85a6f;
        border-color: #3a1a22 !important;
    }

    .gr-button.stop:hover, button.stop:hover {
        background: #222226;
        color: #f47082;
        border-color: #5a202a !important;
    }

    .gr-button.size-lg, button.size-lg {
        padding: 0.6rem 1.5rem;
        font-size: 0.85rem;
    }

    .gr-button.size-sm, button.size-sm {
        padding: 0.35rem 0.85rem;
        font-size: 0.75rem;
    }

    /* ── INPUTS ── */

    input, textarea, select {
        font-family: 'Inter', sans-serif;
        border: 1px solid #2a2a2e !important;
        border-radius: 8px !important;
        font-size: 0.875rem;
        padding: 0.55rem 0.8rem !important;
        transition: all 0.2s ease;
        color: #e8e8e4;
        background: #1a1a1e;
    }

    input:focus, textarea:focus, select:focus {
        border-color: #6b6b70 !important;
        box-shadow: 0 0 0 3px rgba(255,255,255,0.04) !important;
        outline: none;
    }

    input::placeholder, textarea::placeholder {
        color: #515154;
    }

    label, .gr-label {
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        font-size: 0.8rem;
        color: #8a8a88;
        margin-bottom: 0.35rem;
        letter-spacing: 0.01em;
    }

    /* ── TABLES ── */

    table, .gr-dataframe {
        border-collapse: collapse;
        font-family: 'Inter', sans-serif;
        font-size: 0.8125rem;
        width: 100%;
        border-radius: 8px;
        overflow: hidden;
    }

    thead, th {
        background: #1a1a1e !important;
        font-weight: 550;
        color: #aeaeb2;
        padding: 0.65rem 0.85rem;
        border-bottom: 1px solid #2a2a2e;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    td {
        padding: 0.55rem 0.85rem;
        border-bottom: 1px solid #222226;
        color: #d4d4d0;
    }

    tr:last-child td { border-bottom: none; }

    tr:hover td { background: #1a1a1e; }

    .gr-dataframe td:first-child,
    .gr-dataframe th:first-child {
        padding-left: 1rem;
    }

    /* ── MARKDOWN ── */

    .gr-markdown {
        font-family: 'Inter', sans-serif;
        color: #d4d4d0;
        line-height: 1.65;
    }

    .gr-markdown h3 {
        color: #f0f0ec;
        font-size: 1rem;
        font-weight: 600;
        margin: 0 0 0.65rem 0;
        letter-spacing: -0.02em;
    }

    .gr-markdown p {
        color: #8a8a88;
        margin: 0 0 0.5rem 0;
    }

    .gr-markdown strong {
        font-weight: 600;
        color: #f0f0ec;
    }

    /* ── LOG / TEXTBOX ── */

    .gr-textbox textarea {
        font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
        font-size: 0.8rem;
        line-height: 1.6;
        color: #b8b8b2;
        background: #111113;
        border-color: #222226 !important;
    }

    /* ── SLIDER ── */

    .gr-slider input {
        border: none !important;
        box-shadow: none !important;
    }

    /* ── FOOTER ── */

    footer { display: none !important; }

    .footer-section {
        margin-top: 2rem;
        padding: 1.25rem 1.5rem;
        background: #161618;
        border-radius: 12px;
        border: 1px solid #222226;
    }

    .footer-content {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        margin-bottom: 0.75rem;
    }

    .footer-db {
        font-size: 0.8rem;
        color: #6b6b70;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .footer-db strong {
        color: #8a8a88;
        font-weight: 550;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .footer-db code {
        font-family: 'SF Mono', 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        color: #aeaeb2;
        background: #1a1a1e;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
    }

    .footer-hint {
        font-size: 0.78rem;
        color: #515154;
    }

    /* ── CHECKBOX ── */

    .gr-checkbox {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
    }

    .gr-checkbox label {
        color: #d4d4d0 !important;
        font-weight: 450;
    }

    .gr-checkbox .info-text {
        color: #6b6b70 !important;
        font-size: 0.8rem;
    }

    /* ── ROW SPACING ── */

    .gr-row {
        gap: 0.75rem !important;
    }

    .gr-form, .gr-box, .contains-errors {
        color: #d4d4d0;
    }

    .status-text {
        color: #6b6b70;
        font-size: 0.8rem;
    }

    /* ── SCROLLBAR ── */

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #2a2a2e; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #3a3a3e; }

    /* ── ANIMATIONS ── */

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
    }

    .tabitem { animation: fadeIn 0.25s ease; }

    /* ── RESPONSIVE ── */

    @media (max-width: 768px) {
        .gradio-container { padding: 1.25rem 1rem !important; }
        .header-section { padding: 1.25rem; }
        .tab-nav button { font-size: 0.75rem; padding: 0.4rem 0.75rem; }
    }
    """

    THEME = gr.themes.Base(
        primary_hue=gr.themes.Color(
            c50="#1a1a1e",
            c100="#222226",
            c200="#2a2a2e",
            c300="#3a3a3e",
            c400="#515154",
            c500="#f0f0ec",
            c600="#ffffff",
            c700="#ffffff",
            c800="#ffffff",
            c900="#ffffff",
            c950="#ffffff",
        ),
        neutral_hue=gr.themes.Color(
            c50="#111113",
            c100="#161618",
            c200="#1a1a1e",
            c300="#222226",
            c400="#2a2a2e",
            c500="#515154",
            c600="#6b6b70",
            c700="#8a8a88",
            c800="#aeaeb2",
            c900="#d4d4d0",
            c950="#f0f0ec",
        ),
        font=gr.themes.GoogleFont("Inter"),
        font_mono=gr.themes.GoogleFont("JetBrains Mono"),
    )

    with gr.Blocks(title="Academic Records Audit") as app:
        with gr.Column():
            with gr.Column(elem_classes="header-section"):
                gr.HTML(
                    '<div class="app-header">'
                    '<h1>Academic Records Audit</h1>'
                    '<p>Procesamiento y consulta de expedientes acad\u00e9micos</p>'
                    '</div>'
                )

            _pipeline_tab()
            _study_plan_tab()
            _parameters_tab()
            _eligibility_tab()

            with gr.Column(elem_classes="footer-section"):
                gr.HTML(
                    f'<div class="footer-content">'
                    f'<span class="footer-db"><strong>DB</strong> <code>{_GUI_DB_PATH}</code></span>'
                    f'<span class="footer-hint">academic-audit --help para uso avanzado</span>'
                    f'</div>'
                )
                with gr.Row():
                    delete_checkbox = gr.Checkbox(
                        label="Borrar BD al cerrar",
                        info=f"Elimina permanentemente {_GUI_DB_PATH.name} al salir",
                    )
                with gr.Row():
                    btn_delete_db = gr.Button(
                        "Eliminar ahora",
                        variant="stop", size="sm",
                    )
                    db_status = gr.Textbox(
                        label="", lines=1, max_lines=1, interactive=False, scale=3,
                    )

        def _delete_db_click(checkbox_val: bool) -> str:
            result = _delete_db()
            if checkbox_val:
                result += "  |  La opci\u00f3n 'Borrar al cerrar' est\u00e1 activa."
            return result

        btn_delete_db.click(
            fn=_delete_db_click, inputs=[delete_checkbox], outputs=db_status,
            api_name="delete_db",
        )

    CLOSE_JS = f"""
    <script>
    (function() {{
        const STORAGE_KEY = 'gui_delete_db_on_close';
        const checkboxSelector = 'input[type="checkbox"]';

        function persistCheckbox() {{
            const cb = document.querySelector(checkboxSelector);
            if (cb) {{
                const val = cb.checked ? 'true' : 'false';
                try {{ localStorage.setItem(STORAGE_KEY, val); }} catch(e) {{}}
            }}
        }}

        setInterval(persistCheckbox, 1000);

        document.addEventListener('change', function(e) {{
            if (e.target.matches(checkboxSelector)) persistCheckbox();
        }});

        function shouldDelete() {{
            try {{ return localStorage.getItem(STORAGE_KEY) === 'true'; }} catch(e) {{ return false; }}
        }}

        function sendDelete() {{
            if (shouldDelete()) {{
                var blob = new Blob(
                    [JSON.stringify({{data: [true]}})],
                    {{type: 'application/json'}}
                );
                navigator.sendBeacon('/gradio_api/run/delete_db/', blob);
            }}
        }}

        window.addEventListener('pagehide', sendDelete);
        window.addEventListener('beforeunload', function(e) {{
            if (shouldDelete()) {{
                e.preventDefault();
                e.returnValue = '';
                sendDelete();
            }}
        }});
    }})();
    </script>
    """

    app.queue(default_concurrency_limit=1)
    app.launch(
        server_port=port,
        server_name="127.0.0.1",
        show_error=True,
        theme=THEME,
        css=CUSTOM_CSS,
        js=CLOSE_JS,
    )
