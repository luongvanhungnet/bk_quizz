from app.services.grounded_quiz_service import MATH_FORMATTING_INSTRUCTION
from app.services.math_markup import normalize_math_field


def test_preserves_delimited_math() -> None:
    result = normalize_math_field(r"Năng lượng là $E_{a(t)}=E_a$.")
    assert result.value == r"Năng lượng là $E_{a(t)}=E_a$."
    assert result.warning is None


def test_wraps_a_field_that_is_clearly_only_a_latex_formula() -> None:
    result = normalize_math_field(r"E_{a(t)} = \int_{0}^{T} a^2(t)\,dt")
    assert result.value == r"$E_{a(t)} = \int_{0}^{T} a^2(t)\,dt$"
    assert result.warning is None


def test_does_not_guess_math_inside_natural_language() -> None:
    value = r"Công thức E_{a(t)} dùng để tính năng lượng là gì?"
    result = normalize_math_field(value)
    assert result.value == value
    assert result.warning == "MATH_FORMAT_UNVERIFIED"


def test_unbalanced_latex_is_a_non_blocking_warning() -> None:
    value = r"$E_{a(t)}=\frac{a}{b$"
    result = normalize_math_field(value)
    assert result.value == value
    assert result.warning == "MATH_FORMAT_UNVERIFIED"


def test_quiz_prompt_requires_delimited_json_safe_latex() -> None:
    assert "$...$" in MATH_FORMATTING_INSTRUCTION
    assert "$$...$$" in MATH_FORMATTING_INSTRUCTION
    assert "escape" in MATH_FORMATTING_INSTRUCTION.casefold()
