from pathlib import Path

import pymupdf

from app.services.document_parser import DocumentParser
from app.services.pdf_math_extractor import MathVisionResult, reconstruct_math_spans


class FakeVision:
    def enhance(self, regions):  # type: ignore[no-untyped-def]
        return {
            region.region_id: MathVisionResult(
                region.region_id,
                r"E_{a(t)}=\int_0^T a^2(t)\,dt",
                "gemini_api_key",
                "test-model",
            )
            for region in regions
        }


def test_layout_reconstruction_keeps_super_and_subscripts() -> None:
    spans = [
        {"text": "b", "size": 12, "origin": (0, 20)},
        {"text": "j", "size": 8, "origin": (7, 23)},
        {"text": "(t)=", "size": 12, "origin": (12, 20)},
        {"text": "2", "size": 8, "origin": (35, 16)},
    ]
    assert reconstruct_math_spans(spans) == "b_{j}(t)=^{2}"


def test_pdf_math_region_is_replaced_by_validated_latex_and_raw_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "math.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "E_a(t) = Z a2(t) dt")
    document.save(path)
    document.close()

    section = DocumentParser(math_vision=FakeVision()).parse(path)[0]

    assert section.raw_text == "E_a(t) = Z a2(t) dt"
    assert r"$E_{a(t)}=\int_0^T a^2(t)\,dt$" in section.text
    assert section.math_enhanced is True
    assert section.math_formula_count == 1
    assert section.math_warning_count == 0


class BrokenVision:
    def enhance(self, regions):  # type: ignore[no-untyped-def]
        raise TimeoutError("upstream timeout")


def test_pdf_math_vision_failure_keeps_document_usable_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "math.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "E_a(t) = Z a2(t) dt")
    document.save(path)
    document.close()

    section = DocumentParser(math_vision=BrokenVision()).parse(path)[0]

    assert section.text == section.raw_text
    assert section.math_enhanced is False
    assert section.math_warning_count == 1
