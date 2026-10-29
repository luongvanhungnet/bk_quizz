"""Integrity, split isolation, source spans, reference quality and exact token masks."""
import argparse
from pathlib import Path
from common import canonical, digest, encode, load, norm, read_rows, sha, verify_files
from quality import compact_score


def check(root, tokenizer=None):
    root = Path(root); manifest = verify_files(root)
    if manifest["schema"] != "bkquiz-theory-sft-v2": raise ValueError("Wrong dataset")
    if manifest["source_policy"] != "completed_native_text_only": raise ValueError("No unfinished/VLM source allowed")
    facts = {f["id"]: f for f in read_rows(root/"facts.jsonl")}
    locks = load(root/"split_lock.json")
    if not locks["assigned_before_question_generation"]: raise ValueError("Unfrozen split")
    groups, concepts, ids, counts = {}, {}, set(), {}
    for split, n in manifest["counts"].items():
        samples = read_rows(root/(split+".samples.jsonl"))
        messages = read_rows(root/(split+".messages.jsonl"))
        tokens = read_rows(root/(split+".tokenized.jsonl"))
        if len(samples) != n or len(messages) != n or len(tokens) != n: raise ValueError("Split count mismatch")
        counts[split] = n
        for row, msg, encoded in zip(samples, messages, tokens):
            if row["split"] != split or row["id"] in ids or row["id"] != encoded["id"] or row["id"] != msg["id"]:
                raise ValueError("Sample identity/split mismatch")
            ids.add(row["id"])
            if row["messages"] != msg["messages"]: raise ValueError("Training chat differs")
            if not compact_score(canonical(row["reference"]).decode(), row)["usable_proxy"]: raise ValueError("Invalid supervised reference")
            # The model prompt contains theory and planning only, no hidden gold/reference JSON.
            user = load_user(row)
            kind = row.get("training_task", "theory_to_quiz")
            expected = {"theory_to_quiz": {"task", "course", "type", "focus_concepts", "option_terms", "evidence"},
                        "source_grounded_qa": {"task", "question", "evidence"},
                        "closed_book_mcq_format": {"task", "prompt", "options"}}
            if kind not in expected or set(user) != expected[kind]: raise ValueError("Unexpected target leakage field")
            if kind != "theory_to_quiz":
                if split != "train" or row["messages"][-1]["content"] != canonical(row["replay_reference"]).decode(): raise ValueError("Rehearsal target changed")
                if kind == "source_grounded_qa" and row["replay_reference"] != {"answer": facts[row["target_fact_id"]]["definition"], "evidence_ids": ["E1"]}:
                    raise ValueError("QA answer differs from source fact")
                if kind == "closed_book_mcq_format" and row["replay_reference"] != {"correct_labels": [chr(65+j) for j, o in enumerate(row["reference"]["options"]) if o["correct"]]}:
                    raise ValueError("MCQ rehearsal answer differs")
            for e, fid in zip(row["evidence"], row["context_fact_ids"]):
                f = facts[fid]
                if f["split"] != split or f["extraction"] != "completed_native_text_verbatim_span": raise ValueError("Source split/type mismatch")
                if e["text"] != f["quote"] or e["source_id"] != f["record_id"] or e["source_sha256"] != f["source_sha256"]:
                    raise ValueError("Evidence was rewritten or fabricated")
                if locks["assignments"][fid] != {"split": split, "group": f["split_group"]}: raise ValueError("Split lock changed")
                for mapping, key in ((groups, f["split_group"]), (concepts, norm(f["concept"]))):
                    if key in mapping and mapping[key] != split: raise ValueError("Cross-split source leakage")
                    mapping[key] = split
            if tokenizer is not None and encode(tokenizer, row["messages"], row["id"]) != encoded:
                raise ValueError("Assistant mask/tokenization mismatch")
            if not any(x != -100 for x in encoded["labels"]): raise ValueError("No supervised assistant tokens")
    if "test" not in manifest["counts"] and any(root.glob("test.*")): raise ValueError("Held-out test must not be shipped in the training input")
    return {"counts": counts, "manifest_sha256": sha(root/"manifest.json"), "reference_and_source_consistency_checked": True,
            "masks_reencoded": tokenizer is not None, "test_used_for_training_or_selection": False,
            "expert_semantics_verified": False, "human_approvals_created": 0}


def load_user(sample):
    import json
    return json.loads(sample["messages"][1]["content"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--data", type=Path, required=True); p.add_argument("--tokenizer", type=Path, required=True)
    args = p.parse_args(); from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(args.tokenizer), local_files_only=True, trust_remote_code=False)
    print(canonical(check(args.data, tok)).decode())
