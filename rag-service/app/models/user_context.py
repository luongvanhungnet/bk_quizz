import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from app.core.exceptions import ServiceError

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


def normalize_identifier(value: str, *, field_name: str) -> str:
    candidate = value.strip()
    try:
        return str(UUID(candidate))
    except ValueError:
        if IDENTIFIER_PATTERN.fullmatch(candidate):
            return candidate
    raise ServiceError(
        422,
        "INVALID_USER_CONTEXT" if field_name == "user" else "INVALID_CLASSROOM_CONTEXT",
        "Định danh người dùng không hợp lệ."
        if field_name == "user"
        else "Định danh lớp học không hợp lệ.",
    )


def safe_user_key(owner_id: str) -> str:
    try:
        return str(UUID(owner_id))
    except ValueError:
        return "id-" + hashlib.sha256(owner_id.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UserContext:
    owner_id: str
    safe_key: str
    classroom_id: str | None = None
