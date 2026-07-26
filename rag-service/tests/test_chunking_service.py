from app.models.document import DocumentSection
from app.services.chunking_service import ChunkingService


def test_chunks_are_non_empty_and_have_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(80))
    service = ChunkingService(chunk_size=120, overlap=30)

    chunks = service.chunk_sections([DocumentSection(None, None, text)])

    assert len(chunks) > 1
    assert all(chunk.text.strip() for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        previous_words = set(previous.text.split()[-5:])
        current_words = set(current.text.split()[:8])
        assert previous_words & current_words


def test_short_section_produces_one_chunk() -> None:
    chunks = ChunkingService(1200, 200).chunk_sections(
        [DocumentSection(3, "Heading", "Nội dung ngắn.")]
    )

    assert len(chunks) == 1
    assert chunks[0].page_number == 3
    assert chunks[0].heading == "Heading"
    assert chunks[0].text == "Nội dung ngắn."
