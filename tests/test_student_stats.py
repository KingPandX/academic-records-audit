from __future__ import annotations

from academic_audit.student_stats import (
    classify_student,
    compute_stats_pivot,
)

from conftest import seed_student, seed_course, seed_enrollment, seed_plan


def test_classify_regular(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=3)
    seed_course(db, doc_id, code="MAT-301", name="MATEMÁTICA III", semester="3",
                period="1-2024", grade="15")
    seed_course(db, doc_id, code="PRO-301", name="PROGRAMACIÓN I", semester="3",
                period="1-2024", grade="14")
    seed_enrollment(db, subjects=[
        {"code": "MAT-301", "name": "MATEMÁTICA III"},
        {"code": "PRO-301", "name": "PROGRAMACIÓN I"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "regular"
    assert result["effective_semester"] == 3
    assert result["expected_semester"] == 3


def test_classify_repitiente_materia_reprobada_previamente(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=3)
    seed_course(db, doc_id, code="MAT-201", name="MATEMÁTICA II", semester="2",
                period="1-2024", grade="08")
    seed_course(db, doc_id, code="MAT-301", name="MATEMÁTICA III", semester="3",
                period="1-2024", grade="15")
    seed_enrollment(db, subjects=[
        {"code": "MAT-201", "name": "MATEMÁTICA II"},
        {"code": "MAT-301", "name": "MATEMÁTICA III"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "repitiente"
    assert result["effective_semester"] == 3


def test_classify_repitiente_sin_retraso_materia_reprobada(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=2, study_plan_period=2)
    seed_course(db, doc_id, code="MAT-201", name="MATEMÁTICA II", semester="2",
                period="1-2024", grade="08")
    seed_enrollment(db, subjects=[
        {"code": "MAT-201", "name": "MATEMÁTICA II"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "repitiente"
    assert result["effective_semester"] == 2
    assert result["expected_semester"] == 2


def test_classify_desfasado_retrasado_segun_corte(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=3, study_plan_period=4)
    seed_course(db, doc_id, code="MAT-101", name="MATEMÁTICA I", semester="1",
                period="1-2023", grade="10")
    seed_course(db, doc_id, code="MAT-201", name="MATEMÁTICA II", semester="2",
                period="1-2024", grade="08")
    seed_enrollment(db, subjects=[
        {"code": "MAT-101", "name": "MATEMÁTICA I"},
        {"code": "FIS-101", "name": "FÍSICA I"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "desfasado"
    assert result["expected_semester"] == 4
    assert result["effective_semester"] == 1


def test_classify_desfasado_prioritario_sobre_repitiente(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=4, study_plan_period=4)
    seed_course(db, doc_id, code="MAT-101", name="MATEMÁTICA I", semester="1",
                period="1-2023", grade="08")
    seed_course(db, doc_id, code="FIS-101", name="FÍSICA I", semester="1",
                period="1-2023", grade="10")
    seed_enrollment(db, subjects=[
        {"code": "MAT-101", "name": "MATEMÁTICA I"},
        {"code": "FIS-101", "name": "FÍSICA I"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "desfasado"
    assert result["expected_semester"] == 4
    assert result["effective_semester"] == 1


def test_classify_cinu(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=0)
    seed_course(db, doc_id, code="CINU101", name="CINU", semester="0",
                period="2-2024", grade="APROBÓ", course_type="cinu")
    seed_enrollment(db, subjects=[
        {"code": "CINU101", "name": "CINU"},
    ])

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "regular"
    assert result["expected_semester"] == 0
    assert result["effective_semester"] == 0


def test_classify_fallback_to_courses(db):
    seed_plan(db)
    doc_id = seed_student(db, periods_completed=2)
    seed_course(db, doc_id, code="MAT-201", name="MATEMÁTICA II", semester="2",
                period="1-2025", grade="15")
    seed_course(db, doc_id, code="FIS-201", name="FÍSICA II", semester="2",
                period="1-2025", grade="14")

    result = classify_student(db, "V-123", "")
    assert result is not None
    assert result["effective_semester"] == 2


def test_compute_stats_pivot(db):
    seed_plan(db)
    doc_id1 = seed_student(db, identity_document="V-001", periods_completed=2)
    seed_course(db, doc_id1, code="MAT-201", name="MATEMÁTICA II", semester="2",
                identity_document="V-001", grade="15")
    seed_enrollment(db, identity_document="V-001", subjects=[
        {"code": "MAT-201", "name": "MATEMÁTICA II"},
        {"code": "FIS-201", "name": "FÍSICA II"},
    ])

    doc_id2 = seed_student(db, identity_document="V-002", periods_completed=3)
    seed_course(db, doc_id2, code="MAT-201", name="MATEMÁTICA II", semester="2",
                identity_document="V-002", grade="08")
    seed_course(db, doc_id2, code="MAT-301", name="MATEMÁTICA III", semester="3",
                identity_document="V-002", grade="15")
    seed_enrollment(db, identity_document="V-002", subjects=[
        {"code": "MAT-201", "name": "MATEMÁTICA II"},
        {"code": "MAT-301", "name": "MATEMÁTICA III"},
    ])

    doc_id3 = seed_student(db, identity_document="V-003", periods_completed=3)
    seed_course(db, doc_id3, code="MAT-101", name="MATEMÁTICA I", semester="1",
                identity_document="V-003", grade="08")
    seed_course(db, doc_id3, code="FIS-101", name="FÍSICA I", semester="1",
                identity_document="V-003", grade="07")
    seed_enrollment(db, identity_document="V-003", subjects=[
        {"code": "MAT-101", "name": "MATEMÁTICA I"},
        {"code": "FIS-101", "name": "FÍSICA I"},
    ])

    pivot = compute_stats_pivot(db, "1-2025")

    assert len(pivot) == 3

    for row in pivot:
        assert row["Carrera"] == "INGENIERÍA DE PRUEBA"
        if row["Tipo"] == "Regular":
            assert row["II"] == 1
        elif row["Tipo"] == "Repitiente":
            assert row["III"] == 1
        elif row["Tipo"] == "Desfasado":
            assert row["I"] == 1


def test_classify_unknown_student(db):
    result = classify_student(db, "V-NONEXISTENT", "")
    assert result is None


def test_classify_no_enrollment_no_courses(db):
    seed_plan(db)
    seed_student(db, periods_completed=2)

    result = classify_student(db, "V-123", "1-2025")
    assert result is not None
    assert result["clasificacion"] == "sin_datos"
