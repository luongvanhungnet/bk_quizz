"""Internal provenance contracts; these are never imposed on a VLM response."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    engine: str
    text: str = ""
    status: str = "ok"
    confidence: float | None = None
    evidence: Any = None
    bbox: list[float] | None = None
    kind: str | None = None

    @field_validator("confidence")
    @classmethod
    def finite_confidence(cls, value):
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError("confidence must be finite and in [0,1]")
        return value


class RegionRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(min_length=1)
    page: int = Field(ge=1)
    kind: Literal["text", "formula", "table", "diagram", "chart", "image", "code"]
    bbox: list[float | int]
    render_path: str
    crop_path: str | None = None
    context_path: str | None = None
    source_sha256: str
    render_sha256: str
    crop_sha256: str | None = None
    context_sha256: str | None = None
    group_id: str
    split: Literal["train", "development", "holdout"] = "train"
    machine_bucket: Literal["trusted", "uncertain", "critical"] = "uncertain"
    reasons: list[str] = Field(default_factory=list)
    native_text: str = ""
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    proposed_text: str = ""
    risk: Literal["low", "high"] = "low"
    machine_revision: str = ""

    @field_validator("bbox", mode="before")
    @classmethod
    def valid_bbox(cls, value):
        if len(value) != 4 or any(isinstance(v, bool) or not math.isfinite(v) for v in value):
            raise ValueError("bbox must contain four finite coordinates")
        x0, y0, x1, y1 = value
        if not (0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 1000):
            raise ValueError("bbox must be a positive full-slide box in [0,1000]")
        return value

    @field_validator("source_sha256", "render_sha256", "crop_sha256", "context_sha256")
    @classmethod
    def valid_sha256(cls, value):
        if value is not None and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


Record = RegionRecord


def validate_record(record: dict) -> dict:
    return RegionRecord.model_validate(record).model_dump(mode="json")
