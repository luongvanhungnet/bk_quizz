import hashlib
import re
import statistics
from dataclasses import dataclass
from typing import Protocol, Sequence

import pymupdf

MATH_FONT = re.compile(r"math|symbol|cambria|stix|cmr|cmsy", re.IGNORECASE)
MATH_SIGNAL = re.compile(r"[=∫∑√∞≈≤≥]|\\(?:int|sum|frac)|[_^]|\bZ\b")
UNSAFE_LATEX = re.compile(r"\\(?:input|include|write|href|url|html|class|style)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MathRegion:
    region_id: str
    page_number: int
    bbox: tuple[float, float, float, float]
    raw_text: str
    png: bytes
    crop_hash: str
    document_id: str | None = None


@dataclass(frozen=True)
class MathVisionResult:
    region_id: str
    latex: str
    provider: str
    model: str


@dataclass(frozen=True)
class PdfPageMathResult:
    raw_text: str
    enhanced_text: str
    formula_count: int
    warning_count: int


class MathVision(Protocol):
    def enhance(self, regions: Sequence[MathRegion]) -> dict[str, MathVisionResult]: ...


class PdfMathExtractor:
    def __init__(self, vision: MathVision | None = None) -> None:
        self._vision = vision

    def extract(self, page: pymupdf.Page, page_number: int, document_id: str | None = None) -> PdfPageMathResult:
        layout = page.get_text("dict", sort=True)
        lines: list[dict[str, object]] = []
        for block in layout.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(str(span.get("text", "")) for span in spans).strip()
                if not text:
                    continue
                bbox = tuple(float(value) for value in line.get("bbox", (0, 0, 0, 0)))
                styled = any(MATH_FONT.search(str(span.get("font", ""))) for span in spans)
                is_math = styled or bool(MATH_SIGNAL.search(text))
                local_latex = reconstruct_math_spans(spans) if is_math and "Z" not in text else None
                lines.append({"text": text, "bbox": bbox, "is_math": is_math, "local": local_latex})
        raw_text = "\n".join(str(item["text"]) for item in lines).strip()
        candidates = [item for item in lines if item["is_math"] and item["local"] is None]
        local_formula_count = sum(bool(item["local"]) for item in lines)
        if not candidates:
            enhanced = "\n".join(f"${item['local']}$" if item["local"] else str(item["text"]) for item in lines)
            return PdfPageMathResult(raw_text, enhanced, local_formula_count, 0)
        if not any(item["is_math"] for item in lines):
            return PdfPageMathResult(raw_text, raw_text, 0, 0)

        regions = [self._region(page, page_number, index, str(item["text"]), item["bbox"], document_id) for index, item in enumerate(candidates)]  # type: ignore[arg-type]
        if self._vision is None:
            enhanced = "\n".join(f"${item['local']}$" if item["local"] else str(item["text"]) for item in lines)
            return PdfPageMathResult(raw_text, enhanced, local_formula_count, len(regions))
        try:
            replacements: dict[str, MathVisionResult] = {}
            for start in range(0, len(regions), 4):
                replacements.update(self._vision.enhance(regions[start : start + 4]))
        except Exception:
            enhanced = "\n".join(f"${item['local']}$" if item["local"] else str(item["text"]) for item in lines)
            return PdfPageMathResult(raw_text, enhanced, local_formula_count, len(regions))

        enhanced_lines: list[str] = []
        formula_count = local_formula_count
        warnings = 0
        candidate_index = 0
        for item in lines:
            text = str(item["text"])
            is_math = bool(item["is_math"])
            if not is_math:
                enhanced_lines.append(text)
                continue
            if item["local"]:
                enhanced_lines.append(f"${item['local']}$")
                continue
            region = regions[candidate_index]
            candidate_index += 1
            result = replacements.get(region.region_id)
            if result is None or not valid_latex(result.latex, region.raw_text):
                enhanced_lines.append(text)
                warnings += 1
                continue
            latex = result.latex.strip().removeprefix("$$").removesuffix("$$").strip()
            latex = latex.removeprefix("$").removesuffix("$").strip()
            enhanced_lines.append(f"${latex}$")
            formula_count += 1
        return PdfPageMathResult(raw_text, "\n".join(enhanced_lines), formula_count, warnings)

    @staticmethod
    def _region(
        page: pymupdf.Page,
        page_number: int,
        index: int,
        raw_text: str,
        bbox: tuple[float, float, float, float],
        document_id: str | None,
    ) -> MathRegion:
        rect = pymupdf.Rect(bbox) + (-4, -4, 4, 4)
        rect &= page.rect
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(300 / 72, 300 / 72), clip=rect, alpha=False)
        png = pixmap.tobytes("png")
        digest = hashlib.sha256(png).hexdigest()
        return MathRegion(f"p{page_number}-r{index + 1}", page_number, bbox, raw_text, png, digest, document_id)


def valid_latex(latex: str, raw_text: str) -> bool:
    value = latex.strip()
    if not value or len(value) > 2000 or UNSAFE_LATEX.search(value):
        return False
    depth = 0
    for character in value:
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
        if depth < 0:
            return False
    if depth:
        return False
    raw_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", raw_text))
    latex_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", value))
    return raw_numbers.issubset(latex_numbers)


def reconstruct_math_spans(spans: Sequence[dict[str, object]]) -> str | None:
    """Use font size and baseline metadata for a conservative local reconstruction."""
    if not spans:
        return None
    sizes = [float(str(span.get("size", 0) or 0)) for span in spans]
    base_size = max(sizes, default=0)
    if base_size <= 0:
        return None
    normal_origins = [
        _origin_y(span, 0)
        for span, size in zip(spans, sizes, strict=True)
        if size >= base_size * 0.85
    ]
    base_y = statistics.median(normal_origins) if normal_origins else 0
    pieces: list[str] = []
    for span, size in zip(spans, sizes, strict=True):
        text = str(span.get("text", ""))
        text = text.replace("∫", r"\int ").replace("∑", r"\sum ").replace("√", r"\sqrt{}")
        origin_y = _origin_y(span, base_y)
        if size < base_size * 0.85 and text.strip():
            marker = "^" if origin_y < base_y else "_"
            pieces.append(f"{marker}{{{text.strip()}}}")
        else:
            pieces.append(text)
    value = "".join(pieces).strip()
    return value if value and MATH_SIGNAL.search(value) else None


def _origin_y(span: dict[str, object], default: float) -> float:
    origin = span.get("origin")
    if isinstance(origin, (tuple, list)) and len(origin) > 1:
        return float(str(origin[1]))
    return default
