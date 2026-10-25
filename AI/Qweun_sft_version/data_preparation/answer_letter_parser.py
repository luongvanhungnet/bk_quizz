"""Parse native question banks ending each item with an explicit ANSWER: A key.

This parser deliberately does not read the edX label ``Answer:`` beside an input
as an answer key. Only complete key lines naming existing uppercase choices are
accepted. It also rejects incomplete alphabetical option runs.
"""
from __future__ import annotations

import re

from extract_questions import finish, page_lines, source_record, text_clean


KEY_LINE = re.compile(r"^ANSWER\s*:\s*([A-H](?:\s*[,;]\s*[A-H])*)\s*[.]?\s*$")
ANY_ANSWER_LINE = re.compile(r"^ANSWER\s*:", re.I)
CHOICE_LINE = re.compile(r"^([A-H])\s*[)]\s*(.*)$")
QUESTION_PREFIX = re.compile(r"^(?:(?:Câu\s+(?:hỏi\s+)?|Question\s+)\d+|\d+)[.:]\s*", re.I)

# Reviewed against source page renders and independent technical references.
# Keep the original source answer intact; quarantine rather than silently fix it.
SEMANTIC_CONTRADICTIONS = frozenset({
    "q_6b51c70a55d535fd8491",  # FAT32 entry: source selects 32 bytes, not 32 bits.
    "q_697bfdf93c1dc1cc8e57",  # Indexed allocation supports direct access.
    "q_16be77e4e2c7f3393fff",  # Linked allocation has no external fragmentation.
    "q_31b87f5dfdf9b1ccf3d4",  # Open-file tables reduce repeated directory search.
})
UNDERDETERMINED_QUESTIONS = frozenset({
    "q_321dd8b5511a35dbb62e", "q_40be066565016740754f",  # Ready-queue count lacks scheduler/I/O assumptions.
    "q_864dad60f0762496185d",  # Fastest-fit claim lacks free-list implementation assumptions.
})


def _parse_chunk(document: dict, chunk: list[dict], key_line: dict, number: int) -> dict:
    record = source_record(document, f"ANSWER item {number}", chunk + [key_line], "native_answer_letter")
    answer_match = KEY_LINE.fullmatch(key_line["text"])
    if not answer_match:
        record.update(status="quarantine", reasons=["unsupported_answer_key_format"])
        return record

    starts = [(i, CHOICE_LINE.match(line["text"])) for i, line in enumerate(chunk)
              if CHOICE_LINE.match(line["text"])]
    # A sequence starting from A is required, so variables or isolated code labels
    # cannot be silently promoted into options.
    labels = [match.group(1) for _, match in starts]
    if not starts or labels != [chr(65 + i) for i in range(len(labels))] or len(labels) < 2:
        record.update(status="quarantine", reasons=["nonsequential_or_missing_option_labels"])
        return record
    first = starts[0][0]
    prompt = text_clean(" ".join(line["text"] for line in chunk[:first]))
    prompt = QUESTION_PREFIX.sub("", prompt, count=1)
    correct = set(re.split(r"\s*[,;]\s*", answer_match.group(1)))
    options = []
    for index, (start, match) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(chunk)
        value = text_clean(" ".join([match.group(2)] + [line["text"] for line in chunk[start + 1:end]]))
        options.append({"label": match.group(1), "text": value,
                        "correct": match.group(1) in correct, "page": chunk[start]["page"]})
    record.update(prompt=prompt, options=options, answer_evidence=key_line["text"],
                  answer_origin="explicit_source_letter_key", explanation_source="")
    if not correct.issubset(set(labels)):
        record["reasons"] = ["answer_key_label_missing"]
    # PDF-to-text can flatten the cells of a process/resource matrix into one
    # continuous string. Preserve those examples for review, rather than train.
    if re.search(r"MAXALLOCATION|\b[A-Z]{5,}(?:P\d|\d)|P\d\d{7,}", prompt):
        record.setdefault("reasons", []).append("flattened_table_requires_review")
    if re.search(r"Trang\s*\|\s*Khung trang|tiến trình(?:Tiến trình|Thứ tự)|p0\s+0\s+\d+\s+p1\s+\d|p1\s+0\s+\d+\s+p2\s+\d", prompt, re.I):
        record.setdefault("reasons", []).append("flattened_table_requires_review")
    if record["id"] in SEMANTIC_CONTRADICTIONS:
        record.setdefault("reasons", []).append("source_key_semantic_contradiction")
    if record["id"] in UNDERDETERMINED_QUESTIONS:
        record.setdefault("reasons", []).append("source_question_underdetermined")
    return finish(record, chunk + [key_line], document)


def parse_answer_letters(document: dict) -> list[dict]:
    """Return supported keyed questions and quarantined key-bounded fragments.

    The accumulator crosses physical PDF pages, supporting prompts at the bottom
    of one page whose choices are at the top of the next. Every ANSWER line is a
    boundary even when its format is unsupported, preventing two items merging.
    """
    pending: list[dict] = []
    records: list[dict] = []
    number = 0
    for page in document["pages"]:
        # Retain native content ordering, which preserves columns where authored.
        for line in page_lines(page, original=True):
            if ANY_ANSWER_LINE.match(line["text"]):
                number += 1
                records.append(_parse_chunk(document, pending, line, number))
                pending = []
            else:
                pending.append(line)
    # An unkeyed trailing item is not a candidate and remains in page review.
    return records
