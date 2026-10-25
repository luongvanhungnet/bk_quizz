"""CPU-only scoring. Source keys are references, not expert verified truth."""
import json
import math
import re
import unicodedata


def norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text.strip(), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def score_mcq(text, gold, valid_labels):
    try:
        obj = strict_json(text)
        labels = obj["correct_labels"]
        valid = (set(obj) == {"correct_labels"} and isinstance(labels, list)
                 and len(labels) > 0 and all(isinstance(x, str) for x in labels)
                 and len(labels) == len(set(labels)) and set(labels) <= set(valid_labels))
    except (ValueError, TypeError, KeyError):
        valid, labels = False, []
    return {"valid_json_answer": bool(valid), "source_key_exact_match": bool(valid and set(labels) == set(gold)),
            "predicted_labels": labels}


def score_quiz(text, reference, context):
    # This validator is copied from the audited release, bundled alongside this module.
    from quiz_schema import validate_output
    try:
        obj = strict_json(text)
    except (ValueError, TypeError):
        return {"json_valid": False, "schema_and_citations_valid": False,
                "reference_alignment_assessable": False, "source_answer_exact_match": None,
                "errors": ["Not a single strict JSON object"]}
    errors = validate_output(obj, context)
    questions = obj.get("questions", []) if isinstance(obj, dict) else []
    if not isinstance(questions, list):
        questions = []
    if len(questions) != 1:
        errors.append("Exactly one question requested")
    if len(questions) == 1 and isinstance(questions[0], dict):
        q = questions[0]
        if q.get("type") not in {"SINGLE_CHOICE", "MULTIPLE_SELECT"}:
            errors.append("Requested choice question type")
        if q.get("acceptedAnswers") != []:
            errors.append("Choice acceptedAnswers must be present and empty")
    # Exact matching is deliberately conservative: paraphrases need semantic review.
    aligned, match = False, None
    if not errors:
        q = questions[0]
        aligned = (norm(q["prompt"]) == norm(reference["prompt"])
                   and sorted(norm(o["text"]) for o in q["options"])
                   == sorted(norm(o["text"]) for o in reference["options"]))
        if aligned:
            match = sorted(norm(o["text"]) for o in q["options"] if o["correct"]) == sorted(
                norm(o["text"]) for o in reference["options"] if o["correct"])
    return {"json_valid": True, "schema_and_citations_valid": not errors,
            "reference_alignment_assessable": aligned, "source_answer_exact_match": match, "errors": errors}


def wilson(successes, n):
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return [max(0, center-half), min(1, center+half)]
