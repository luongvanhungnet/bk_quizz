"""One isolated GPU process per variant; immutable prompts, no answer repair/judge."""
from __future__ import annotations
import argparse
import gc
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
import time

from sft_contract import MODEL_ID, MODEL_REVISION, digest, load, save, sha, verify_dataset, native_bf16
from scoring import score_mcq, score_quiz, wilson

VARIANTS = ("base", "cpt", "sft", "cpt_sft")
PACKAGES = ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "huggingface-hub", "tokenizers", "safetensors")


def preflight(root):
    root = Path(root)
    manifest = load(root / "comparison_manifest.json")
    for name, wanted in manifest["files_sha256"].items():
        target = (root / name).resolve()
        if not target.is_relative_to(root.resolve()) or sha(target) != wanted:
            raise ValueError("Comparison input changed: " + name)
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(root / "data/tokenizer"), local_files_only=True, trust_remote_code=False)
    _, _, datasets, report = verify_dataset(root / "data", tokenizer=tok)
    tasks = load(root / "tasks.json")
    if [t["id"] for t in tasks] != [r["id"] for r in datasets["test"]]:
        raise ValueError("Evaluation must use the frozen test split in order")
    print(json.dumps({"event": "preflight", "test": len(tasks), "report": report}), flush=True)
    return manifest, tok, datasets, tasks


def adapter_for(root, variant, sft_run):
    if variant == "base":
        return None
    if variant == "cpt":
        return root / "data/assets/cpt_adapter"
    if variant == "cpt_sft":
        return root / "models/cpt_sft"
    if sft_run is None:
        raise ValueError("The SFT-only checkpoint is required")
    done = load(sft_run / "completed.json")
    prov = load(sft_run / "MODEL_PROVENANCE.json")
    if (done.get("status") != "completed" or done.get("mode") != "train"
            or prov.get("variant") != "sft" or prov.get("cpt_weights_loaded") is not False
            or prov.get("dataset_manifest_sha256") != sha(root / "data/manifest.json")
            or prov.get("base_revision") != MODEL_REVISION):
        raise ValueError("Not a completed standalone SFT-only run")
    for name, wanted in done["outputs_sha256"].items():
        if sha(sft_run / name) != wanted:
            raise ValueError("SFT-only output changed: " + name)
    cfg = load(sft_run / "run_identity.json")
    if cfg["config"] != load(root / "runtime/config.json") or cfg["cpt_weights_loaded"] is not False:
        raise ValueError("SFT-only training protocol differs")
    return sft_run / "adapter"


def evaluate(args):
    root = args.root.resolve()
    manifest, tok, datasets, tasks = preflight(root)
    if args.mode == "preflight":
        return
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, GenerationConfig, set_seed
    from peft import PeftModel, prepare_model_for_kbit_training
    if not torch.cuda.is_available():
        raise RuntimeError("Select a CUDA GPU")
    dtype = torch.bfloat16 if native_bf16(torch) else torch.float16
    adapter = adapter_for(root, args.variant, args.sft_run)
    adapter_hashes = {n: sha(adapter/n) for n in ("adapter_config.json", "adapter_model.safetensors")} if adapter else {}
    packages = {n: importlib.metadata.version(n) for n in PACKAGES}
    identity = {"schema": "bkquiz-four-way-eval-v1", "variant": args.variant,
                "input_manifest_sha256": sha(root/"comparison_manifest.json"), "model": MODEL_ID,
                "revision": MODEL_REVISION, "adapter_sha256": adapter_hashes, "packages": packages,
                "dtype": str(dtype), "gpu": torch.cuda.get_device_name(0), "protocol": manifest["protocol"],
                "generation_count": args.generation_count}
    out = args.output / args.variant
    out.mkdir(parents=True, exist_ok=True)
    if (out/"identity.json").is_file() and load(out/"identity.json") != identity:
        raise ValueError("Cached evaluation has another identity; use a new RUN_NAME")
    save(out/"identity.json", identity)
    set_seed(42)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                              bnb_4bit_compute_dtype=dtype)
    start = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
        quantization_config=quant, torch_dtype=dtype, device_map={"": 0}, attn_implementation="sdpa", low_cpu_mem_usage=True)
    # Same non-quantized dtype preparation on all four, matching the training model.
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    if adapter:
        model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False, autocast_adapter_dtype=True)
    model.eval()
    model.config.use_cache = True
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - start

    def generate(messages, cap):
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = tok(prompt, return_tensors="pt", add_special_tokens=False).to("cuda:0")
        prompt_count = inputs["input_ids"].shape[1]
        if prompt_count > 4096:
            raise ValueError("Prompt exceeds frozen context budget")
        config = GenerationConfig(do_sample=False, num_beams=1, max_new_tokens=cap,
            eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id or tok.eos_token_id, use_cache=True,
            repetition_penalty=1.0, renormalize_logits=False)
        torch.cuda.synchronize()
        begin = time.perf_counter()
        with torch.inference_mode():
            result = model.generate(**inputs, generation_config=config)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - begin
        ids = result[0, prompt_count:].tolist()
        return {"text": tok.decode(ids, skip_special_tokens=True),
                "raw_text_with_special_tokens": tok.decode(ids, skip_special_tokens=False), "generated_token_ids": ids,
                "new_tokens": len(ids),
                "prompt_tokens": prompt_count, "seconds": seconds,
                "length_stop": len(ids) == cap and ids[-1] != tok.eos_token_id}

    # Identical non-test warmup; excluded from throughput metrics.
    generate([{"role": "user", "content": "Trả lời ngắn: 1 + 1 bằng bao nhiêu?"}], 8)
    torch.cuda.reset_peak_memory_stats()
    records = []
    generation_ids = manifest["generation_order"][:args.generation_count]
    for index, (task, encoded) in enumerate(zip(tasks, datasets["test"]), 1):
        path = out / "samples" / (task["id"] + ".json")
        if path.is_file():
            envelope = load(path)
            row = envelope["record"]
            if envelope["identity_sha256"] != digest(identity) or digest(row) != envelope["record_sha256"]:
                raise ValueError("Invalid result cache")
            records.append(row)
            print(json.dumps({"variant": args.variant, "sample": index, "cached": True}), flush=True)
            continue
        inputs = {k: torch.tensor([encoded[k]], dtype=torch.long, device="cuda:0")
                  for k in ("input_ids", "attention_mask", "labels")}
        with torch.inference_mode():
            result = model(**inputs, use_cache=False)
        nll = result.loss.float().item()
        if not math.isfinite(nll):
            raise RuntimeError("Nonfinite test loss")
        count = sum(x != -100 for x in encoded["labels"][1:])
        del inputs, result
        mcq = generate(task["closed_book_messages"], manifest["protocol"]["mcq_max_new_tokens"])
        mcq["score"] = score_mcq(mcq["text"], task["gold_labels"], task["valid_labels"])
        row = {"id": task["id"], "course": task["course"], "assistant_nll": nll,
               "supervised_tokens": count, "closed_book": mcq}
        if task["id"] in generation_ids:
            quiz = generate(task["grounded_messages"], manifest["protocol"]["quiz_max_new_tokens"])
            quiz["score"] = score_quiz(quiz["text"], task["reference_question"], task["grounded_messages"][-1]["content"])
            row["grounded_quiz"] = quiz
        save(path, {"identity_sha256": digest(identity), "record_sha256": digest(row), "record": row})
        records.append(row)
        print(json.dumps({"variant": args.variant, "sample": index, "of": len(tasks),
                          "mcq_match": mcq["score"]["source_key_exact_match"],
                          "quiz_valid": row.get("grounded_quiz", {}).get("score", {}).get("schema_and_citations_valid")}), flush=True)
    n = len(records)
    hits = sum(r["closed_book"]["score"]["source_key_exact_match"] for r in records)
    generated = [r["grounded_quiz"] for r in records if "grounded_quiz" in r]
    all_gen = [r["closed_book"] for r in records] + generated
    mean_nll = statistics.mean(r["assistant_nll"] for r in records)
    token_nll = sum(r["assistant_nll"]*r["supervised_tokens"] for r in records)/sum(r["supervised_tokens"] for r in records)
    summary = {"variant": args.variant, "n_test": n, "assistant_mean_example_nll": mean_nll,
               "assistant_mean_example_ppl": math.exp(mean_nll), "assistant_token_weighted_nll": token_nll,
               "assistant_token_weighted_ppl": math.exp(token_nll), "source_key_matches": hits,
               "source_key_agreement": hits/n, "source_key_agreement_wilson95": wilson(hits, n),
               "mcq_invalid": sum(not r["closed_book"]["score"]["valid_json_answer"] for r in records),
               "n_grounded": len(generated), "grounded_valid": sum(g["score"]["schema_and_citations_valid"] for g in generated),
               "grounded_json_valid": sum(g["score"]["json_valid"] for g in generated),
               "grounded_length_stops": sum(g["length_stop"] for g in generated),
               "grounded_reference_assessable": sum(g["score"]["reference_alignment_assessable"] for g in generated),
               "grounded_reference_matches": sum(g["score"]["source_answer_exact_match"] is True for g in generated),
               "generation_tokens_per_second": sum(g["new_tokens"] for g in all_gen)/sum(g["seconds"] for g in all_gen),
               "generation_seconds": sum(g["seconds"] for g in all_gen), "model_load_seconds": load_seconds,
               "peak_allocated_gib_this_process": torch.cuda.max_memory_allocated()/1024**3,
               "performance_note": "Cached samples retain earlier timings; VRAM is this process only. Model load excluded.",
               "semantic_explanation_quality_measured": False}
    save(out/"summary.json", summary)
    save(out/"completed.json", {"identity_sha256": digest(identity), "n": n,
        "outputs_sha256": {p.relative_to(out).as_posix(): sha(p) for p in [out/"identity.json", out/"summary.json", *sorted((out/"samples").glob("*.json"))]}})
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    del model
    gc.collect()
    torch.cuda.empty_cache()


def report(args):
    import random
    import zipfile
    from itertools import combinations
    root, out = args.root, args.output
    tasks = {t["id"]: t for t in load(root/"tasks.json")}
    summaries, rows, identities = {}, {}, {}
    for variant in VARIANTS:
        folder = out/variant
        done = load(folder/"completed.json")
        for name, wanted in done["outputs_sha256"].items():
            if sha(folder/name) != wanted:
                raise ValueError("Evaluation output changed: " + variant + "/" + name)
        identities[variant] = load(folder/"identity.json")
        if done["identity_sha256"] != digest(identities[variant]):
            raise ValueError("Result identity changed")
        summaries[variant] = load(folder/"summary.json")
        rows[variant] = {p.stem: load(p)["record"] for p in (folder/"samples").glob("*.json")}
        if set(rows[variant]) != set(tasks):
            raise ValueError("Incomplete test comparison")
    common_fields = ("input_manifest_sha256", "model", "revision", "packages", "dtype", "gpu", "protocol", "generation_count")
    if any(any(identities[v][k] != identities["base"][k] for k in common_fields) for v in VARIANTS):
        raise ValueError("Four variants were not evaluated under the same protocol/environment")
    pairs = []
    for a, b in combinations(VARIANTS, 2):
        wins = sum(rows[a][i]["closed_book"]["score"]["source_key_exact_match"] and not rows[b][i]["closed_book"]["score"]["source_key_exact_match"] for i in tasks)
        losses = sum(not rows[a][i]["closed_book"]["score"]["source_key_exact_match"] and rows[b][i]["closed_book"]["score"]["source_key_exact_match"] for i in tasks)
        pairs.append({"a": a, "b": b, "a_only_correct": wins, "b_only_correct": losses,
                      "both_same_outcome": len(tasks)-wins-losses})
    save(out/"comparison.json", {"summaries": summaries, "paired_source_key_outcomes": pairs,
                                 "semantic_explanation_quality_measured": False})
    rng = random.Random(20261025)
    blind, key = [], []
    for identity, task in tasks.items():
        if "grounded_quiz" not in rows["base"][identity]:
            continue
        order = list(VARIANTS)
        rng.shuffle(order)
        answers = {}
        for idx, variant in enumerate(order):
            label = chr(65+idx)
            answers[label] = rows[variant][identity]["grounded_quiz"]["text"]
            key.append({"id": identity, "label": label, "variant": variant})
        blind.append({"id": identity, "course": task["course"], "context": task["grounded_messages"],
                      "reference_question": task["reference_question"], "answers": answers,
                      "review": {"answer_correctness": None, "distractor_quality": None,
                                 "explanation_support": None, "hallucination": None, "notes": ""}})
    save(out/"blind_review.json", blind)
    save(out/"blind_review_key.json", key)
    text = ["# So sánh bốn phiên bản\n", "Cùng test40; source-key agreement không phải expert accuracy. Không dùng test để chọn checkpoint.\n",
            "| Phiên bản | Test NLL ↓ | PPL ↓ | Khớp đáp án nguồn | JSON + citations hợp lệ | tokens/s |",
            "|---|---:|---:|---:|---:|---:|"]
    for variant in VARIANTS:
        s = summaries[variant]
        text.append(f"| {variant} | {s['assistant_mean_example_nll']:.4f} | {s['assistant_mean_example_ppl']:.3f} | {s['source_key_matches']}/{s['n_test']} | {s['grounded_valid']}/{s['n_grounded']} | {s['generation_tokens_per_second']:.1f} |")
    text += ["", "NLL đo assistant theo ngữ cảnh có đáp án nguồn. MCQ đo đóng sách, giữ thứ tự phương án nguồn; có thể chịu thiên lệch vị trí.",
             "JSON/citations chỉ là kiểm tra cấu trúc và trích dẫn nguyên văn; chưa đánh giá lời giải sâu/độ đúng học thuật. Duyệt blind_review.json trước khi mở key.",
             "Test chỉ40 câu và có PDF cùng nguồn với train; một seed; chưa chứng minh khái quát sang giáo trình/tài liệu mới.",
             "Các đáp án nguồn chưa được chuyên gia xác nhận. Các bản đều nạp NF4 chung; benchmark này đo adapter, không đo bản GGUF triển khai."]
    (out/"COMPARISON.md").write_text("\n".join(text)+"\n", encoding="utf-8")
    files = [p for p in out.rglob("*") if p.is_file() and p.suffix in {".json", ".md"} and "sft_only_training" not in p.parts]
    # Include the new checkpoint safely, excluding optimizer pickle files.
    if args.sft_run:
        files.extend(p for p in args.sft_run.rglob("*") if p.is_file() and
                     (p.parent.name == "adapter" and p.name in {"adapter_config.json", "adapter_model.safetensors"}
                      or p.parent == args.sft_run and p.suffix == ".json"))
    archive = out/"four_way_results.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)):
            name = p.relative_to(out).as_posix() if p.is_relative_to(out) else "sft_only_training/" + p.relative_to(args.sft_run).as_posix()
            z.write(p, name)
    print("RESULT:", archive, "SHA256:", sha(archive), flush=True)
    print((out/"COMPARISON.md").read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--sft-run", type=Path)
    p.add_argument("--mode", choices=("preflight", "evaluate", "report"), default="evaluate")
    p.add_argument("--variant", choices=VARIANTS)
    p.add_argument("--generation-count", type=int, choices=(12, 40), default=12)
    args = p.parse_args()
    if args.mode != "preflight" and args.output is None:
        p.error("--output required")
    if args.mode == "evaluate" and args.variant is None:
        p.error("--variant required")
    report(args) if args.mode == "report" else evaluate(args)
