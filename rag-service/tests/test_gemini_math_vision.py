import json
from pathlib import Path
from types import SimpleNamespace

from app.db.database import Database
from app.db.models import DocumentRecord
from app.services.gemini_math_vision import GeminiMathVisionService
from app.services.pdf_math_extractor import MathRegion


def region(identifier: str = "p1-r1") -> MathRegion:
    return MathRegion(identifier, 1, (0, 0, 10, 10), "E=1", b"png", "hash")


def response(identifier: str = "p1-r1") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"regions": [{"regionId": identifier, "latex": "E=1"}]})}]}}]}


def settings(**values):  # type: ignore[no-untyped-def]
    defaults = dict(
        gemini_api_key="key",
        gemini_oauth_enabled=True,
        gemini_api_base_url=None,
        gemini_oauth_quota_project="project",
        math_vision_model="vision-model",
        math_vision_timeout_seconds=60,
        math_extraction_version="pdf-math-v1",
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_math_vision_uses_api_key_before_oauth() -> None:
    service = GeminiMathVisionService(settings())
    called: list[str] = []
    service._api_key_request = lambda payload: called.append("api") or response()  # type: ignore[method-assign]
    service._oauth_request = lambda payload: called.append("oauth") or response()  # type: ignore[method-assign]

    result = service.enhance([region()])

    assert called == ["api"]
    assert result["p1-r1"].latex == "E=1"


def test_math_vision_falls_back_to_oauth_and_payload_contains_no_full_pdf() -> None:
    service = GeminiMathVisionService(settings())
    payloads: list[dict] = []
    service._api_key_request = lambda payload: (_ for _ in ()).throw(TimeoutError())  # type: ignore[method-assign]
    service._oauth_request = lambda payload: payloads.append(payload) or response()  # type: ignore[method-assign]

    assert service.enhance([region()])["p1-r1"].provider == "gemini_oauth"
    inline = payloads[0]["contents"][0]["parts"][2]["inlineData"]
    assert inline["mimeType"] == "image/png"
    assert "responseJsonSchema" in payloads[0]["generationConfig"]


def test_math_vision_reuses_cached_crop(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'cache.db').as_posix()}", create_for_tests=True)
    with database.session() as session:
        session.add(DocumentRecord(
            id="00000000-0000-0000-0000-000000000001", owner_id="owner",
            original_filename="math.pdf", mime_type="application/pdf", file_size=3,
            file_hash="h" * 64,
        ))
        session.commit()
    item = MathRegion("p1-r1", 1, (0, 0, 10, 10), "E=1", b"png", "hash", "00000000-0000-0000-0000-000000000001")
    first = GeminiMathVisionService(settings(), database)
    first._api_key_request = lambda payload: response()  # type: ignore[method-assign]
    assert first.enhance([item])["p1-r1"].provider == "gemini_api_key"

    second = GeminiMathVisionService(settings(), database)
    second._api_key_request = lambda payload: (_ for _ in ()).throw(AssertionError("cache miss"))  # type: ignore[method-assign]
    assert second.enhance([item])["p1-r1"].provider == "gemini_api_key"
