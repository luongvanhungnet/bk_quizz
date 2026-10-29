"""Separate syntax, structural safety, source consistency and human semantics."""
from __future__ import annotations
import copy
import re
from common import norm, strict_json


def selection_quality(scores, loss):
    if not scores:raise ValueError('Validation generation must not be empty')
    import math
    if not math.isfinite(loss):raise ValueError('Nonfinite validation loss')
    n=len(scores)
    usable=sum(s['usable_proxy'] for s in scores)/n
    correct=sum(s['reference_answer_preserved'] for s in scores)/n
    structural=sum(s['structural_valid'] for s in scores)/n
    return {'eval_generation_quality':100*usable+10*correct+structural-min(loss,10)*.001,
            'eval_generation_usable':usable,'eval_generation_answer':correct,'eval_generation_structure':structural}


def compact_schema(evidence_ids):
    text = {"type": "string", "minLength": 1, "maxLength": 1400}
    ids = {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string", "enum": evidence_ids}}
    option = {"type": "object", "properties": {"text": text, "correct": {"type": "boolean"}}, "required": ["text", "correct"], "additionalProperties": False}
    reason = {"type": "object", "properties": {"option": {"type": "integer", "minimum": 0, "maximum": 3}, "reason": text, "evidence_ids": ids},
              "required": ["option", "reason", "evidence_ids"], "additionalProperties": False}
    props = {"type": {"type": "string", "enum": ["SINGLE_CHOICE", "MULTIPLE_SELECT"]},
             "prompt": text, "options": {"type": "array", "minItems": 4, "maxItems": 4, "items": option},
             "principle": text, "application": text, "distractor_explanations": {"type": "array", "minItems": 1, "maxItems": 3, "items": reason},
             "evidence_ids": ids}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def mcq_schema(labels, multi=False):
    return {"type": "object", "additionalProperties": False,
            "properties": {"correct_labels": {"type": "array", "minItems": 2 if multi else 1,
              "maxItems": len(labels)-1 if multi else 1, "items": {"type": "string", "enum": labels}}}, "required": ["correct_labels"]}


def compact_score(text, sample):
    errors = []; q = None
    try: q = strict_json(text)
    except (ValueError, TypeError):
        return {"json_valid": False, "structural_valid": False, "reference_answer_preserved": False,
                "source_supported_contrast": False, "usable_proxy": False, "errors": ["invalid_json"], "human_semantics_verified": False}
    required = {"type", "prompt", "options", "principle", "application", "distractor_explanations", "evidence_ids"}
    if not isinstance(q, dict) or set(q) != required:
        errors.append("exact_fields_required")
        if not isinstance(q, dict): q = {}
    for field in ("prompt", "principle", "application"):
        if not isinstance(q.get(field), str) or not 1 <= len(q[field].strip()) <= 1400: errors.append("invalid_"+field)
    options = q.get("options", [])
    if not isinstance(options, list): options = []
    if len(options) != 4: errors.append("exactly_four_options")
    for o in options:
        if not isinstance(o, dict) or set(o) != {"text", "correct"} or not isinstance(o.get("text"), str) or not o["text"].strip() or type(o.get("correct")) is not bool:
            errors.append("invalid_option")
    valid_options = [o for o in options if isinstance(o, dict) and isinstance(o.get("text"), str)]
    if len({norm(o["text"]) for o in valid_options}) != len(options): errors.append("duplicate_options")
    count = sum(o.get("correct") is True for o in valid_options)
    if q.get("type") == "SINGLE_CHOICE":
        if count != 1: errors.append("single_choice_cardinality")
    elif q.get("type") == "MULTIPLE_SELECT":
        if not 2 <= count < len(options): errors.append("multi_select_cardinality")
    else: errors.append("unsupported_type")
    ev = {e["id"]: e for e in sample["evidence"]}
    def check_ids(values):
        return isinstance(values, list) and 1 <= len(values) <= 4 and all(isinstance(x, str) and x in ev for x in values) and len(set(values)) == len(values)
    if not check_ids(q.get("evidence_ids")): errors.append("unknown_evidence_id")
    reasons = q.get("distractor_explanations")
    if not isinstance(reasons, list): reasons = []
    indices = []
    for reason in reasons:
        if (not isinstance(reason, dict) or set(reason) != {"option", "reason", "evidence_ids"}
                or type(reason.get("option")) is not int or not 0 <= reason["option"] < len(options)
                or not isinstance(reason.get("reason"), str) or not 1<=len(reason["reason"].strip())<=1400 or not check_ids(reason.get("evidence_ids"))):
            errors.append("invalid_distractor_explanation"); continue
        indices.append(reason["option"])
    wrong = [i for i, o in enumerate(options) if isinstance(o, dict) and o.get("correct") is False]
    if sorted(indices) != wrong: errors.append("each_wrong_option_requires_one_explanation")
    if check_ids(q.get('evidence_ids')) and set(q['evidence_ids'])!=set(sample['reference']['evidence_ids']):
        errors.append('answer_evidence_does_not_match_target_source')
    expected_wrong_sources={norm(sample['reference']['options'][r['option']]['text']):set(r['evidence_ids']) for r in sample['reference']['distractor_explanations']}
    for r in reasons:
        if not isinstance(r,dict) or type(r.get('option')) is not int or not 0<=r['option']<len(options):continue
        option=options[r['option']]
        if not isinstance(option,dict) or not isinstance(option.get('text'),str) or not check_ids(r.get('evidence_ids')):continue
        needed=expected_wrong_sources.get(norm(option['text']))
        if needed and not needed<=set(r['evidence_ids']):errors.append('wrong_source_for_distractor_explanation')
    # Exact fact-card references make this a conservative proxy, not a semantic judge.
    correct = sorted(norm(o["text"]) for o in valid_options if o.get("correct") is True)
    gold = sorted(norm(x) for x in sample["gold_texts"])
    preserved = bool(correct) and correct == gold
    if q.get("type") != sample["reference"]["type"]: errors.append("blueprint_type_changed")
    prompt = q.get("prompt") if isinstance(q.get("prompt"), str) else ""
    def contains(fragment):
        if re.fullmatch(r'\d+(?:[.,]\d+)?',fragment):return re.search(r'(?<!\d)'+re.escape(fragment)+r'(?!\d)',prompt) is not None
        return norm(fragment) in norm(prompt)
    if sample.get("required_prompt_fragments") and any(not contains(fragment) for fragment in sample["required_prompt_fragments"]):
        errors.append("essential_prompt_information_missing")
    content_tokens = sample.get("prompt_content_tokens", [])
    if content_tokens and sum(w in norm(prompt) for w in content_tokens) < max(1, len(content_tokens)//4):
        errors.append("prompt_source_overlap_low_needs_review")
    expected = {norm(o["text"]) for o in sample["reference"]["options"]}
    all_anchored = len(valid_options) == 4 and {norm(o["text"]) for o in valid_options} == expected
    return {"json_valid": True, "structural_valid": not errors, "reference_answer_preserved": preserved,
            "source_supported_contrast": all_anchored, "usable_proxy": not errors and preserved and all_anchored,
            "errors": sorted(set(errors)), "human_semantics_verified": False}


def hydrate(q, evidence):
    """Only application code emits exact sourceId/quotes, never invented strings."""
    ev = {e["id"]: e for e in evidence}
    def citations(ids):
        if any(i not in ev for i in ids): raise ValueError("Unknown evidence ID")
        return [{"sourceId": ev[i]["source_id"], "evidenceQuote": ev[i]["text"]} for i in dict.fromkeys(ids)]
    wrong = " ".join(f"Phương án {chr(65+r['option'])}: {r['reason']}" for r in q["distractor_explanations"])
    explanation = "Căn cứ: "+q["principle"]+" Áp dụng: "+q["application"]+" "+wrong
    used = q["evidence_ids"]+[e for r in q["distractor_explanations"] for e in r["evidence_ids"]]
    return {"questions": [{"type": q["type"], "prompt": q["prompt"], "options": copy.deepcopy(q["options"]),
        "acceptedAnswers": [], "explanation": explanation, "questionCitations": citations(q["evidence_ids"]),
        "answerCitations": citations(q["evidence_ids"]), "explanationCitations": citations(used)}]}


def legacy_schema(source_ids):
    text = {"type": "string", "minLength": 1, "maxLength": 1600}
    citation = {"type": "object", "properties": {"sourceId": {"type": "string", "enum": source_ids}, "evidenceQuote": text},
                "required": ["sourceId", "evidenceQuote"], "additionalProperties": False}
    cites = {"type": "array", "items": citation, "minItems": 1, "maxItems": 3}
    props = {"type": {"type": "string", "enum": ["SINGLE_CHOICE", "MULTIPLE_SELECT"]}, "prompt": text, "explanation": text,
             "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": {"type": "object", "properties": {"text": text, "correct": {"type": "boolean"}}, "required": ["text", "correct"], "additionalProperties": False}},
             "acceptedAnswers": {"type": "array", "items": text, "maxItems": 0},
             "questionCitations": cites, "answerCitations": cites, "explanationCitations": cites}
    question = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return {"type": "object", "properties": {"questions": {"type": "array", "minItems": 1, "maxItems": 1, "items": question}}, "required": ["questions"], "additionalProperties": False}


def legacy_strict_score(text, task):
    # Compatibility with the first benchmark, plus exact source identifiers.
    from legacy_scoring import score_quiz
    result = score_quiz(text, task["reference_question"], task["grounded_messages"][-1]["content"])
    exact_ids = re.findall(r"\[([^\[\]\n]+)\]", task["grounded_messages"][-1]["content"])
    exact = False
    if result["json_valid"]:
        obj = strict_json(text)
        questions = obj.get("questions") if isinstance(obj, dict) else None
        if isinstance(questions, list) and questions and all(isinstance(q, dict) for q in questions):
            exact = all(isinstance(c, dict) and c.get("sourceId") in exact_ids
                        for q in questions for k in ("questionCitations", "answerCitations", "explanationCitations")
                        for c in (q.get(k) if isinstance(q.get(k), list) else [{}]))
    result["exact_context_ids"] = exact
    result["structural_valid_v2"] = result["schema_and_citations_valid"] and exact
    result["semantic_quality_verified"] = False
    return result
