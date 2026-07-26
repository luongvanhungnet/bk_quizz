from pathlib import Path

import pymupdf

from app.services.document_parser import DocumentParser


def test_parse_txt_and_markdown(tmp_path: Path) -> None:
    txt = tmp_path / "guide.txt"
    txt.write_text("Dòng một.\n\nDòng hai.", encoding="utf-8-sig")
    markdown = tmp_path / "guide.md"
    markdown.write_text("# Mở đầu\n\nNội dung A.\n\n## Chi tiết\nNội dung B.", encoding="utf-8")
    parser = DocumentParser()

    txt_sections = parser.parse(txt)
    md_sections = parser.parse(markdown)

    assert txt_sections[0].page_number is None
    assert txt_sections[0].heading is None
    assert "Dòng hai" in txt_sections[0].text
    assert [section.heading for section in md_sections] == ["Mở đầu", "Chi tiết"]


def test_parse_pdf_preserves_one_based_page_number(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "First page")
    second = document.new_page()
    second.insert_text((72, 72), "Second page")
    document.save(path)
    document.close()

    sections = DocumentParser().parse(path)

    assert [(section.page_number, section.text) for section in sections] == [
        (1, "First page"),
        (2, "Second page"),
    ]


def test_empty_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()

    try:
        DocumentParser().parse(path)
    except ValueError as error:
        assert "không có văn bản" in str(error)
    else:
        raise AssertionError("Expected empty PDF to be rejected")
