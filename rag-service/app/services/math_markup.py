import re
from dataclasses import dataclass

LATEX_SIGNAL = re.compile(
    r"\\(?:int|sum|prod|frac|sqrt|lim|alpha|beta|gamma|theta|pi|mathbf)\b"
    r"|[_^](?:\{[^{}]+\}|[A-Za-z0-9])"
)


@dataclass(frozen=True)
class MathMarkupResult:
    value: str
    warning: str | None = None


def normalize_math_field(value: str) -> MathMarkupResult:
    """Normalize only unambiguous whole-field formulae; never rewrite prose."""
    stripped = value.strip()
    if not stripped or not LATEX_SIGNAL.search(stripped):
        return MathMarkupResult(value)
    if not _balanced_braces(stripped) or not _balanced_dollars(stripped):
        return MathMarkupResult(value, "MATH_FORMAT_UNVERIFIED")
    if "$" in stripped or r"\(" in stripped or r"\[" in stripped:
        return MathMarkupResult(value)
    looks_like_formula = bool(re.search(r"[=<>±×÷]", stripped)) and len(stripped.split()) <= 12
    if looks_like_formula:
        return MathMarkupResult(f"${stripped}$")
    return MathMarkupResult(value, "MATH_FORMAT_UNVERIFIED")


def _balanced_braces(value: str) -> bool:
    depth = 0
    for character in value:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def _balanced_dollars(value: str) -> bool:
    unescaped = re.findall(r"(?<!\\)\$", value)
    return len(unescaped) % 2 == 0
