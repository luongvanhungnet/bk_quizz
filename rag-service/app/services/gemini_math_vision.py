import base64
import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import google.auth
import httpx
from google.auth.transport.requests import AuthorizedSession

from app.core.config import Settings
from app.db.models import MathExtractionRecord
from app.services.pdf_math_extractor import MathRegion, MathVisionResult


class GeminiMathVisionService:
    """Small, synchronous Vision client used only inside blocking parser workers."""

    def __init__(self, settings: Settings, database: Any | None = None) -> None:
        self._settings = settings
        self._database = database

    def enhance(self, regions: Sequence[MathRegion]) -> dict[str, MathVisionResult]:
        if not regions:
            return {}
        cached, unresolved = self._load_cache(regions)
        if not unresolved:
            return cached
        payload = self._payload(unresolved)
        failures: list[Exception] = []
        if self._settings.gemini_api_key:
            try:
                data = self._api_key_request(payload)
                decoded = self._decode(data, unresolved, "gemini_api_key", self._settings.math_vision_model)
                self._store_cache(unresolved, decoded)
                return {**cached, **decoded}
            except Exception as error:
                failures.append(error)
        if self._settings.gemini_oauth_enabled:
            try:
                data = self._oauth_request(payload)
                decoded = self._decode(data, unresolved, "gemini_oauth", self._settings.math_vision_model)
                self._store_cache(unresolved, decoded)
                return {**cached, **decoded}
            except Exception as error:
                failures.append(error)
        self._store_failure(unresolved, "MATH_VISION_UNAVAILABLE")
        raise RuntimeError("MATH_VISION_UNAVAILABLE") from (failures[-1] if failures else None)

    def _load_cache(self, regions: Sequence[MathRegion]) -> tuple[dict[str, MathVisionResult], list[MathRegion]]:
        if self._database is None:
            return {}, list(regions)
        cached: dict[str, MathVisionResult] = {}
        unresolved: list[MathRegion] = []
        with self._database.session() as session:
            for region in regions:
                if region.document_id is None:
                    unresolved.append(region)
                    continue
                record = session.query(MathExtractionRecord).filter_by(
                    document_id=region.document_id,
                    crop_sha256=region.crop_hash,
                    model=self._settings.math_vision_model,
                    extraction_version=self._settings.math_extraction_version,
                    status="ENHANCED",
                ).first()
                if record is None or not record.latex:
                    unresolved.append(region)
                else:
                    cached[region.region_id] = MathVisionResult(
                        region.region_id, record.latex, record.provider or "cache", record.model or self._settings.math_vision_model
                    )
        return cached, unresolved

    def _store_cache(self, regions: Sequence[MathRegion], results: dict[str, MathVisionResult]) -> None:
        if self._database is None:
            return
        with self._database.session() as session:
            for region in regions:
                result = results.get(region.region_id)
                if region.document_id is None or result is None:
                    continue
                existing = session.query(MathExtractionRecord).filter_by(
                    document_id=region.document_id,
                    crop_sha256=region.crop_hash,
                    model=result.model,
                    extraction_version=self._settings.math_extraction_version,
                ).first()
                if existing is not None:
                    existing.latex = result.latex
                    existing.provider = result.provider
                    existing.status = "ENHANCED"
                    existing.error_code = None
                    continue
                session.add(MathExtractionRecord(
                    id=str(uuid.uuid4()),
                    document_id=region.document_id,
                    page_number=region.page_number,
                    bbox_json=json.dumps(region.bbox),
                    crop_sha256=region.crop_hash,
                    raw_text=region.raw_text,
                    latex=result.latex,
                    provider=result.provider,
                    model=result.model,
                    status="ENHANCED",
                    error_code=None,
                    extraction_version=self._settings.math_extraction_version,
                    created_at=datetime.now(timezone.utc),
                ))
            session.commit()

    def _store_failure(self, regions: Sequence[MathRegion], code: str) -> None:
        if self._database is None:
            return
        with self._database.session() as session:
            for region in regions:
                if region.document_id is None:
                    continue
                existing = session.query(MathExtractionRecord).filter_by(
                    document_id=region.document_id,
                    crop_sha256=region.crop_hash,
                    model=self._settings.math_vision_model,
                    extraction_version=self._settings.math_extraction_version,
                ).first()
                if existing is None:
                    session.add(MathExtractionRecord(
                        id=str(uuid.uuid4()), document_id=region.document_id,
                        page_number=region.page_number, bbox_json=json.dumps(region.bbox),
                        crop_sha256=region.crop_hash, raw_text=region.raw_text,
                        latex=None, provider=None, model=self._settings.math_vision_model,
                        status="FAILED", error_code=code,
                        extraction_version=self._settings.math_extraction_version,
                        created_at=datetime.now(timezone.utc),
                    ))
                else:
                    existing.status = "FAILED"
                    existing.error_code = code
            session.commit()

    def _api_key_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = self._settings.gemini_api_base_url or "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base.rstrip('/')}/models/{self._settings.math_vision_model}:generateContent"
        with httpx.Client(timeout=self._settings.math_vision_timeout_seconds) as client:
            response = client.post(url, params={"key": self._settings.gemini_api_key}, json=payload)
            response.raise_for_status()
            return response.json()

    def _oauth_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/generative-language"])
        session = AuthorizedSession(credentials)
        headers = {}
        if self._settings.gemini_oauth_quota_project:
            headers["x-goog-user-project"] = self._settings.gemini_oauth_quota_project
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._settings.math_vision_model}:generateContent"
        )
        response = session.post(
            url,
            json=payload,
            headers=headers,
            timeout=self._settings.math_vision_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _payload(regions: Sequence[MathRegion]) -> dict[str, Any]:
        parts: list[dict[str, Any]] = [{
            "text": (
                "Chuyển từng vùng công thức được đánh số thành LaTeX. Không suy diễn nội dung "
                "ngoài ảnh. Trả đúng regionId và latex, không thêm delimiter $."
            )
        }]
        for region in regions:
            parts.extend((
                {"text": f"regionId={region.region_id}"},
                {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(region.png).decode("ascii")}},
            ))
        return {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
                "responseJsonSchema": {
                    "type": "object",
                    "properties": {
                        "regions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"regionId": {"type": "string"}, "latex": {"type": "string"}},
                                "required": ["regionId", "latex"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["regions"],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _decode(data: dict[str, Any], regions: Sequence[MathRegion], provider: str, model: str) -> dict[str, MathVisionResult]:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        allowed = {region.region_id for region in regions}
        results: dict[str, MathVisionResult] = {}
        for item in parsed.get("regions", []):
            region_id = str(item.get("regionId", ""))
            latex = str(item.get("latex", ""))
            if region_id in allowed and region_id not in results:
                results[region_id] = MathVisionResult(region_id, latex, provider, model)
        return results
