"""Audit returned four-way bytes and recompute scores without rerunning a model."""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import statistics
import sys
import zipfile

HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent / "model_comparisons/four_way_20261025"
INPUT = RELEASE/"input"
OUT = RELEASE/"returned_analysis"
sys.path.insert(0, str(INPUT/"runtime"))
from sft_contract import canonical, digest, load, save, sha
from scoring import score_mcq, score_quiz, strict_json, wilson

VARIANTS = ("base", "cpt", "sft", "cpt_sft")


def safe_archive(path):
    z = zipfile.ZipFile(path)
    entries = z.infolist()
    names = [i.filename for i in entries]
    if len(names) != len(set(names)) or len(names) > 1000 or sum(i.file_size for i in entries) > 256*1024**2:
        raise ValueError("Archive budget/duplicate members")
    for info in entries:
        rel = PurePosixPath(info.filename)
        if (rel.is_absolute() or any(p in {"..", "."} for p in rel.parts) or ":" in info.filename
                or "\\" in info.filename or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK):
            raise ValueError("Unsafe member: " + info.filename)
    return z


def strip_fence(text):
    match = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", text, re.S | re.I)
    return match.group(1) if match else text


def first_json_object(text):
    # DIAGNOSTIC ONLY: never used to replace the strict original benchmark.
    text = strip_fence(text).lstrip()
    try:
        obj, end = json.JSONDecoder().raw_decode(text)
        return obj, text[end:].strip()
    except ValueError:
        return None, ""


def main(path):
    OUT.mkdir(exist_ok=True)
    tasks = {t["id"]: t for t in load(INPUT/"tasks.json")}
    manifest_sha = sha(INPUT/"comparison_manifest.json")
    identities, rows, summaries = {}, {}, {}
    audit = {"archive_sha256": sha(path), "input_manifest_sha256": manifest_sha,
             "gpu_not_rerun": True, "original_strict_scores_preserved": True}
    diagnostic, semantic_packet = {}, []
    with safe_archive(path) as z:
        names = set(z.namelist())
        def obj(name):
            return json.loads(z.read(name))
        audit["members"] = len(names)
        for name in names:
            if name.endswith((".json", ".md")):
                destination = OUT/"extracted"/name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(z.read(name))
        for variant in VARIANTS:
            identities[variant] = ident = obj(variant+"/identity.json")
            if ident["input_manifest_sha256"] != manifest_sha:
                raise ValueError("Input identity differs from frozen input")
            done = obj(variant+"/completed.json")
            if done["identity_sha256"] != digest(ident):
                raise ValueError("Identity digest mismatch")
            for name, expected in done["outputs_sha256"].items():
                if hashlib.sha256(z.read(variant+"/"+name)).hexdigest() != expected:
                    raise ValueError("Output hash mismatch")
            summaries[variant] = summary = obj(variant+"/summary.json")
            rows[variant] = selected = {}
            for name in sorted(names):
                if not name.startswith(variant+"/samples/") or not name.endswith(".json"):
                    continue
                env = obj(name)
                r = env["record"]
                if digest(r) != env["record_sha256"] or env["identity_sha256"] != digest(ident):
                    raise ValueError("Sample digest mismatch")
                selected[r["id"]] = r
                task = tasks[r["id"]]
                if score_mcq(r["closed_book"]["text"], task["gold_labels"], task["valid_labels"]) != r["closed_book"]["score"]:
                    raise ValueError("MCQ score differs")
                if "grounded_quiz" in r:
                    g = r["grounded_quiz"]
                    if score_quiz(g["text"], task["reference_question"], task["grounded_messages"][-1]["content"]) != g["score"]:
                        raise ValueError("Quiz score differs")
            if set(selected) != set(tasks) or done["n"] != len(tasks):
                raise ValueError("Test IDs differ")
            if not math.isclose(statistics.mean(r["assistant_nll"] for r in selected.values()), summary["assistant_mean_example_nll"], abs_tol=1e-12):
                raise ValueError("NLL aggregation mismatch")
            hits = sum(r["closed_book"]["score"]["source_key_exact_match"] for r in selected.values())
            invalid = sum(not r["closed_book"]["score"]["valid_json_answer"] for r in selected.values())
            grounded = [r for r in selected.values() if "grounded_quiz" in r]
            if (hits != summary["source_key_matches"] or invalid != summary["mcq_invalid"]
                    or sum(r["grounded_quiz"]["score"]["schema_and_citations_valid"] for r in grounded) != summary["grounded_valid"]):
                raise ValueError("Summary mismatch")
            d = {"mcq_invalid": invalid, "mcq_length_stops": 0, "mcq_system_instruction_echo": 0,
                 "mcq_first_object_assessable": 0, "mcq_first_object_matches": 0,
                 "mcq_first_object_labels": Counter(), "mcq_sole_missing_final_brace": 0,
                 "mcq_missing_brace_labels_matches": 0,
                 "grounded_fenced": 0, "grounded_unfenced_json_valid": 0, "grounded_unfenced_full_valid": 0,
                 "grounded_error_sample_counts": Counter(), "grounded_fence_only_error_sample_counts": Counter(),
                 "strict_valid_and_exact_context_ids": 0, "closed_book_by_course": {}, "samples": []}
            by_course = defaultdict(list)
            for identity, r in selected.items():
                t, c = tasks[identity], r["closed_book"]
                d["mcq_length_stops"] += c["length_stop"]
                d["mcq_system_instruction_echo"] += "dùng nhãn lựa chọn trong câu hỏi" in c["text"]
                first, tail = first_json_object(c["text"])
                first_score = score_mcq(json.dumps(first), t["gold_labels"], t["valid_labels"]) if first is not None else None
                if first_score and first_score["valid_json_answer"]:
                    d["mcq_first_object_assessable"] += 1
                    d["mcq_first_object_matches"] += first_score["source_key_exact_match"]
                    d["mcq_first_object_labels"]["+".join(first_score["predicted_labels"])] += 1
                if c["text"].rstrip().endswith("]") and not c["score"]["valid_json_answer"]:
                    repaired = score_mcq(c["text"]+"}", t["gold_labels"], t["valid_labels"])
                    if repaired["valid_json_answer"]:
                        d["mcq_sole_missing_final_brace"] += 1
                        d["mcq_missing_brace_labels_matches"] += repaired["source_key_exact_match"]
                by_course[t["course"]].append(c["score"])
                if "grounded_quiz" not in r:
                    continue
                g = r["grounded_quiz"]
                unwrapped = strip_fence(g["text"])
                d["grounded_fenced"] += unwrapped != g["text"]
                unwrapped_score = score_quiz(unwrapped, t["reference_question"], t["grounded_messages"][-1]["content"])
                d["grounded_unfenced_json_valid"] += unwrapped_score["json_valid"]
                d["grounded_unfenced_full_valid"] += unwrapped_score["schema_and_citations_valid"]
                for error in set(g["score"]["errors"]):
                    d["grounded_error_sample_counts"][error] += 1
                for error in set(unwrapped_score["errors"]):
                    d["grounded_fence_only_error_sample_counts"][error] += 1
                generated, tail = first_json_object(g["text"])
                question = (generated.get("questions") or [{}])[0] if isinstance(generated, dict) else None
                exact_ids = re.findall(r"\[([^\[\]\n]+)\]", t["grounded_messages"][-1]["content"])
                if g["score"]["schema_and_citations_valid"]:
                    d["strict_valid_and_exact_context_ids"] += all(
                        c.get("sourceId") in exact_ids for k in ("questionCitations", "answerCitations", "explanationCitations") for c in question[k])
                packet = {"id": identity, "variant": variant, "course": t["course"],
                          "reference_prompt": t["reference_question"]["prompt"],
                          "gold_texts": [o["text"] for o in t["reference_question"]["options"] if o["correct"]],
                          "context": t["grounded_messages"][-1]["content"], "original_text": g["text"],
                          "strict_score": g["score"], "fence_only_score": unwrapped_score,
                          "first_parsed_question": question, "non_json_suffix": tail,
                          "length_stop": g["length_stop"]}
                semantic_packet.append(packet)
                d["samples"].append({"id": identity, "strict_valid": g["score"]["schema_and_citations_valid"],
                                     "fence_only_valid": unwrapped_score["schema_and_citations_valid"],
                                     "raw_tokens": g["new_tokens"], "length_stop": g["length_stop"]})
            d["closed_book_by_course"] = {course: {"n": len(rr), "matches": sum(x["source_key_exact_match"] for x in rr),
                "invalid": sum(not x["valid_json_answer"] for x in rr)} for course, rr in by_course.items()}
            diagnostic[variant] = d
        common = ("input_manifest_sha256", "model", "revision", "packages", "dtype", "gpu", "protocol", "generation_count")
        if any(identities[v][k] != identities["base"][k] for v in VARIANTS for k in common):
            raise ValueError("Evaluation environments differ")
        blind, key = obj("blind_review.json"), obj("blind_review_key.json")
        key = {(k["id"], k["label"]): k["variant"] for k in key}
        for task in blind:
            if task["context"] != tasks[task["id"]]["grounded_messages"] or task["reference_question"] != tasks[task["id"]]["reference_question"]:
                raise ValueError("Blind review reference differs")
            for label, text in task["answers"].items():
                if text != rows[key[task["id"], label]][task["id"]]["grounded_quiz"]["text"]:
                    raise ValueError("Blind review output differs")
        for v, adapter in (("cpt", INPUT/"data/assets/cpt_adapter"), ("cpt_sft", INPUT/"models/cpt_sft")):
            if identities[v]["adapter_sha256"] != {n: sha(adapter/n) for n in ("adapter_config.json", "adapter_model.safetensors")}:
                raise ValueError("Wrong adapter identity")
        train = obj("sft_only_training/run_identity.json")
        for name, wanted in train["runtime_sha256"].items():
            if sha(INPUT/"runtime"/name) != wanted:
                raise ValueError("SFT-only training source differs")
        if train["cpt_weights_loaded"] is not False or train["config"] != load(INPUT/"runtime/config.json"):
            raise ValueError("SFT-only did not use the same training config")
        finished = obj("sft_only_training/completed.json")
        present, absent = [], []
        for name, wanted in finished["outputs_sha256"].items():
            key = "sft_only_training/"+name
            if key not in names:
                absent.append(name)
            elif hashlib.sha256(z.read(key)).hexdigest() != wanted:
                raise ValueError("SFT-only archived file hash differs")
            else:
                present.append(name)
        for name, wanted in identities["sft"]["adapter_sha256"].items():
            if hashlib.sha256(z.read("sft_only_training/adapter/"+name)).hexdigest() != wanted:
                raise ValueError("SFT-only eval adapter differs from exported adapter")
            destination = OUT/"extracted/sft_only_training/adapter"/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(z.read("sft_only_training/adapter/"+name))
        from safetensors.numpy import load_file
        import numpy as np
        weights = load_file(str(OUT/"extracted/sft_only_training/adapter/adapter_model.safetensors"))
        if not all(np.isfinite(w).all() for w in weights.values()):
            raise ValueError("Nonfinite SFT-only tensor")
        audit.update(all_160_sample_hashes_and_scores_verified=True, evaluation_environment_matches=True,
                     pinned_input_and_three_adapter_identities_verified=True, sft_only_config_and_runtime_verified=True,
                     all_48_blind_outputs_and_references_match_hashed_samples=True,
                     sft_only_weights_finite=True, sft_only_weight_tensor_count=len(weights),
                     sft_only_weight_parameters=sum(w.size for w in weights.values()),
                     sft_only_present_files_verified=present, sft_only_files_omitted_by_result_packer=absent,
                     summaries=summaries, diagnostics=diagnostic)
    # Paired differences are more appropriate than treating these as independent samples.
    from itertools import combinations
    paired = []
    for a, b in combinations(VARIANTS, 2):
        wins = sum(rows[a][i]["closed_book"]["score"]["source_key_exact_match"] and not rows[b][i]["closed_book"]["score"]["source_key_exact_match"] for i in tasks)
        losses = sum(not rows[a][i]["closed_book"]["score"]["source_key_exact_match"] and rows[b][i]["closed_book"]["score"]["source_key_exact_match"] for i in tasks)
        n = wins+losses
        p = min(1.0, 2*sum(math.comb(n, k) for k in range(min(wins, losses)+1))/2**n) if n else 1.0
        paired.append({"a": a, "b": b, "a_only_correct": wins, "b_only_correct": losses,
                       "mcnemar_exact_two_sided_unadjusted_p": p, "outcome_is_strict_format_plus_source_key_agreement": True})
    audit["paired_strict_mcq_comparison"] = paired
    save(OUT/"AUDIT.json", audit)
    save(OUT/"SEMANTIC_REVIEW_PACKET.json", semantic_packet)
    print(json.dumps({"audit": str(OUT/"AUDIT.json"), "samples_verified": 160,
                      "blind_outputs_verified": 48, "weights_finite": True,
                      "tensor_count": len(weights)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(Path(sys.argv[1]))
