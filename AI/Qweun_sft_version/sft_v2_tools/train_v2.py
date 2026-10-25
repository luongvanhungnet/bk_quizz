"""Fresh QLoRA on base, with validation generation selecting checkpoints."""
from __future__ import annotations
import argparse
import gc
import importlib.metadata
import math
from pathlib import Path
from common import MODEL_ID, REVISION, canonical, digest, load, make_zip, native_bf16, padded, read_rows, save, sha
from preflight import check
from quality import compact_schema, compact_score, selection_quality


def latest_checkpoint(out, fp16):
    required = {"adapter_model.safetensors", "adapter_config.json", "optimizer.pt", "scheduler.pt", "rng_state.pth", "trainer_state.json"}
    if fp16: required.add("scaler.pt")
    choices = [p for p in out.glob("checkpoint-*") if p.name[11:].isdigit() and all((p/n).is_file() for n in required)]
    if not choices: raise ValueError("No complete checkpoint; choose a new run name")
    return max(choices, key=lambda p: int(p.name[11:]))


def main(args):
    from transformers import AutoTokenizer
    root = args.root.resolve(); cfg = load(root/"runtime/train_config.json")
    if args.epochs is not None:cfg['epochs']=args.epochs
    verify = __import__("common").verify_files; verify(root)
    tok = AutoTokenizer.from_pretrained(str(root/"tokenizer"), local_files_only=True, trust_remote_code=False)
    report = check(root/"data", tok)
    if args.mode == "preflight": print(canonical(report).decode()); return
    import torch
    from packaging.version import Version
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, TrainerCallback, set_seed
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from engine import Generator, environment
    if not torch.cuda.is_available() or torch.cuda.get_device_properties(0).total_memory < 14*1024**3:
        raise RuntimeError("GPU with at least14GiB required")
    if Version(torch.__version__.split('+')[0]) < Version('2.6'): raise RuntimeError("torch>=2.6 required for checkpoint loading")
    if cfg["epochs"] not in (1, 2): raise ValueError("This pilot only checks1/2epochs")
    env = environment(); bf16 = native_bf16(torch); dtype = torch.bfloat16 if bf16 else torch.float16
    val = read_rows(root/"data/validation.samples.jsonl")
    val_ids = load(root/"validation_generation_ids.json")
    quality_rows = [next(s for s in val if s["id"] == i) for i in val_ids]
    if len(quality_rows) != 4: raise ValueError("Exactly4frozen validation generation cases required")
    identity = {"schema": "bkquiz-theory-sft-v2-run", "input_sha256": sha(root/"manifest.json"), "config": cfg,
        "environment": env, "base_model": MODEL_ID, "base_revision": REVISION, "cpt_weights_loaded": False,
        "initialization": "fresh_lora_zero_B", "validation_generation_ids": val_ids}
    out = args.output.resolve(); checkpoint = None
    if (out/"identity.json").exists():
        if load(out/"identity.json") != identity: raise ValueError("Resume identity changed; use a new RUN_NAME")
        if not (out/"completed.json").exists() and (out/"packaging.json").exists():
            pending = load(out/"packaging.json")
            for n, expected in pending["outputs_sha256"].items():
                if sha(out/n) != expected: raise ValueError("Pending trained output changed")
            make_zip(out/"sft_v2_adapter.zip", {n: out/n for n in pending["outputs_sha256"]} | {"completed.json": out/"packaging.json"})
            save(out/"completed.json", pending); print("PACKAGING_RECOVERED", out/"sft_v2_adapter.zip"); return
        if (out/"completed.json").exists():
            completed = load(out/"completed.json")
            for name, expected in completed["outputs_sha256"].items():
                if sha(out/name) != expected: raise ValueError("Completed output changed")
            if not (out/"sft_v2_adapter.zip").exists():
                make_zip(out/"sft_v2_adapter.zip", {n: out/n for n in completed["outputs_sha256"]} | {"completed.json": out/"completed.json"})
            print("ALREADY_COMPLETED", out/"sft_v2_adapter.zip"); return
        if not args.resume: raise ValueError("Use --resume for an existing run")
        checkpoint = latest_checkpoint(out, fp16=not bf16)
    elif out.exists() and any(out.iterdir()): raise ValueError("Output nonempty")
    out.mkdir(parents=True, exist_ok=True); save(out/"identity.json", identity); save(out/"preflight.json", report)
    set_seed(42)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False,
        quantization_config=quant, torch_dtype=dtype, device_map={"": 0}, attn_implementation="sdpa", low_cpu_mem_usage=True)
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False})
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=.05, bias="none", task_type="CAUSAL_LM",
                 target_modules=["down_proj", "gate_proj", "v_proj", "o_proj", "k_proj", "up_proj", "q_proj"], init_lora_weights=True))
    trainables = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
    if sum(p.numel() for _, p in trainables) != 8716288 or any('lora_' not in n for n, _ in trainables): raise ValueError("Wrong trainable set")
    if any(torch.count_nonzero(p).item() for n, p in trainables if 'lora_B' in n): raise ValueError("Fresh base LoRA must have zero B")
    initial = digest({n: __import__('hashlib').sha256(p.detach().float().cpu().numpy().tobytes()).hexdigest() for n, p in trainables})
    training = read_rows(root/"data/train.tokenized.jsonl"); validation = read_rows(root/"data/validation.tokenized.jsonl")
    class Data(torch.utils.data.Dataset):
        def __init__(self, rows): self.rows = rows
        def __len__(self): return len(self.rows)
        def __getitem__(self, i): return self.rows[i]
    def collate(rows): return {k: torch.tensor(v, dtype=torch.long) for k, v in padded(rows, tok.pad_token_id).items()}
    tok.padding_side = "right"
    generator = Generator(model, tok)
    validation_history = []
    class QualityTrainer(Trainer):
        def evaluate(self, eval_dataset=None, ignore_keys=None, metric_key_prefix="eval"):
            was_training=self.model.training
            metrics = super().evaluate(eval_dataset=eval_dataset, ignore_keys=ignore_keys, metric_key_prefix=metric_key_prefix)
            if metric_key_prefix != "eval": return metrics
            use_cache = self.model.config.use_cache
            self.model.eval(); self.model.config.use_cache = True; tok.padding_side = "left"
            results = []
            try:
                for i,sample in enumerate(quality_rows,1):
                    print(canonical({'event':'validation_generation','step':self.state.global_step,'case':i,'of':len(quality_rows)}).decode(),flush=True)
                    result = generator.one(sample["messages"][:-1], compact_schema([e["id"] for e in sample["evidence"]]), cfg["quality_max_new_tokens"])
                    result["score"] = compact_score(result["text"], sample)
                    results.append({"id": sample["id"], **result})
            finally:
                self.model.config.use_cache = use_cache; self.model.train(was_training); tok.padding_side = "right"
            metrics.update(selection_quality([r['score'] for r in results],metrics['eval_loss']))
            event = {"step": self.state.global_step, "metrics": metrics, "results": results, "human_semantics_verified": False}
            save(out/"validation_generation"/(str(self.state.global_step)+".json"), event)
            validation_history.append(event); self.log({k: v for k, v in metrics.items() if k.startswith("eval_generation")})
            return metrics
    steps = math.ceil(len(training)/cfg["gradient_accumulation_steps"])*cfg["epochs"]
    class FinalStep(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step == steps: control.should_evaluate = True; control.should_save = True
            return control
    settings = TrainingArguments(output_dir=str(out), per_device_train_batch_size=1, per_device_eval_batch_size=1,
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"], num_train_epochs=cfg["epochs"], learning_rate=cfg["learning_rate"],
        warmup_ratio=.03, weight_decay=.01, lr_scheduler_type="cosine", optim="adamw_torch", max_grad_norm=1.,
        bf16=bf16, fp16=not bf16, gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1, save_strategy="steps", eval_strategy="steps", save_steps=20, eval_steps=20, save_total_limit=2,
        save_safetensors=True, load_best_model_at_end=True, metric_for_best_model="eval_generation_quality", greater_is_better=True,
        seed=42, data_seed=42, report_to=[], dataloader_num_workers=0, label_names=["labels"], prediction_loss_only=True,
        remove_unused_columns=False, save_only_model=False)
    trainer = QualityTrainer(model=model, args=settings, train_dataset=Data(training), eval_dataset=Data(validation),
        data_collator=collate, processing_class=tok, callbacks=[FinalStep()])
    result = trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
    if not math.isfinite(result.training_loss): raise RuntimeError("Nonfinite training loss")
    if any(not torch.isfinite(p).all().item() for _,p in trainables):raise RuntimeError('Nonfinite LoRA weights; artifact export blocked')
    final = digest({n: __import__('hashlib').sha256(p.detach().float().cpu().numpy().tobytes()).hexdigest() for n, p in trainables})
    if final == initial: raise RuntimeError("No weight changed")
    model.save_pretrained(out/"adapter", safe_serialization=True)
    trainer.save_state(); save(out/"train_metrics.json", result.metrics)
    metrics = trainer.evaluate(metric_key_prefix="final_validation"); save(out/"validation_metrics.json", metrics)
    save(out/"MODEL_PROVENANCE.json", {"variant": "sft_v2", "base_model": MODEL_ID, "base_revision": REVISION,
         "cpt_weights_loaded": False, "dataset_manifest_sha256": sha(root/"data/manifest.json"),
         "initial_lora_digest": initial, "final_lora_digest": final, "test_used_for_training_or_selection": False,
         "checkpoint_selection": "fixed4validation_generation_proxy_then_NLL_tiebreak", "expert_semantics_verified": False})
    (out/"LOAD.md").write_text("Load adapter once on pinned Qwen3-1.7B base with the input bundle tokenizer, thinking disabled. No CPT adapter. This is an experimental pilot; generation proxy is not expert approval.\n", encoding="utf-8")
    kept = {p.relative_to(out).as_posix(): p for p in out.rglob('*') if p.is_file() and
            ('checkpoint-' not in str(p.relative_to(out)) and (p.suffix in {'.json', '.md', '.safetensors'}))
            and p.name not in {'completed.json', 'packaging.json'}}
    completed = {"status": "trained_pilot_not_production_approved", "steps": trainer.state.global_step,
        "best_model_checkpoint": trainer.state.best_model_checkpoint, "best_generation_proxy": trainer.state.best_metric,
        "test_used_for_selection": False, "outputs_sha256": {n: sha(p) for n, p in kept.items()}}
    # Completion marker is included in ZIP, but publish it on Drive only after successful packaging.
    save(out/"packaging.json", completed)
    make_zip(out/"sft_v2_adapter.zip", kept | {"completed.json": out/"packaging.json"})
    save(out/"completed.json", completed)
    print(canonical(completed).decode(), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--output", type=Path)
    p.add_argument("--mode", choices=("preflight", "train"), default="train"); p.add_argument("--resume", action="store_true")
    p.add_argument('--epochs',type=int,choices=(1,2))
    args = p.parse_args()
    if args.mode == "train" and args.output is None: p.error("--output required")
    main(args)
