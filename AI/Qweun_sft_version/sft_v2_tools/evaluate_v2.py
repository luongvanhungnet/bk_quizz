"""Final100-source-group holdout, separate from training input/checkpoint selection."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
from common import canonical, digest, load, make_zip, read_rows, save, sha, verify_files
from preflight import check
from quality import compact_schema, compact_score, hydrate, mcq_schema


def mcq_messages(sample):
    q = sample["reference"]
    user = {"prompt": q["prompt"], "options": [{"label": chr(65+i), "text": o["text"]} for i, o in enumerate(q["options"])]}
    return [{"role": "system", "content": 'Trả duy nhất JSON có correct_labels là mảng nhãn tất cả phương án đúng. Không giải thích.'},
            {"role": "user", "content": canonical(user).decode()}]


def score_mcq(text, sample):
    from common import strict_json
    try:
        obj = strict_json(text); labels = obj["correct_labels"]
        valid = (set(obj) == {"correct_labels"} and isinstance(labels, list) and labels
                 and all(isinstance(l, str) and l in "ABCD" for l in labels) and len(labels) == len(set(labels)))
    except (ValueError, KeyError, TypeError): valid, labels = False, []
    expected = {chr(65+i) for i, o in enumerate(sample["reference"]["options"]) if o["correct"]}
    return {"valid": bool(valid), "source_key_match": bool(valid and set(labels) == expected)}


def validate_adapter(run, expected_input_sha):
    provenance = load(run/"MODEL_PROVENANCE.json"); identity = load(run/"identity.json"); done = load(run/"completed.json")
    if provenance.get("variant") != "sft_v2" or provenance.get("cpt_weights_loaded") is not False or provenance.get("test_used_for_training_or_selection") is not False:
        raise ValueError("This notebook only evaluates the fresh-base SFT-v2 artifact")
    if identity["input_sha256"] != expected_input_sha: raise ValueError("Adapter came from another training release")
    for name, expected in done["outputs_sha256"].items():
        if sha(run/name) != expected: raise ValueError("Trained output changed: "+name)
    return run/"adapter"


def wilson(k, n):
    z = 1.959963984540054; p = k/n; d = 1+z*z/n
    mid = (p+z*z/(2*n))/d; half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0, mid-half), min(1, mid+half)]


def cluster_interval(records):
    groups=defaultdict(list)
    # Context cards can span multiple page blocks. Whole-document clustering also
    # groups all overlapping contexts and all three question variants together.
    for r in records:groups[r.get('course',r['split_group'])].append(r['mcq']['score']['source_key_match'])
    units=[(sum(x),len(x)) for x in groups.values()];rng=random.Random(42);values=[]
    for _ in range(2000):
        selected=[rng.choice(units) for _ in units]
        values.append(sum(x[0] for x in selected)/sum(x[1] for x in selected))
    values.sort()
    return [values[49],values[1949]]


def main(args):
    root = args.root.resolve(); manifest = verify_files(root)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(root/"tokenizer"), local_files_only=True, trust_remote_code=False)
    checked = check(root/"data", tok)
    if checked["counts"] != {"test": 100}: raise ValueError("Exactly100frozen test references required")
    samples = read_rows(root/"data/test.samples.jsonl")
    if args.mode == "preflight": print(canonical(checked).decode()); return
    if args.mode == "report": return report(args, manifest, samples)
    from engine import Generator, environment, load_model
    adapter = None if args.variant == "base" else validate_adapter(args.sft_run, manifest["expected_training_input_sha256"])
    identity = {"test_manifest_sha256": sha(root/"manifest.json"), "variant": args.variant,
        "environment": environment(), "adapter_sha256": {n: sha(adapter/n) for n in ("adapter_config.json", "adapter_model.safetensors")} if adapter else {},
        "batch_size": args.batch_size, "generation_limit": args.generation_limit, "decoder": "LMFE0.11.3",
        "max_new_tokens": 1536, "checkpoint_selection_uses_this_test": False}
    folder = args.output/args.variant; folder.mkdir(parents=True, exist_ok=True)
    if (folder/"identity.json").exists() and load(folder/"identity.json") != identity: raise ValueError("Cache identity changed; use a new test run name")
    save(folder/"identity.json", identity)
    model, tok = load_model(root/"tokenizer", adapter); gen = Generator(model, tok)
    # Fixed ordering/sample count chosen before any model output.
    generation_ids = {s["id"] for s in samples[:args.generation_limit]}
    for start in range(0, len(samples), args.batch_size):
        batch = samples[start:start+args.batch_size]; pending = []
        for sample in batch:
            path = folder/"samples"/(sample["id"]+".json")
            if path.exists():
                c = load(path)
                if c["identity"] != digest(identity) or c["sha256"] != digest(c["record"]): raise ValueError("Invalid cached result")
            else: pending.append(sample)
        if not pending: continue
        mcqs = gen.batch([mcq_messages(s) for s in pending], [mcq_schema(list('ABCD'), s["reference"]["type"] == "MULTIPLE_SELECT") for s in pending], 128)
        quiz_samples = [s for s in pending if s["id"] in generation_ids]
        generated = gen.batch([s["messages"][:-1] for s in quiz_samples], [compact_schema([e["id"] for e in s["evidence"]]) for s in quiz_samples], 1536) if quiz_samples else []
        quiz_map = {s["id"]: g for s, g in zip(quiz_samples, generated)}
        for sample, answer in zip(pending, mcqs):
            answer["score"] = score_mcq(answer["text"], sample)
            record = {"id": sample["id"], "course": sample["course"], "test_scope": sample["test_scope"],
                      "split_group":sample['split_group'],"target_fact_id":sample['target_fact_id'],"mcq": answer}
            if sample["id"] in quiz_map:
                q = quiz_map[sample["id"]]; q["score"] = compact_score(q["text"], sample)
                record["quiz"] = q
                if q["score"]["structural_valid"]:
                    record["hydrated_quiz"] = hydrate(json.loads(q["text"]), sample["evidence"])
            save(folder/"samples"/(sample["id"]+".json"), {"identity": digest(identity), "sha256": digest(record), "record": record})
        print(canonical({"variant": args.variant, "done": min(start+len(batch), len(samples)), "of": len(samples)}).decode(), flush=True)
    records = [load(folder/"samples"/(s["id"]+".json"))["record"] for s in samples]
    n = len(records); quiz = [r["quiz"] for r in records if "quiz" in r]
    hits = sum(r["mcq"]["score"]["source_key_match"] for r in records)
    scopes = {}
    for scope in sorted({r["test_scope"] for r in records}):
        rows = [r for r in records if r["test_scope"] == scope]
        scopes[scope] = {"n": len(rows), "mcq_matches": sum(r["mcq"]["score"]["source_key_match"] for r in rows),
                         "quiz_generated": sum("quiz" in r for r in rows), "quiz_proxy_pass": sum(r.get("quiz", {}).get("score", {}).get("usable_proxy", False) for r in rows)}
    summary = {"n_mcq": n, "mcq_matches": hits, "mcq_document_cluster_bootstrap95": cluster_interval(records),
        "n_source_documents":len({r['course'] for r in records}),
        "n_source_groups":len({r['split_group'] for r in records}),"n_target_families":len({r['target_fact_id'] for r in records}),
        "mcq_invalid": sum(not r["mcq"]["score"]["valid"] for r in records),
        "n_quiz": len(quiz), "quiz_json_valid": sum(q["score"]["json_valid"] for q in quiz),
        "quiz_structure_valid": sum(q["score"]["structural_valid"] for q in quiz), "quiz_reference_answer_preserved": sum(q["score"]["reference_answer_preserved"] for q in quiz),
        "quiz_usable_proxy": sum(q["score"]["usable_proxy"] for q in quiz), "quiz_length_stops": sum(q["length_stop"] for q in quiz),
        "by_test_scope": scopes, "oracle_source_context_provided": True, "retrieval_recall_measured": False,
        "expert_semantics_verified": False, "source_references_machine_verified_not_expert_gold": True}
    save(folder/"summary.json", summary)
    save(folder/"completed.json", {"identity_sha256": digest(identity), "files_sha256": {p.relative_to(folder).as_posix(): sha(p) for p in [folder/"identity.json", folder/"summary.json", *sorted((folder/"samples").glob('*.json'))]}})
    print(canonical(summary).decode(), flush=True)


def report(args, manifest, samples):
    variants = ("base", "sft_v2"); summaries = {}; identities = {}; results = {}
    for v in variants:
        folder = args.output/v; done = load(folder/"completed.json")
        for name, expected in done["files_sha256"].items():
            if sha(folder/name) != expected: raise ValueError("Evaluation output changed")
        identities[v] = load(folder/"identity.json")
        summaries[v] = load(folder/"summary.json")
        if digest(identities[v]) != done["identity_sha256"]: raise ValueError("Result identity mismatch")
        results[v] = {s["id"]: load(folder/"samples"/(s["id"]+".json"))["record"] for s in samples}
    for key in ('test_manifest_sha256', 'environment', 'batch_size', 'generation_limit', 'max_new_tokens'):
        if identities['base'][key] != identities['sft_v2'][key]: raise ValueError("Models used different test protocols")
    wins = sum(results['base'][s['id']]['mcq']['score']['source_key_match'] and not results['sft_v2'][s['id']]['mcq']['score']['source_key_match'] for s in samples)
    losses = sum(not results['base'][s['id']]['mcq']['score']['source_key_match'] and results['sft_v2'][s['id']]['mcq']['score']['source_key_match'] for s in samples)
    save(args.output/"comparison.json", {"summaries": summaries, "paired_mcq": {"base_only": wins, "sft_v2_only": losses},
         "scope": "source-group and2-document holdout from SFT-v2; all27PDFs seen by legacy CPT", "human_expert_gold": False})
    rng = random.Random(20261025); blind = []; key = []
    for s in samples:
        if 'quiz' not in results['base'][s['id']]: continue
        order = list(variants); rng.shuffle(order)
        blind.append({"id": s['id'], "evidence": s['evidence'], "reference": s['reference'],
            "answers": {chr(65+i): results[v][s['id']]['quiz']['text'] for i, v in enumerate(order)},
            "review": {"prompt_self_contained": None, "answer_correct": None, "distractors_unambiguous": None,
                       "explanation_supported": None, "notes": ""}})
        key.extend({"id": s['id'], "label": chr(65+i), "variant": v} for i, v in enumerate(order))
    save(args.output/"blind_review.json", blind); save(args.output/"blind_key.json", key)
    lines = ["# Base vs SFT-v2: separate100-reference holdout", "", "References are source-aligned machine drafts, not expert gold. Compact-output task uses controlled option terms.", "",
             "| Model | MCQ source-key agreement | Quiz structural | Quiz usable proxy |", "|---|---:|---:|---:|"]
    for v, s in summaries.items(): lines.append(f"| {v} | {s['mcq_matches']}/{s['n_mcq']} | {s['quiz_structure_valid']}/{s['n_quiz']} | {s['quiz_usable_proxy']}/{s['n_quiz']} |")
    lines += ["", "Oracle source cards are provided; this does not measure retrieval recall, expert correctness, or unrestricted scenario generation. Review blind outputs before selecting production behavior."]
    (args.output/"FINAL_TEST.md").write_text("\n".join(lines), encoding="utf-8")
    files = {p.relative_to(args.output).as_posix(): p for p in args.output.rglob('*') if p.is_file() and p.suffix in {'.json', '.md'}}
    make_zip(args.output/"sft_v2_final_test_results.zip", files)
    print("\n".join(lines), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True); p.add_argument('--output', type=Path)
    p.add_argument('--sft-run', type=Path); p.add_argument('--variant', choices=('base', 'sft_v2')); p.add_argument('--batch-size', type=int, choices=(1, 2, 4), default=2)
    p.add_argument('--generation-limit', type=int, choices=(20, 50, 100), default=100)
    p.add_argument('--mode', choices=('preflight', 'evaluate', 'report'), default='evaluate'); args = p.parse_args()
    if args.mode != 'preflight' and not args.output: p.error('--output required')
    if args.mode == 'evaluate' and not args.variant: p.error('--variant required')
    if args.mode == 'evaluate' and args.variant == 'sft_v2' and not args.sft_run: p.error('--sft-run required')
    main(args)
