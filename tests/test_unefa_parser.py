from __future__ import annotations

from pathlib import Path

from academic_audit.parsers.unefa import parse_unefa_transcript

_HERE = Path(__file__).parent
FIXTURE = _HERE / "fixtures" / "unefa_vasquez.md"


def test_parse_student_info():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    student = result.student

    assert student["surnames"] == "VASQUEZ ABREU"
    assert student["given_names"] == "JOSUÉ GABRIEL"
    assert student["student_id"] == "1-2021-30255692"
    assert student["identity_document"] == "V-30255692"
    assert student["program"] == "INGENIERÍA DE SISTEMAS"
    assert student["periods_completed"] == 8
    assert student["study_plan_period"] == 9
    assert student["nucleus"] == "MIRANDA SANTA TERESA"
    assert student["academic_index"] == 14.54
    assert student["issue_date"] == "05-02-2026"
    assert student["full_name"] == "VASQUEZ ABREU, JOSUÉ GABRIEL"


def test_parse_courses_count():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    assert len(result.courses) == 69


def test_parse_cinu_courses():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    cinu_courses = [c for c in result.courses if c["course_type"] == "cinu"]
    assert len(cinu_courses) == 2
    assert cinu_courses[0]["period"] == "1-2021"
    assert cinu_courses[0]["grade"] == "REPROBÓ"
    assert cinu_courses[0]["observation"] == "REPROBÓ"
    assert cinu_courses[1]["period"] == "2-2021"
    assert cinu_courses[1]["grade"] == "APROBÓ"
    assert cinu_courses[1]["observation"] == "APROBÓ"
    assert cinu_courses[1]["semester"] is None


def test_parse_first_regular_course():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    regular = [c for c in result.courses if c["course_type"] == "regular"]
    first = regular[0]
    assert first["period"] == "1-2022"
    assert first["semester"] == "01"
    assert first["code"] == "DIN-21113"
    assert first["name"] == "DEFENSA INTEGRAL DE LA NACIÓN I"
    assert first["grade"] == "19"
    assert first["credits"] == 3
    assert first["points"] == 57


def test_parse_course_with_repitio_observation():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    repitio = [c for c in result.courses if c.get("observation") == "REPITIÓ"]
    assert len(repitio) >= 2
    ing_repeated = [c for c in repitio if c["code"] == "IDM-24113"]
    assert len(ing_repeated) > 0
    assert ing_repeated[0]["name"] == "INGLÉS I"


def test_parse_course_with_reprobo_observation():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    reprobo = [c for c in result.courses if c.get("grade") == "REPROBÓ" or
               c.get("observation") == "REPROBÓ"]
    assert len(reprobo) >= 1


def test_parse_courses_via_status_only_next_line():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    cultural = [c for c in result.courses
                if c["code"] == "ACT-13010" and c["name"] == "CULTURA Y COMUNICACIÓN"]
    assert len(cultural) == 1
    assert cultural[0]["grade"] == "APROBÓ"


def test_parse_all_semesters_present():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    regular = [c for c in result.courses if c["course_type"] == "regular"]
    semesters = {c["semester"] for c in regular}
    assert "01" in semesters
    assert "02" in semesters
    assert "03" in semesters
    assert "04" in semesters
    assert "05" in semesters
    assert "06" in semesters
    assert "07" in semesters
    assert "08" in semesters


def test_parse_academic_index_snapshots():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    assert len(result.index_snapshots) > 0
    last = result.index_snapshots[-1]
    assert last["uc_cumulative"] == 222
    assert last["points_cumulative"] == 3162
    assert last["index_value"] == 14.24


def test_parse_extra_fields():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    assert result.extra_fields["total_courses_taken"] == "67"
    assert result.extra_fields["total_courses_passed"] == "65"
    assert result.extra_fields["total_uc_taken"] == "222"
    assert result.extra_fields["total_uc_passed"] == "214"


def test_parse_courses_with_pipe_table_format():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    dibujo = [c for c in result.courses
              if c["code"] == "MAT-21212" and c["name"] == "DIBUJO"]
    assert len(dibujo) == 1
    assert dibujo[0]["grade"] == "11"
    assert dibujo[0]["credits"] == 2


def test_parse_courses_without_credits_aprobo_only():
    text = FIXTURE.read_text(encoding="utf-8")
    result = parse_unefa_transcript(text)
    bolivariana = [c for c in result.courses
                   if c["code"] == "ADG-10820" and "CÁTEDRA" in c["name"]]
    assert len(bolivariana) == 1
    assert bolivariana[0]["grade"] == "APROBÓ"
