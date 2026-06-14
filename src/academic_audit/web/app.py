from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from academic_audit.config import Paths
from academic_audit.convert import convert_folder as _convert_folder
from academic_audit.database import Database
from academic_audit.eligibility import (
    evaluate_student,
    get_student_courses,
)
from academic_audit.extract import extract_folder as _extract_folder
from academic_audit.pipeline import run_pipeline as _run_pipeline
from academic_audit.report import REGISTRY as _REPORT_REGISTRY, generate_reports as _generate_reports
from academic_audit.study_plan import parse_xls as _parse_xls
from academic_audit.query import ask_query as _ask_query
from academic_audit.web.tasks import TaskManager

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_GUI_DB_PATH = Path.cwd() / "data" / "audit.db"


def _open_db(db_path: Path | None = None) -> Database:
    p = db_path or _GUI_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    db = Database(p, memory=False)
    db.init_schema()
    return db


def _resolve_path(val: str) -> Path | None:
    val = val.strip()
    if not val:
        return None
    p = Path(val)
    return p if p.is_absolute() else Path.cwd() / p


# ── App factory ──

task_manager = TaskManager()

app = FastAPI(title="Academic Records Audit")

app.mount(
    "/static",
    StaticFiles(directory=str(_HERE / "static")),
    name="static",
)
_jinja_env = Environment(
    loader=FileSystemLoader(str(_HERE / "templates")),
    autoescape=select_autoescape(["html"]),
)


def _render(name: str, **ctx: object) -> str:
    return _jinja_env.get_template(name).render(**ctx)


# ── HTML routes ──


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_render("index.html", db_path=str(_GUI_DB_PATH)))


@app.get("/tabs/{tab_name}", response_class=HTMLResponse)
def get_tab(tab_name: str) -> HTMLResponse:
    ctx: dict[str, Any] = {}

    if tab_name == "pipeline":
        ctx["paths"] = Paths()
    elif tab_name == "parameters":
        db = _open_db()
        try:
            ctx["params"] = db.get_all_parameters()
        finally:
            db.close()
    elif tab_name == "study_plan":
        db = _open_db()
        try:
            ctx["programs"] = db.get_all_programs()
        finally:
            db.close()

    return HTMLResponse(_render(f"tabs/{tab_name}.html", **ctx))


# ── Pipeline API ──


def _launch_task(desc: str, fn: Any, *args: Any) -> dict[str, str]:
    task_id = task_manager.start_task(desc, fn, *args)
    return {"task_id": task_id}


def _task_convert(pdf_dir_str: str, md_dir_str: str, workers: int) -> None:
    pdf = _resolve_path(pdf_dir_str)
    md = _resolve_path(md_dir_str)
    db = _open_db()
    try:
        _convert_folder(
            pdf or Paths.pdf_dir,
            md or Paths.markdown_dir,
            db,
            recursive=True,
            workers=workers,
        )
    finally:
        db.close()


def _task_extract(md_dir_str: str, pdf_dir_str: str) -> None:
    md = _resolve_path(md_dir_str) or Paths().markdown_dir
    pdf = _resolve_path(pdf_dir_str) or md
    db = _open_db()
    try:
        _extract_folder(md, db, pdf_dir=pdf, recursive=True)
    finally:
        db.close()


def _task_pipeline(
    pdf_dir_str: str,
    md_dir_str: str,
    insc_dir_str: str,
    insc_md_dir_str: str,
    report_dir_str: str,
    workers: int,
) -> None:
    paths = Paths(
        pdf_dir=_resolve_path(pdf_dir_str) or Paths.pdf_dir,
        markdown_dir=_resolve_path(md_dir_str) or Paths.markdown_dir,
        inscripcion_dir=_resolve_path(insc_dir_str) or Paths.inscripcion_dir,
        inscripcion_md_dir=_resolve_path(insc_md_dir_str) or Paths.inscripcion_md_dir,
        db_path=_GUI_DB_PATH,
        report_dir=_resolve_path(report_dir_str) or Paths.report_dir,
    )
    db = _open_db()
    try:
        _run_pipeline(paths, recursive=True, memory=False, workers=workers, report=False)
    finally:
        db.close()


def _task_reports(report_dir_str: str) -> None:
    db = _open_db()
    try:
        _generate_reports(db, _resolve_path(report_dir_str) or Paths.report_dir)
    finally:
        db.close()


@app.post("/api/pipeline/convert")
def api_pipeline_convert(
    pdf_dir: str = Form(""),
    md_dir: str = Form(""),
    workers: int = Form(3),
) -> dict[str, str]:
    return _launch_task("convertir", _task_convert, pdf_dir, md_dir, int(workers))


@app.post("/api/pipeline/extract")
def api_pipeline_extract(
    md_dir: str = Form(""),
    pdf_dir: str = Form(""),
) -> dict[str, str]:
    return _launch_task("extraer", _task_extract, md_dir, pdf_dir)


@app.post("/api/pipeline/run")
def api_pipeline_run(
    pdf_dir: str = Form(""),
    md_dir: str = Form(""),
    insc_dir: str = Form(""),
    insc_md_dir: str = Form(""),
    report_dir: str = Form(""),
    workers: int = Form(3),
) -> dict[str, str]:
    return _launch_task(
        "pipeline", _task_pipeline,
        pdf_dir, md_dir, insc_dir, insc_md_dir, report_dir, int(workers),
    )


@app.post("/api/pipeline/reports")
def api_pipeline_reports(
    report_dir: str = Form(""),
) -> dict[str, str]:
    return _launch_task("reportes", _task_reports, report_dir)


# ── SSE stream ──


@app.get("/api/tasks/{task_id}/stream")
def task_stream(task_id: str) -> StreamingResponse:
    return StreamingResponse(
        task_manager.event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Study Plan API ──


@app.post("/api/study-plan/import")
def api_study_plan_import(file: UploadFile) -> JSONResponse:
    if not file.filename or not file.filename.endswith(".xls"):
        return JSONResponse(
            {"message": "Selecciona un archivo .xls", "programs": []}, status_code=400
        )

    tmp = Path.cwd() / "data" / "_upload.xls"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)

        db = _open_db()
        try:
            results = _parse_xls(tmp)
            for prog in results:
                db.clear_plan(prog["program"])
                db.import_plan_subjects(prog["subjects"], prog["prerequisites"])
            programs = db.get_all_programs()
            return JSONResponse(
                {
                    "message": f"{len(results)} programa(s) importado(s)",
                    "programs": programs,
                }
            )
        finally:
            db.close()
    except Exception as e:
        logger.exception("Error importando plan")
        return JSONResponse({"message": f"Error: {e}", "programs": []}, status_code=500)
    finally:
        if tmp.exists():
            tmp.unlink()


@app.get("/api/study-plan/programs")
def api_study_plan_programs() -> JSONResponse:
    db = _open_db()
    try:
        programs = db.get_all_programs()
        return JSONResponse({"programs": programs})
    finally:
        db.close()


@app.get("/api/study-plan/subjects/{program}")
def api_study_plan_subjects(program: str) -> HTMLResponse:
    db = _open_db()
    try:
        subjects = db.get_plan_subjects(program)
        rows = [
            {
                "code": s["code"],
                "name": s["name"],
                "credits": s["credits"] or 0,
                "semester": s["semester"] or "",
                "type": s["subject_type"],
            }
            for s in subjects
        ]
        return HTMLResponse(
            _render("tabs/_subjects_table.html", subjects=rows)
        )
    finally:
        db.close()


@app.get("/api/study-plan/prerequisites/{program}")
def api_study_plan_prerequisites(program: str) -> HTMLResponse:
    db = _open_db()
    try:
        subjects = db.get_plan_subjects(program)
        prereq_rows: list[dict[str, str]] = []
        for s in subjects:
            prereqs = db.get_prerequisites(s["code"], program)
            for p in prereqs:
                prereq_rows.append({"subject": s["code"], "prereq": p})
        return HTMLResponse(
            _render("tabs/_prereq_table.html", prereqs=prereq_rows)
        )
    finally:
        db.close()


# ── Parameters API ──


@app.get("/api/parameters")
def api_parameters_list() -> HTMLResponse:
    db = _open_db()
    try:
        params = db.get_all_parameters()
        return HTMLResponse(_render("tabs/_param_rows.html", params=params))
    finally:
        db.close()


@app.post("/api/parameters/set")
def api_parameters_set(
    key: str = Form(""),
    value: str = Form(""),
    description: str = Form(""),
) -> JSONResponse:
    if not key.strip():
        return JSONResponse({"message": "La clave no puede estar vacía"}, status_code=400)

    db = _open_db()
    try:
        db.set_parameter(key.strip(), value.strip(), description.strip() or None)
        params = db.get_all_parameters()
        html = _render("tabs/_param_rows.html", params=params)
        return JSONResponse(
            {"message": f"Parámetro '{key}' guardado", "html": html}
        )
    finally:
        db.close()


@app.post("/api/parameters/delete")
def api_parameters_delete(
    key: str = Form(""),
) -> JSONResponse:
    if not key.strip():
        return JSONResponse({"message": "Indica la clave a eliminar"}, status_code=400)

    db = _open_db()
    try:
        if db.delete_parameter(key.strip()):
            params = db.get_all_parameters()
            html = _render("tabs/_param_rows.html", params=params)
            return JSONResponse(
                {"message": f"Parámetro '{key}' eliminado", "html": html}
            )
        return JSONResponse(
            {"message": f"Parámetro '{key}' no encontrado"}, status_code=404
        )
    finally:
        db.close()


# ── Eligibility API ──


@app.post("/api/eligibility/evaluate")
def api_eligibility_evaluate(
    identity: str = Form(""),
    period: str = Form(""),
) -> JSONResponse:
    identity = identity.strip()
    period = period.strip()

    if not identity:
        return JSONResponse(
            {
                "veredict": "### Ingresa una c\u00e9dula de identidad",
                "student_info": "",
                "courses": [],
                "art118": "",
                "prereq": "",
            }
        )

    db = _open_db()
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM students"
            ).fetchone()
            total_students = row["c"] if row else 0

        if total_students == 0:
            return JSONResponse(
                {
                    "veredict": "### Base de datos vac\u00eda",
                    "student_info": "No hay estudiantes. Ejecuta el Pipeline primero.",
                    "courses": [],
                    "art118": "",
                    "prereq": "",
                }
            )

        result = evaluate_student(db, identity, period)
        if result is None:
            return JSONResponse(
                {
                    "veredict": "### Estudiante no encontrado",
                    "student_info": f"No se encontr\u00f3 un estudiante con c\u00e9dula **{identity}**.",
                    "courses": [],
                    "art118": "",
                    "prereq": "",
                }
            )

        s = result
        is_eligible = s["is_eligible"]
        badge = "🟢 **APTO**" if is_eligible else "🔴 **NO APTO**"
        info = (
            f"**{s['full_name']}**  \n"
            f"Cédula: {s['identity_document']}  |  "
            f"Matrícula: {s.get('student_id', '?')}  |  "
            f"Programa: {s['program']}  \n"
            f"Índice académico: {s.get('academic_index', 'N/A')}  |  "
            f"Períodos cursados: {s.get('periods_completed', '?')}"
        )

        courses = get_student_courses(db, identity)
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
        art118_text = (
            "**Violaciones Artículo 118:**\n"
            + ("\n".join(f"- {v}" for v in art118) if art118 else "_Ninguna_")
        )

        prereq = result.get("prereq_issues", [])
        prereq_text = (
            "**Prelaciones incumplidas:**\n"
            + ("\n".join(f"- {p}" for p in prereq) if prereq else "_Ninguna_")
        )

        return JSONResponse(
            {
                "veredict": badge,
                "student_info": info,
                "courses": course_rows,
                "art118": art118_text,
                "prereq": prereq_text,
            }
        )
    except Exception as e:
        logger.exception("Error evaluando estudiante")
        return JSONResponse(
            {
                "veredict": f"### Error: {e}",
                "student_info": "Revisa la terminal para más detalles.",
                "courses": [],
                "art118": "",
                "prereq": "",
            }
        )
    finally:
        db.close()


# ── Database API ──


@app.post("/api/db/delete")
def api_db_delete() -> JSONResponse:
    try:
        if _GUI_DB_PATH.exists():
            size = _GUI_DB_PATH.stat().st_size
            _GUI_DB_PATH.unlink()
            return JSONResponse(
                {"message": f"Base de datos eliminada ({size:,} bytes)"}
            )
        return JSONResponse({"message": "La base de datos no existe"})
    except Exception as e:
        logger.exception("Error eliminando BD")
        return JSONResponse({"message": f"Error al eliminar: {e}"}, status_code=500)


@app.get("/api/db/info")
def api_db_info() -> JSONResponse:
    exists = _GUI_DB_PATH.exists()
    size = _GUI_DB_PATH.stat().st_size if exists else 0
    return JSONResponse(
        {
            "path": str(_GUI_DB_PATH),
            "exists": exists,
            "size": size,
            "name": _GUI_DB_PATH.name,
        }
    )


# ── Query API ──


_GROQ_API_KEY_PARAM = "groq_api_key"


def _get_saved_api_key(db: Database) -> str | None:
    return db.get_parameter(_GROQ_API_KEY_PARAM)


@app.post("/api/query/ask")
def api_query_ask(
    question: str = Form(""),
    model: str = Form("qwen-2.5-coder-32b"),
    api_key: str | None = Form(None),
) -> JSONResponse:
    if not question.strip():
        return JSONResponse(
            {"sql": None, "results": None, "error": "Escribe una pregunta"}
        )

    db = _open_db()
    try:
        key = api_key or _get_saved_api_key(db) or None
        result = _ask_query(db, question.strip(), model, key)
        return JSONResponse(result)
    finally:
        db.close()


@app.post("/api/query/save-key")
def api_query_save_key(api_key: str = Form("")) -> JSONResponse:
    if not api_key.strip():
        return JSONResponse({"message": "API key vacía, no se guardó"})
    db = _open_db()
    try:
        db.set_parameter(
            _GROQ_API_KEY_PARAM,
            api_key.strip(),
            description="API Key de Groq para consultas IA",
        )
        return JSONResponse({"message": "API key guardada en parámetros"})
    finally:
        db.close()


@app.post("/api/query/delete-key")
def api_query_delete_key() -> JSONResponse:
    db = _open_db()
    try:
        if db.delete_parameter(_GROQ_API_KEY_PARAM):
            return JSONResponse({"message": "API key eliminada"})
        return JSONResponse({"message": "No hay API key guardada"})
    finally:
        db.close()


@app.get("/api/query/key-status")
def api_query_key_status() -> JSONResponse:
    db = _open_db()
    try:
        key = _get_saved_api_key(db)
        return JSONResponse({"configured": key is not None})
    finally:
        db.close()


# ── Reports API ──

_REPORT_DIR = Path.cwd() / "reports"


@app.get("/api/reports/list")
def api_reports_list() -> JSONResponse:
    report_dir = _REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    for name, cls in _REPORT_REGISTRY.items():
        r = cls()
        fp = report_dir / r.filename
        info: dict[str, Any] = {
            "name": name,
            "filename": r.filename,
            "label": r.label,
            "exists": fp.exists(),
        }
        if fp.exists():
            s = fp.stat()
            info["size"] = s.st_size
            info["size_human"] = _human_size(s.st_size)
            info["modified"] = s.st_mtime
        else:
            info["size"] = 0
            info["size_human"] = ""
            info["modified"] = None
        reports.append(info)
    return JSONResponse({"reports": reports})


@app.post("/api/reports/generate/{report_name}")
def api_reports_generate(report_name: str) -> JSONResponse:
    if report_name != "all" and report_name not in _REPORT_REGISTRY:
        return JSONResponse(
            {"message": f"Reporte '{report_name}' no encontrado"}, status_code=404
        )
    db = _open_db()
    try:
        names = None if report_name == "all" else [report_name]
        paths = _generate_reports(db, _REPORT_DIR, report_names=names)
        return JSONResponse({
            "message": f"{len(paths)} reporte(s) generado(s)",
            "files": [p.name for p in paths],
        })
    finally:
        db.close()


@app.get("/api/reports/preview/{report_name}")
def api_reports_preview(report_name: str) -> JSONResponse:
    cls = _REPORT_REGISTRY.get(report_name)
    if not cls:
        return JSONResponse({"error": "Reporte no encontrado"}, status_code=404)

    report = cls()
    fp = _REPORT_DIR / report.filename

    if not fp.exists():
        db = _open_db()
        try:
            report.write(db, _REPORT_DIR)
        finally:
            db.close()

    if not fp.exists():
        return JSONResponse({"headers": [], "rows": [], "message": "No se pudo generar el reporte"})

    import csv
    with fp.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    headers = rows[0] if rows else []
    data = rows[1:] if len(rows) > 1 else []
    return JSONResponse({"headers": headers, "rows": data, "filename": report.filename})


@app.get("/api/reports/download/{report_name}", response_model=None)
def api_reports_download(report_name: str):
    cls = _REPORT_REGISTRY.get(report_name)
    if not cls:
        return JSONResponse({"error": "Reporte no encontrado"}, status_code=404)
    report = cls()
    fp = _REPORT_DIR / report.filename
    if not fp.exists():
        return JSONResponse({"error": "Reporte no generado"}, status_code=404)
    return FileResponse(fp, media_type="text/csv", filename=report.filename)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# ── Run ──


def run(host: str = "127.0.0.1", port: int = 8000, db_path: Path | None = None) -> None:
    global _GUI_DB_PATH
    if db_path:
        _GUI_DB_PATH = db_path.resolve()
    _GUI_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Iniciando servidor en http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
