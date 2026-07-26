import re

from app.models.document import ChunkDraft, DocumentSection

PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
INLINE_SPACE = re.compile(r"[ \t]+")


class ChunkingService:
    def __init__(self, chunk_size: int, overlap: int) -> None:
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("Cấu hình chunk size/overlap không hợp lệ.")
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk_sections(self, sections: list[DocumentSection]) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        for section in sections:
            text = self._clean(section.text)
            if not text:
                continue
            start = 0
            while start < len(text):
                maximum_end = min(start + self._chunk_size, len(text))
                end = self._preferred_end(text, start, maximum_end)
                if end <= start:
                    end = min(start + self._chunk_size, len(text))
                value = text[start:end].strip()
                if value:
                    chunks.append(
                        ChunkDraft(
                            section.page_number,
                            section.heading,
                            value,
                            section.slide_number,
                        )
                    )
                if end >= len(text):
                    break
                next_start = max(start + 1, end - self._overlap)
                while next_start > start and next_start < end and text[next_start].isspace():
                    next_start += 1
                start = min(next_start, end)
        return chunks

    @staticmethod
    def _clean(text: str) -> str:
        paragraphs = [
            INLINE_SPACE.sub(" ", paragraph.replace("\n", " ")).strip()
            for paragraph in PARAGRAPH_BREAK.split(text.replace("\r\n", "\n"))
        ]
        return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)

    @staticmethod
    def _preferred_end(text: str, start: int, maximum_end: int) -> int:
        if maximum_end >= len(text):
            return len(text)
        minimum = start + max(1, (maximum_end - start) // 2)
        for separator in ("\n\n", ". ", "? ", "! ", "; ", " "):
            position = text.rfind(separator, minimum, maximum_end)
            if position >= minimum:
                return position + len(separator.rstrip())
        return maximum_end
