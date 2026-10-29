"""Constrained re-evaluation of the old 40/12 cases, now regression/dev only."""
import argparse
from pathlib import Path
import re
from collections import Counter
from common import canonical, digest, load, save, sha, verify_files
from quality import legacy_schema, legacy_strict_score, mcq_schema


def main(args):
    manifest = verify_files(args.root)
    tasks = load(args.root/"legacy_tasks.json")
    if args.mode == "preflight":
        print(canonical({"files_verified": True, "tasks": len(tasks), "scope": "old_test_is_now_regression_dev"}).decode()); return
    if args.mode == "report":
        comparison = {"scope": "old test reused for diagnostics, not independent test", "variants": {}}
        for v in ("base", "cpt", "sft", "cpt_sft"):
            comparison["variants"][v] = load(args.output/v/"summary.json")
        save(args.output/"comparison.json", comparison)
        lines = ["# Structured decoding diagnostics", "", "Old40/12 cases are regression/dev; unchanged raw scores are preserved.", "",
                 "| Model | Raw MCQ | Schema MCQ | Raw valid quiz | Schema valid quiz, exact source IDs |", "|---|---:|---:|---:|---:|"]
        for v, s in comparison["variants"].items():
            lines.append(f"| {v} | {s['raw_mcq']}/40 | {s['constrained_mcq']}/40 | {s['raw_quiz']}/12 | {s['constrained_quiz']}/12 |")
        (args.output/"DIAGNOSTICS.md").write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines)); return
    from engine import Generator, environment, load_model
    adapter = args.root/"models"/args.variant if args.variant != "base" else None
    env = environment()
    original_env = load(args.root/'baseline_identity.json')
    if env['gpu'] != original_env['gpu'] or env['dtype'] != original_env['dtype'] or any(env['packages'][k] != v for k, v in original_env['packages'].items() if k in env['packages']):
        raise ValueError('Raw-vs-schema diagnostics require the original T4/FP16 and package versions; use the documented runtime')
    baseline = load(args.root/"baseline_comparison.json")["summaries"][args.variant]
    identity = {"manifest_sha256": sha(args.root/"manifest.json"), "variant": args.variant, "environment": env,
                "decoder": "LMFE0.11.3", "no_json_repair": True}
    out = args.output/args.variant; out.mkdir(parents=True, exist_ok=True)
    if (out/"identity.json").exists() and load(out/"identity.json") != identity: raise ValueError("Use a new run name after config/environment changes")
    save(out/"identity.json", identity)
    model, tok = load_model(args.root/"tokenizer", adapter); gen = Generator(model, tok)
    records = []
    for i, task in enumerate(tasks):
        path = out/"samples"/(task["id"]+".json")
        if path.exists():
            cached = load(path)
            if cached["identity"] != digest(identity) or cached["sha256"] != digest(cached["record"]): raise ValueError("Invalid cache")
            records.append(cached["record"]); continue
        from legacy_scoring import score_mcq
        multi = len(task["gold_labels"]) > 1
        answer = gen.one(task["closed_book_messages"], mcq_schema(task["valid_labels"], multi), 128)
        answer["score"] = score_mcq(answer["text"], task["gold_labels"], task["valid_labels"])
        r = {"id": task["id"], "mcq": answer}
        if task["id"] in manifest["legacy_generation_ids"]:
            ids = re.findall(r"\[([^\[\]\n]+)\]", task["grounded_messages"][-1]["content"])
            quiz = gen.one(task["grounded_messages"], legacy_schema(ids), 2048)
            quiz["score"] = legacy_strict_score(quiz["text"], task); r["quiz"] = quiz
        save(path, {"identity": digest(identity), "sha256": digest(r), "record": r}); records.append(r)
        print(canonical({"variant": args.variant, "done": i+1, "of": len(tasks)}).decode(), flush=True)
    old_records=load(args.root/'baseline_records.json')[args.variant]
    raw_exact=sum(legacy_strict_score(old_records[t['id']]['grounded_quiz']['text'],t)['structural_valid_v2'] for t in tasks if 'grounded_quiz' in old_records[t['id']])
    summary = {"raw_mcq": baseline["source_key_matches"], "raw_quiz_old_validator": baseline["grounded_valid"],"raw_quiz":raw_exact,
               "constrained_mcq": sum(r["mcq"]["score"]["source_key_exact_match"] for r in records),
               "constrained_mcq_invalid": sum(not r["mcq"]["score"]["valid_json_answer"] for r in records),
               "constrained_quiz": sum(r.get("quiz", {}).get("score", {}).get("structural_valid_v2", False) for r in records),
               "constrained_quiz_old_validator":sum(r.get('quiz',{}).get('score',{}).get('schema_and_citations_valid',False) for r in records),
               "semantic_quality_verified": False, "scope": "regression_dev_only"}
    save(out/"summary.json", summary); print(canonical(summary).decode(), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--output", type=Path)
    p.add_argument("--variant", choices=("base", "cpt", "sft", "cpt_sft")); p.add_argument("--mode", choices=("preflight", "evaluate", "report"), default="evaluate")
    args = p.parse_args()
    if args.mode != "preflight" and not args.output: p.error("--output required")
    if args.mode == "evaluate" and not args.variant: p.error("--variant required")
    main(args)
