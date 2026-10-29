"""Conservative exam parsers. Answer evidence is required; no model is called."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pymupdf

from scan_sources import dump

QHEAD = re.compile(r"^(?:Câu\s+(?:hỏi\s+)?|Question\s+)(\d+)\s*[:.\-]?\s*", re.I)
OPTION = re.compile(r"^([A-Ha-h])(?:[.)]\s*|\s+)(.*)$")
ANSWER = re.compile(r"(?:the\s+correct\s+answers?\s+(?:is|are)\s*(?::\s*)?|correct\s+answers?\s*:\s*|đáp\s*án\s*:\s*)", re.I)
SYMBOLS = re.compile(r"[\ue000-\uf8ff\ufffd]|[\x00-\x08\x0b\x0c\x0e-\x1f]")
UI = re.compile(r"^(?:Correct|Corrected|Incorrect|Partially correct|Not answered|Unanswered|Select one:|Select one or more:|Hide|sidebars|Hide sidebars|Auto-graded|\d+(?:\.\d+)?/\d+(?:\.\d+)?\s*(?:Points|pts?)|/?\s*\d+\s*pts?|/|Mark(?:ed)?\s+(?:out|\d).*|\d+\.\d+|Gửi|Your answer is (?:correct|incorrect)\.)$", re.I)


def text_clean(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r"[\uf00c\uf00d\uf058\uf05d\ue682]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def key(value: str) -> str:
    return re.sub(r"[^\w]", "", text_clean(value).casefold())


def page_lines(page: dict, *, original: bool = False) -> list[dict]:
    lines = []
    for raw in page["lines"]:
        line = dict(raw, page=page["page"])
        line["text"] = text_clean(line["text"])
        if not line["text"] or line["bbox"][1] < 25 or line["bbox"][3] > page["height"] - 26:
            continue
        if re.search(r"https?://|Attempt review|Dashboard|Home\s+Courses|Time taken|Completed on|Started on|Copyright|Jump to|Chapter\s+\d+:", line["text"], re.I):
            continue
        if UI.fullmatch(line["text"]) and line["text"] == "Corrected":
            continue
        if original and re.fullmatch(r"\d+",line["text"]) and max((s.get("size",0) for s in line.get("spans",[])),default=0)>=12:
            continue
        lines.append(line)
    if original:
        return lines
    ordered, row = [], []
    for line in sorted(lines, key=lambda l: l["bbox"][1]):
        if row and line["bbox"][1] - row[0]["bbox"][1] > 3:
            ordered.extend(sorted(row,key=lambda l:l["bbox"][0])); row=[]
        row.append(line)
    return ordered + sorted(row,key=lambda l:l["bbox"][0])


def radio_marks(page: pymupdf.Page) -> list[dict]:
    marks = []
    for draw in page.get_drawings():
        box, fill = draw["rect"], draw["fill"]
        if draw["type"] != "fs" or fill is None:
            continue
        # Both supported publishers draw circular choices as paths with curves.
        if not (4 <= box.width <= 20 and 4 <= box.height <= 20 and .8 < box.width / box.height < 1.2):
            continue
        if len(draw["items"]) < 4 or not any(item[0] == "c" for item in draw["items"]):
            continue
        if len(fill) != 3 or max(fill) - min(fill) > .06:
            continue
        marks.append({"bbox": list(box), "selected": sum(fill) / 3 < .9, "fill": fill})
    return marks


def add_marks(lines: list[dict], marks: list[dict], corrected: bool) -> None:
    for mark in marks:
        x0, y0, x1, y1 = mark["bbox"]
        candidates = [l for l in lines if l["bbox"][1] - 2 <= (y0 + y1) / 2 <= l["bbox"][3] + 2
                      and ((abs(l["bbox"][0] - x0) < 4) if corrected else (0 <= l["bbox"][0] - x1 <= 55))]
        if not candidates:
            continue
        line = min(candidates, key=lambda l: abs(l["bbox"][1] - y0) + abs(l["bbox"][0] - x1))
        if not corrected:
            # Forms vertically centers a radio beside the complete wrapped option.
            # Walk back to the start of that paragraph, rather than its middle line.
            pos = lines.index(line)
            while pos > 0:
                previous = lines[pos - 1]
                if (abs(previous["bbox"][0] - line["bbox"][0]) > 2
                        or not -2 <= line["bbox"][1] - previous["bbox"][3] <= 8
                        or "radio" in previous):
                    break
                line, pos = previous, pos - 1
        if "radio" in line:
            line["radio_ambiguous"] = True
        else:
            line["radio"] = mark


def groups(lines: list[dict], pattern: re.Pattern) -> list[tuple[str, list[dict]]]:
    output, current, label = [], [], ""
    for line in lines:
        match = pattern.match(line["text"])
        if match:
            if current:
                output.append((label, current))
            current, label = [], match.group(0)
        if current or match:
            current.append(line)
    if current:
        output.append((label, current))
    return output


def source_record(document: dict, label: str, lines: list[dict], parser: str) -> dict:
    raw = "\n".join(l["text"] for l in lines)
    pages = sorted({l["page"] for l in lines})
    identity = f"{document['source_id']}:{pages}:{label}:{raw}"
    return {"id": "q_" + hashlib.sha256(identity.encode()).hexdigest()[:20],
            "source_id": document["source_id"], "source_sha256": document["sha256"],
            "source_path": document["path"], "source_relative_path": document["relative_path"],
            "course": document["course"], "pages": pages, "question_label": label,
            "parser": parser, "raw_text": raw, "regions": [
                {"page": p, "bbox": [min(l["bbox"][0] for l in lines if l["page"] == p),
                                      min(l["bbox"][1] for l in lines if l["page"] == p),
                                      max(l["bbox"][2] for l in lines if l["page"] == p),
                                      max(l["bbox"][3] for l in lines if l["page"] == p)]}
                for p in pages]}


def parse_options(lines: list[dict], radio: bool) -> tuple[str, list[dict]]:
    prompt, options = [], []
    for line in lines:
        value = line["text"]
        if UI.fullmatch(value) or re.fullmatch(r"(?:Correct|Incorrect)\s+.*Points.*", value, re.I):
            continue
        if not prompt and not options and re.fullmatch(r"\d+\.?", value):
            continue
        label = OPTION.match(value)
        starts_option = "radio" in line if radio else bool(label)
        if starts_option:
            content = label.group(2) if label else value
            options.append({"text": content, "label": label.group(1).upper() if label else chr(65 + len(options)),
                            "selected": line.get("radio", {}).get("selected", False),
                            "marker": line.get("radio"), "page": line["page"]})
        elif options:
            options[-1]["text"] += " " + value
        else:
            prompt.append(value)
    stem = QHEAD.sub("", text_clean(" ".join(prompt)), count=1)
    stem = re.sub(r"^\d+\.\s+", "", stem)
    return stem, [{**o, "text": text_clean(o["text"])} for o in options]


def finish(record: dict, lines: list[dict], document: dict) -> dict:
    reasons = []
    stem, options = record.get("prompt", ""), record.get("options", [])
    if len(stem) < 15 or len(stem) > 2500:
        reasons.append("invalid_or_incomplete_prompt")
    if not 2 <= len(options) <= 8:
        reasons.append("invalid_option_count")
    if options and len({key(o["text"]) for o in options}) != len(options):
        reasons.append("duplicate_options")
    if any(not 1 <= len(o["text"]) <= 1800 for o in options):
        reasons.append("invalid_option_text")
    if not any(o.get("correct") for o in options):
        reasons.append("no_verified_correct_option")
    if SYMBOLS.search(stem + " ".join(o["text"] for o in options)):
        reasons.append("unsupported_or_corrupt_glyph")
    if re.search(r"([^\W\d_])\1{5,}",stem+" ".join(o["text"] for o in options),re.I):
        reasons.append("repeated_character_corruption")
    if any(re.search(r"Math|Symbol|CambriaMath", s.get("font", ""), re.I)
           for l in lines for s in l.get("spans", [])):
        reasons.append("math_layout_requires_review")
    if re.search(r"(?:hình|bảng|sơ đồ|biểu đồ|đồ thị).{0,55}(?:dưới đây|sau đây|đưa ra|như sau|bên dưới|ở trên)|(?:hình|bảng|sơ đồ)\s+(?:vẽ|sau|dưới|bên|trên|\d)|trong hình|sơ đồ.{0,25}\bsau\b|mockup.{0,90}\bsau\b|shown\s+(?:below|above)|following\s+(?:diagram|figure)|đồ thị\s+(?:sau|dưới|bên|trên)", stem, re.I):
        reasons.append("visual_reference_requires_review")
    if any(l.get("radio_ambiguous") for l in lines):
        reasons.append("ambiguous_visual_marker")
    for region in record["regions"]:
        page = document["pages"][region["page"] - 1]
        box = pymupdf.Rect(region["bbox"])
        if any((box & pymupdf.Rect(im["bbox"])).get_area() > 1000 for im in page["images"]):
            reasons.append("embedded_figure_requires_review")
    if re.search(r"(?:Corrected|Correct|Incorrect|Mark \d|Select one|sidebars|https?://|Hide|Chapter \d)\b|/\s*\d+\s*pts?\b", stem + " ".join(o["text"] for o in options)):
        reasons.append("residual_ui_text")
    record["status"] = "candidate" if not reasons else "quarantine"
    record["reasons"] = sorted(set(record.get("reasons", []) + reasons))
    if record["reasons"]:
        record["status"] = "quarantine"
    record["type"] = "MULTIPLE_SELECT" if sum(o.get("correct", False) for o in options) > 1 else "SINGLE_CHOICE"
    record["human_verified"] = False
    return record


def parse_moodle(document: dict) -> list[dict]:
    lines = []
    for page in document["pages"]:
        all_lines = page_lines(page)
        lines += all_lines
    result = []
    for label, chunk in groups(lines, re.compile(r"^Question\s+\d+\b", re.I)):
        record = source_record(document, label, chunk, "moodle_explicit_key")
        split = next((i for i, l in enumerate(chunk) if ANSWER.search(l["text"])), None)
        if split is None:
            record.update(status="quarantine", reasons=["no_explicit_answer_key"])
            result.append(record)
            continue
        body, tail = chunk[:split], [chunk[split]]
        # An answer may wrap, but the next card's UI and next page are not evidence.
        for line in chunk[split+1:]:
            previous=tail[-1]
            if (line["page"]!=previous["page"] or line["bbox"][1]-previous["bbox"][3]>12
                    or UI.fullmatch(line["text"]) or re.search(r"Courses|Support|News|Grade|Finished|Jump to|Copyright",line["text"])):
                break
            tail.append(line)
        # Selectors delimit the stem even when option labels are missing.
        selector = next((i for i, l in enumerate(body) if re.match(r"Select one", l["text"], re.I)), None)
        boolean = selector is not None and [l["text"] for l in body[selector+1:selector+3]] in [["True","False"],["False","True"]]
        if selector is not None and not boolean and not any(OPTION.match(l["text"]) for l in body[selector + 1:]):
            record.update(status="quarantine", reasons=["unlabelled_options_require_review"])
            result.append(record)
            continue
        stem, options = parse_options(body, radio=False)
        if boolean:
            stem,_=parse_options(body[:selector],radio=False)
            options=[{"label":chr(65+i),"text":line["text"]} for i,line in enumerate(body[selector+1:selector+3])]
        answer = ANSWER.sub("", " ".join(l["text"] for l in tail), count=1)
        answer_key = key(answer)
        single = selector is not None and re.fullmatch(r"Select one:",body[selector]["text"],re.I)
        matches = []
        remainder = answer_key
        for option in sorted(options, key=lambda o:len(key(o["text"])),reverse=True):
            value=key(option["text"])
            if value and ((value==answer_key) if single else value in remainder):
                matches.append(option); remainder=remainder.replace(value,"",1)
        for option in options:
            option["correct"] = option in matches
        record.update(prompt=stem, options=options, answer_evidence=answer,
                      answer_origin="explicit_source_key", explanation_source="")
        if remainder or not matches:
            record["reasons"] = ["answer_key_does_not_exactly_match_options"]
        if selector is not None and re.fullmatch(r"Select one:", body[selector]["text"], re.I) and len(matches) != 1:
            record.setdefault("reasons", []).append("single_choice_key_ambiguous")
        result.append(finish(record, chunk, document))
    return result


def parse_radios(document: dict, corrected: bool) -> list[dict]:
    lines = []
    with pymupdf.open(document["path"]) as pdf:
        for page in document["pages"]:
            current = page_lines(page, original=corrected)
            add_marks(current, radio_marks(pdf[page["page"] - 1]), corrected)
            lines.extend(current)
    if corrected:
        pattern = re.compile(r"^Câu\s+\d+\s*[:.]", re.I)
    else:
        pattern = re.compile(r"^(?:Correct|Incorrect|Partially correct|Unanswered)(?:\s|$)", re.I)
    result = []
    for label, chunk in groups(lines, pattern):
        record = source_record(document, label, chunk, "corrected_filled_circle" if corrected else "forms_full_credit_radio")
        if not corrected and (not re.match(r"^Correct(?:\s|$)", label) or not re.search(r"\b([1-9]\d*)/\1\s*Points", " ".join(l["text"] for l in chunk[:3]), re.I)):
            record.update(status="quarantine", reasons=["attempt_not_demonstrably_full_credit"])
            result.append(record)
            continue
        stem, options = parse_options(chunk[1:] if not corrected else chunk, radio=True)
        for option in options:
            option["correct"] = option["selected"]
        record.update(prompt=stem, options=options,
                      answer_evidence="; ".join(o["text"] for o in options if o["correct"]),
                      answer_origin="publisher_corrected_circle" if corrected else "selected_radio_and_full_credit",
                      explanation_source="")
        result.append(finish(record, chunk, document))
    return result


def parse_inline_keys(document: dict) -> list[dict]:
    # Only the teacher's numbered answer sheet; prose answers are preserved for review.
    lines = [l for p in document["pages"] for l in page_lines(p)]
    result = []
    for label, chunk in groups(lines, re.compile(r"^\d+\.\s+")):
        split = next((i for i,l in enumerate(chunk) if ANSWER.search(l["text"])), None)
        if split is None:
            continue
        record = source_record(document, label, chunk, "inline_explicit_key")
        body = " ".join(l["text"] for l in chunk[:split])
        parts = list(re.finditer(r"(?<!\w)([a-hа])\)\s*", body, re.I))
        answer = ANSWER.sub("", " ".join(l["text"] for l in chunk[split:]), count=1)
        key_match = re.match(r"([a-h](?:\s*,\s*[a-h])*)(?:\s*[,.;]|\s*$)", answer, re.I)
        if not parts or not key_match or re.search(r"hoặc|chấp nhận|khả năng cho", answer, re.I):
            record.update(status="quarantine", reasons=["prose_or_ambiguous_answer_requires_review"])
            result.append(record)
            continue
        correct = set(re.findall(r"[a-h]", key_match.group(1).lower()))
        options = [{"label": m.group(1).upper().replace("А", "A"),
                    "text": text_clean(body[m.end():parts[i+1].start() if i+1<len(parts) else len(body)]),
                    "correct": m.group(1).lower().replace("а", "a") in correct}
                   for i,m in enumerate(parts)]
        record.update(prompt=re.sub(r"^\d+\.\s*", "", body[:parts[0].start()]), options=options,
                      answer_evidence=answer, answer_origin="explicit_source_key",
                      explanation_source=answer[key_match.end():].strip(" ,.;"))
        result.append(finish(record, chunk, document))
    return result


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    inventory = [json.loads(l) for l in (args.dataset / "inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    all_records, coverage, queue = [], [], []
    for index, source in enumerate(inventory, 1):
        document = json.loads((args.dataset / "extracted" / (source["source_id"] + ".json")).read_text(encoding="utf-8"))
        full = "\n".join(p["raw_text"] for p in document["pages"])
        if re.search(r"the correct answers? (?:is|are)", full, re.I) and re.search(r"Question\s+\d+", full):
            records = parse_moodle(document)
        elif "Corrected" in full:
            records = parse_radios(document, corrected=True)
        elif re.search(r"\bCorrect\b", full) and re.search(r"\d+/\d+\s*Points", full, re.I):
            records = parse_radios(document, corrected=False)
        elif "ĐÁP ÁN VẮN TẮT" in full:
            records = parse_inline_keys(document)
        elif re.search(r"(?m)^ANSWER\s*:\s*[A-H]\s*$",full):
            from answer_letter_parser import parse_answer_letters
            records = parse_answer_letters(document)
        else:
            records = []
        all_records.extend(records)
        coverage.append({"source_id":source["source_id"],"course":source["course"],
                         "relative_path":source["relative_path"],"pages":source.get("page_count",len(document["pages"])),
                         "parsed":len(records),"candidates":sum(r["status"]=="candidate" for r in records),
                         "low_text_pages":source.get("low_text_pages",0),
                         "status":"parsed" if records else "needs_ocr_or_answer_review"})
        if not document["pages"]:
            queue.append({"source_id":source["source_id"],"page":None,
                          "reason":source["status"],"extracted_file":f"extracted/{source['source_id']}.json"})
        covered = {p for r in records for p in r["pages"]}
        for page in document["pages"]:
            if page["page"] not in covered:
                queue.append({"source_id":source["source_id"],"page":page["page"],
                              "reason":"ocr_required" if len(re.sub(r"\s","",page["text"]))<80 else "no_supported_verified_answer",
                              "extracted_file":f"extracted/{source['source_id']}.json"})
        if index%40==0:
            print(json.dumps({"sources":index,"records":len(all_records)},ensure_ascii=False),flush=True)
    write_jsonl(args.dataset/"questions_all.jsonl",all_records)
    write_jsonl(args.dataset/"questions_candidates.jsonl",[r for r in all_records if r["status"]=="candidate"])
    write_jsonl(args.dataset/"questions_quarantine.jsonl",[r for r in all_records if r["status"]!="candidate"])
    write_jsonl(args.dataset/"source_coverage.jsonl",coverage)
    write_jsonl(args.dataset/"pages_review_queue.jsonl",queue)
    stats={"records":len(all_records),"statuses":dict(Counter(r["status"] for r in all_records)),
           "quarantine_reasons":dict(Counter(reason for r in all_records for reason in r.get("reasons",[]))),
           "candidate_parsers":dict(Counter(r["parser"] for r in all_records if r["status"]=="candidate")),
           "candidate_courses":dict(Counter(r["course"] for r in all_records if r["status"]=="candidate")),
           "uncovered_pages":len(queue),"page_review_reasons":dict(Counter(r["reason"] for r in queue))}
    dump(args.dataset/"question_extraction_report.json",stats)
    print(json.dumps(stats,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
