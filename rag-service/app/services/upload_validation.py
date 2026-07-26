import re
import unicodedata
import zipfile
from pathlib import Path

from app.core.exceptions import ServiceError

ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_filename(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "document")
    normalized = normalized.replace("\\", "/").split("/")[-1]
    normalized = CONTROL_CHARACTERS.sub("", normalized).strip(" .")
    if not normalized:
        normalized = "document"
    return normalized[:255]


class UploadValidator:
    def validate(self, path: Path, filename: str, declared_mime: str | None) -> str:
        suffix = Path(filename).suffix.casefold()
        if suffix not in ALLOWED_TYPES:
            raise ServiceError(415, "UNSUPPORTED_FILE_TYPE", "Định dạng tài liệu không được hỗ trợ.")
        mime = (declared_mime or "").split(";", 1)[0].strip().casefold()
        if mime not in ALLOWED_TYPES[suffix]:
            raise ServiceError(415, "FILE_TYPE_MISMATCH", "Định dạng và MIME của tệp không khớp.")
        with path.open("rb") as stream:
            signature = stream.read(8)
        if signature.startswith((b"MZ", b"\x7fELF")):
            raise ServiceError(415, "EXECUTABLE_FILE_BLOCKED", "Không chấp nhận tệp thực thi.")
        if suffix == ".pdf":
            if not signature.startswith(b"%PDF-"):
                raise ServiceError(415, "FILE_TYPE_MISMATCH", "Tệp không có cấu trúc PDF hợp lệ.")
        elif suffix in {".docx", ".pptx"}:
            self._validate_office_zip(path, "word/" if suffix == ".docx" else "ppt/")
        else:
            try:
                path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as error:
                raise ServiceError(415, "INVALID_TEXT_ENCODING", "Tệp văn bản phải dùng UTF-8.") from error
        return mime

    @staticmethod
    def _validate_office_zip(path: Path, required_prefix: str) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                total = sum(entry.file_size for entry in entries)
                if len(entries) > 10_000 or total > 100 * 1024 * 1024:
                    raise ServiceError(413, "ARCHIVE_LIMIT_EXCEEDED", "Tệp nén có cấu trúc bất thường.")
                if not any(entry.filename.startswith(required_prefix) for entry in entries):
                    raise ServiceError(415, "FILE_TYPE_MISMATCH", "Tệp Office không đúng định dạng khai báo.")
        except zipfile.BadZipFile as error:
            raise ServiceError(415, "FILE_TYPE_MISMATCH", "Tệp Office không phải ZIP hợp lệ.") from error
