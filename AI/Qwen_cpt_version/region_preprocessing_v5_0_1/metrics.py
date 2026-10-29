"""Reference-based metrics. No machine confidence or bucket is a ground truth.

evaluate_metrics accepts human-reference rows:
  {id, reference_verified: true, reviewer, reference: {text?, latex?, bbox?, label?,
   component_ids?}, assessment?: {groundedness?: 0..1}}
and prediction rows keyed by id: {text?, latex?, bbox?, label?,
covered_component_ids?: [...], structural_valid?: bool}.
Component IDs must be matched by a human or a documented reference annotation;
an LLM inventing matching strings is not a verified coverage assessment.
Q is absent until every A/G/C/L/D dimension has human-reference evidence.
"""
from __future__ import annotations

import argparse
import json
import math
import unicodedata
from pathlib import Path

from cross_validation import formula_structure_issues


def normalize_reference_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def edit_distance(reference, prediction) -> int:
    if len(reference) < len(prediction):
        reference, prediction = prediction, reference
    previous = list(range(len(prediction) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(prediction, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def cer(reference: str, prediction: str) -> float | None:
    reference, prediction = normalize_reference_text(reference), normalize_reference_text(prediction)
    return edit_distance(reference, prediction) / len(reference) if reference else None


def wer(reference: str, prediction: str) -> float | None:
    reference, prediction = normalize_reference_text(reference).split(), normalize_reference_text(prediction).split()
    return edit_distance(reference, prediction) / len(reference) if reference else None


def bbox_iou(reference, prediction) -> float:
    def checked(box):
        if len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in box):
            raise ValueError("invalid bbox")
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("bbox must have positive area")
        return box
    a, b = checked(reference), checked(prediction)
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union


iou = bbox_iou


def formula_exact_match(reference: str, prediction: str) -> bool:
    # Do not erase braces, operators, accents, signs, or interchangeable-looking symbols.
    return (bool(normalize_reference_text(reference)) and not formula_structure_issues(reference)
            and not formula_structure_issues(prediction)
            and normalize_reference_text(reference) == normalize_reference_text(prediction))


def label_accuracy(reference_labels, prediction_labels) -> float | None:
    references, predictions = list(reference_labels), list(prediction_labels)
    if len(references) != len(predictions):
        raise ValueError("labels must be aligned")
    return sum(a == b for a, b in zip(references, predictions)) / len(references) if references else None


def image_label_alignment(human_judgments) -> float | None:
    judgments = [j for j in human_judgments if j is not None]
    if any(not isinstance(j, bool) for j in judgments):
        raise ValueError("alignment requires human true/false judgments")
    return sum(judgments) / len(judgments) if judgments else None


def coverage(correct_components: int, total_components: int) -> float | None:
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (correct_components, total_components)):
        raise ValueError("component counts must be integers")
    if not 0 <= correct_components <= total_components:
        raise ValueError("invalid component counts")
    return correct_components / total_components if total_components else None


def composite_quality(dimensions: dict) -> float | None:
    weights = {"A": .30, "G": .25, "C": .20, "L": .15, "D": .10}
    if any(dimensions.get(key) is None for key in weights):
        return None
    if any(isinstance(dimensions[key], bool) or not isinstance(dimensions[key], (int, float))
           or not math.isfinite(dimensions[key]) or not 0 <= dimensions[key] <= 1 for key in weights):
        raise ValueError("quality dimensions must be finite numbers in [0,1]")
    return sum(weights[key] * dimensions[key] for key in weights)


def _mean(values):
    return sum(values) / len(values) if values else None


def evaluate_metrics(gold_records, predictions=None) -> dict:
    gold_records = list(gold_records)
    if predictions is None:
        predictions = [dict(row.get("prediction", {}), id=row["id"]) for row in gold_records]
    by_id = {}
    for row in predictions:
        if row["id"] in by_id:
            raise ValueError("duplicate prediction id")
        by_id[row["id"]] = row
    seen_gold = set()
    chars = char_errors = words = word_errors = correct_components = total_components = 0
    labels, formulas, layouts, grounded, structures, alignments = [], [], [], [], [], []
    evaluated = skipped = missing = 0
    for row in gold_records:
        if row["id"] in seen_gold:
            raise ValueError("duplicate reference id")
        seen_gold.add(row["id"])
        if row.get("reference_verified") is not True or not str(row.get("reviewer", "")).strip():
            skipped += 1
            continue
        prediction = by_id.get(row["id"])
        if prediction is None:
            missing += 1
            prediction = {"structural_valid": False, "covered_component_ids": []}
        evaluated += 1
        reference = row.get("reference", {})
        assessment = row.get("assessment", {})
        if "text" in reference:
            ref, pred = normalize_reference_text(reference["text"]), normalize_reference_text(prediction.get("text", ""))
            if ref:
                chars += len(ref)
                char_errors += edit_distance(ref, pred)
                ref_words, pred_words = ref.split(), pred.split()
                words += len(ref_words)
                word_errors += edit_distance(ref_words, pred_words)
        if "label" in reference:
            labels.append(reference["label"] == prediction.get("label"))
        if "latex" in reference:
            formulas.append(formula_exact_match(reference["latex"], prediction.get("latex", "")))
        if "bbox" in reference:
            layouts.append(bbox_iou(reference["bbox"], prediction["bbox"]) if prediction.get("bbox") is not None else 0.0)
        if "component_ids" in reference and "covered_component_ids" in prediction:
            expected = set(reference["component_ids"])
            supplied = set(prediction.get("covered_component_ids", []))
            correct_components += len(expected & supplied)
            total_components += len(expected)
        if "groundedness" in assessment:
            value = assessment["groundedness"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("groundedness must be a human-assessed number in [0,1]")
            grounded.append(value)
        if "image_label_aligned" in assessment:
            value = assessment["image_label_aligned"]
            if not isinstance(value, bool):
                raise ValueError("image_label_aligned must be human boolean")
            alignments.append(value)
        if isinstance(prediction.get("structural_valid"), bool):
            structures.append(prediction["structural_valid"])
    dimensions = {"A": _mean(labels), "G": _mean(grounded),
                  "C": coverage(correct_components, total_components), "L": _mean(layouts), "D": _mean(structures)}
    return {"reference_rows": len(gold_records), "evaluated": evaluated,
            "skipped_unverified_reference": skipped, "missing_predictions": missing,
            "CER": char_errors / chars if chars else None, "WER": word_errors / words if words else None,
            "Label_Accuracy": _mean(labels), "Layout_IoU": _mean(layouts),
            "Image_Label_Alignment": image_label_alignment(alignments), "Formula_Exact_Match": _mean(formulas),
            "Coverage": dimensions["C"], "dimensions": dimensions, "Q": composite_quality(dimensions),
            "Q_scale": "0..1; multiply by 100 for percentage points",
            "denominators": {"characters": chars, "words": words, "labels": len(labels),
                             "formulas": len(formulas), "layouts": len(layouts), "groundedness": len(grounded),
                             "components": total_components, "structures": len(structures)},
            "normalization": "NFC and whitespace collapse only; mathematical symbols retained"}


def _read(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    return json.loads(path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", required=True)
    parser.add_argument("--predictions")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(output)
    report = evaluate_metrics(_read(args.references), _read(args.predictions) if args.predictions else None)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
