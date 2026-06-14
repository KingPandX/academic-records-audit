from __future__ import annotations

from pathlib import Path

from academic_audit.report import (
    REGISTRY,
    StudentCoursesReport,
    StudentStatsReport,
    generate_reports,
)

from conftest import seed_plan, seed_student, seed_course, seed_enrollment


def test_registry_has_all_reporters():
    assert "student_courses" in REGISTRY
    assert "eligibility" in REGISTRY
    assert "student_stats" in REGISTRY


def test_student_courses_report_columns():
    report = StudentCoursesReport()
    assert "student_id" in report.columns
    assert "program" in report.columns
    assert "period" in report.columns
    assert "code" in report.columns
    assert report.filename == "estudiantes-materias.csv"


def test_student_courses_report_data(db, tmp_path):
    seed_plan(db)
    doc_id = seed_student(db, identity_document="V-001")
    seed_course(db, doc_id, code="MAT-101", name="MATEMÁTICA I", semester="1",
                identity_document="V-001")

    report = StudentCoursesReport()
    data = report.query_data(db)
    assert len(data) == 1
    row = data[0]
    assert row["student_id"] == "1-2021-V-001"
    assert row["code"] == "MAT-101"
    assert row["program"] == "INGENIERÍA DE PRUEBA"


def test_student_stats_report_columns():
    report = StudentStatsReport()
    assert report.filename == "estadisticas-carreras.csv"
    assert "Carrera" in report.columns
    assert "Tipo" in report.columns
    assert "I" in report.columns
    assert "X" in report.columns


def test_student_stats_report_data(db):
    seed_plan(db)
    doc_id = seed_student(db, identity_document="V-001", periods_completed=1)
    seed_course(db, doc_id, code="MAT-101", name="MATEMÁTICA I", semester="1",
                identity_document="V-001", grade="15")
    seed_enrollment(db, identity_document="V-001", subjects=[
        {"code": "MAT-101", "name": "MATEMÁTICA I"},
        {"code": "FIS-101", "name": "FÍSICA I"},
    ])

    report = StudentStatsReport()
    data = report.query_data(db)
    assert len(data) == 3
    regular = [r for r in data if r["Tipo"] == "Regular"][0]
    assert regular["I"] == 1


def test_generate_reports_writes_csv(db, tmp_path):
    seed_plan(db)
    doc_id = seed_student(db, identity_document="V-001")
    seed_course(db, doc_id, code="MAT-101", name="MATEMATICA I", semester="1",
                identity_document="V-001")

    paths = generate_reports(db, tmp_path, report_names=["student_courses"])
    assert len(paths) == 1
    assert paths[0].exists()
    content = paths[0].read_text(encoding="utf-8")
    assert "student_id" in content
    assert "MAT-101" in content


def test_multiple_students_in_report(db, tmp_path):
    seed_plan(db)
    for suf in ("001", "002"):
        doc_id = seed_student(db, identity_document=f"V-{suf}")
        seed_course(db, doc_id, code="MAT-101", identity_document=f"V-{suf}",
                    name="MATEMÁTICA I", semester="1")

    paths = generate_reports(db, tmp_path, report_names=["student_courses"])
    lines = paths[0].read_text(encoding="utf-8").strip().split("\n")
    data_lines = lines[1:]
    student_ids = [line.split(",")[0] for line in data_lines]
    assert student_ids.count("1-2021-V-001") == 1
    assert student_ids.count("1-2021-V-002") == 1


def test_unknown_report_name_skipped(db, tmp_path):
    paths = generate_reports(db, tmp_path, report_names=["nonexistent"])
    assert paths == []
