from __future__ import annotations

from academic_audit.eligibility import (
    _is_passed,
    _is_failed,
    check_article_118a,
    check_article_118b,
    check_article_118c,
    check_prerequisites,
    check_article_118,
)


def make_course(*, code: str = "MAT-101", name: str = "MATEMÁTICA I",
                period: str = "1-2025", grade: str = "15",
                observation: str = "", credits: int = 4) -> dict:
    return {
        "code": code,
        "name": name,
        "period": period,
        "grade": grade,
        "observation": observation,
        "credits": credits,
    }


class TestIsPassed:
    def test_grade_10_or_higher(self):
        assert _is_passed(make_course(grade="10")) is True
        assert _is_passed(make_course(grade="15")) is True
        assert _is_passed(make_course(grade="20")) is True

    def test_grade_below_10(self):
        assert _is_passed(make_course(grade="09")) is False
        assert _is_passed(make_course(grade="00")) is False
        assert _is_passed(make_course(grade="01")) is False

    def test_aprobo_observation(self):
        assert _is_passed(make_course(grade="APROBÓ")) is True
        assert _is_passed(make_course(grade="", observation="APROBÓ")) is True
        assert _is_passed(make_course(grade="APROBÓ", observation="APROBÓ")) is True

    def test_reprobo_is_not_passed(self):
        assert _is_passed(make_course(grade="REPROBÓ")) is False
        assert _is_passed(make_course(grade="", observation="REPROBÓ")) is False


class TestIsFailed:
    def test_grade_below_10(self):
        assert _is_failed(make_course(grade="09")) is True
        assert _is_failed(make_course(grade="00")) is True
        assert _is_failed(make_course(grade="01")) is True

    def test_grade_10_or_higher(self):
        assert _is_failed(make_course(grade="10")) is False
        assert _is_failed(make_course(grade="15")) is False

    def test_reprobo_observation(self):
        assert _is_failed(make_course(grade="REPROBÓ")) is True
        assert _is_failed(make_course(grade="", observation="REPROBÓ")) is True

    def test_aprobo_is_not_failed(self):
        assert _is_failed(make_course(grade="APROBÓ")) is False


class TestCheckArticle118a:
    def test_no_violation(self):
        courses = [
            make_course(code="MAT-101", grade="10"),
            make_course(code="MAT-101", grade="09"),
        ]
        assert check_article_118a(courses) == []

    def test_three_failures_same_course(self):
        courses = [
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="05"),
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="04"),
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="06"),
        ]
        violations = check_article_118a(courses)
        assert len(violations) == 1
        assert "MATEMÁTICA I" in violations[0]
        assert "3" in violations[0]

    def test_four_failures(self):
        courses = [
            make_course(code="FIS-101", name="FÍSICA I", grade="05"),
            make_course(code="FIS-101", name="FÍSICA I", grade="04"),
            make_course(code="FIS-101", name="FÍSICA I", grade="06"),
            make_course(code="FIS-101", name="FÍSICA I", grade="03"),
        ]
        violations = check_article_118a(courses)
        assert len(violations) == 1
        assert "4" in violations[0]

    def test_multiple_courses_violating(self):
        courses = [
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="05"),
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="04"),
            make_course(code="MAT-101", name="MATEMÁTICA I", grade="06"),
            make_course(code="FIS-101", name="FÍSICA I", grade="05"),
            make_course(code="FIS-101", name="FÍSICA I", grade="04"),
            make_course(code="FIS-101", name="FÍSICA I", grade="06"),
        ]
        violations = check_article_118a(courses)
        assert len(violations) == 2

    def test_fifth_failure_counts_but_status_not_failed(self):
        courses = [
            make_course(code="MAT-101", name="MAT", period="1-2023", grade="APROBÓ"),
            make_course(code="MAT-101", name="MAT", period="1-2024", grade="APROBÓ"),
            make_course(code="MAT-101", name="MAT", period="1-2025", grade="APROBÓ"),
        ]
        assert check_article_118a(courses) == []


class TestCheckArticle118b:
    def test_no_violation(self):
        courses = [
            make_course(code="MAT-101", period="1-2025", grade="15"),
            make_course(code="FIS-101", period="1-2025", grade="10"),
            make_course(code="QUI-101", period="1-2025", grade="08"),
        ]
        assert check_article_118b(courses) == []

    def test_more_than_half_failed(self):
        courses = [
            make_course(code="MAT-101", period="1-2025", grade="05"),
            make_course(code="FIS-101", period="1-2025", grade="04"),
            make_course(code="QUI-101", period="1-2025", grade="03"),
            make_course(code="ING-101", period="1-2025", grade="16"),
        ]
        violations = check_article_118b(courses)
        assert len(violations) == 1
        assert "3/4" in violations[0]

    def test_exactly_half_failed_is_ok(self):
        courses = [
            make_course(code="MAT-101", period="1-2025", grade="05"),
            make_course(code="FIS-101", period="1-2025", grade="06"),
            make_course(code="QUI-101", period="1-2025", grade="15"),
            make_course(code="ING-101", period="1-2025", grade="16"),
        ]
        assert check_article_118b(courses) == []

    def test_multiple_periods(self):
        courses = [
            make_course(code="MAT-101", period="1-2024", grade="05"),
            make_course(code="FIS-101", period="1-2024", grade="04"),
            make_course(code="QUI-101", period="1-2024", grade="15"),
            make_course(code="MAT-201", period="1-2025", grade="05"),
            make_course(code="FIS-201", period="1-2025", grade="06"),
            make_course(code="QUI-201", period="1-2025", grade="15"),
        ]
        violations = check_article_118b(courses)
        assert len(violations) == 2
        assert "1-2024" in violations[0]


class TestCheckArticle118c:
    def test_no_teg_no_violation(self):
        courses = [make_course(code="MAT-101")]
        assert check_article_118c(courses) == []

    def test_teg_failed_one_period_no_violation(self):
        courses = [
            make_course(code="TES-001", name="TRABAJO ESPECIAL DE GRADO",
                        period="1-2025", grade="REPROBÓ"),
        ]
        assert check_article_118c(courses) == []

    def test_teg_failed_two_periods(self):
        courses = [
            make_course(code="TES-001", name="TRABAJO ESPECIAL DE GRADO",
                        period="1-2024", grade="REPROBÓ"),
            make_course(code="TES-001", name="TRABAJO ESPECIAL DE GRADO",
                        period="1-2025", grade="REPROBÓ"),
        ]
        violations = check_article_118c(courses)
        assert len(violations) == 1
        assert "TRABAJO ESPECIAL DE GRADO" in violations[0]

    def test_pasantia_failed_two_periods(self):
        courses = [
            make_course(code="PAS-001", name="PASANTÍA PROFESIONAL",
                        period="1-2024", grade="REPROBÓ"),
            make_course(code="PAS-001", name="PASANTÍA PROFESIONAL",
                        period="1-2025", grade="REPROBÓ"),
        ]
        violations = check_article_118c(courses)
        assert len(violations) == 1
        assert "PASANTÍA PROFESIONAL" in violations[0]

    def test_teg_passed_no_violation(self):
        courses = [
            make_course(code="TES-001", name="TESIS",
                        period="1-2024", grade="APROBÓ"),
            make_course(code="TES-001", name="TESIS",
                        period="1-2025", grade="APROBÓ"),
        ]
        assert check_article_118c(courses) == []


class TestCheckPrerequisites:
    def test_no_prereqs(self):
        assert check_prerequisites("MAT-101", "MAT", [], []) == ""

    def test_all_prereqs_passed(self):
        courses = [make_course(code="MAT-101", grade="15")]
        assert check_prerequisites("MAT-201", "MAT II", courses, ["MAT-101"]) == ""

    def test_missing_prereqs(self):
        courses = [make_course(code="FIS-101", grade="15")]
        msg = check_prerequisites("MAT-201", "MAT II", courses, ["MAT-101"])
        assert "MAT-101" in msg

    def test_multiple_missing(self):
        courses = []
        msg = check_prerequisites("MAT-301", "MAT III", courses, ["MAT-101", "MAT-201"])
        assert "MAT-101" in msg
        assert "MAT-201" in msg


class TestCheckArticle118:
    def test_clean_record(self):
        courses = [make_course(code="MAT-101", grade="15")]
        assert check_article_118(courses) == []

    def test_aggregates_all_checks(self):
        courses = [
            make_course(code="MAT-101", name="MAT I", grade="05", period="1-2024"),
            make_course(code="MAT-101", name="MAT I", grade="04", period="1-2025"),
            make_course(code="MAT-101", name="MAT I", grade="06", period="2-2025"),
            make_course(code="FIS-101", name="FÍSICA I", grade="05", period="1-2025"),
            make_course(code="FIS-101", name="FÍSICA I", grade="04", period="1-2025"),
            make_course(code="FIS-101", name="FÍSICA I", grade="06", period="1-2025"),
        ]
        violations = check_article_118(courses)
        assert len(violations) >= 2
