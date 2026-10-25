"""SFT only: continue the verified CPT27 LoRA with assistant-only chat loss.

The exported adapter contains both CPT and SFT updates. Load it once onto the
pinned base; never stack the original CPT adapter a second time.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import gc
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
import sys

from sft_contract import (MODEL_ID,MODEL_REVISION,CPT_HASHES,EOS_ID,canonical,digest,sha,load,save,
                          verify_dataset,verify_adapter,padded_batch,native_bf16,
                          complete_checkpoint,latest_checkpoint,export_zip)

PACKAGES=("torch","transformers","peft","accelerate","bitsandbytes","huggingface-hub","tokenizers","safetensors")


def check_config(cfg):
    if cfg.get("model_id")!=MODEL_ID or cfg.get("revision")!=MODEL_REVISION or cfg.get("max_length")!=4096:raise ValueError("Wrong model revision or sequence contract")
    if not 0<cfg.get("learning_rate",0)<=.001 or not 0<cfg.get("epochs",0)<=10:raise ValueError("Invalid training schedule")
    for key in ("batch_size","gradient_accumulation_steps","save_steps","save_total_limit","smoke_steps"):
        if type(cfg.get(key))is not int or cfg[key]<1:raise ValueError("Positive integer required: "+key)


def print_json(event,**data):print(json.dumps({"event":event,**data},ensure_ascii=False),flush=True)


def finalize_artifact(output,completed):
    """Publish completion last, and permit repackaging after a Drive interruption."""
    output=Path(output)
    for name,wanted in completed["outputs_sha256"].items():
        if sha(output/name)!=wanted:raise ValueError("Trained output changed before packaging: "+name)
    pending=output/"packaging_report.json";save(pending,completed)
    export_zip(output/completed["bundle_name"],{**{name:output/name for name in completed["outputs_sha256"]},"completed.json":pending})
    bundle=output/completed["bundle_name"]
    save(output/"RESULT_BUNDLE.json",{"path":completed["bundle_name"],"sha256":sha(bundle),"size_bytes":bundle.stat().st_size})
    save(output/"completed.json",completed)
    return bundle


def main(args):
    from transformers import AutoTokenizer
    root=Path(__file__).resolve().parent;cfg=load(root/"config.json");check_config(cfg)
    # Verify declared bytes before reading the tokenizer or any model artifact.
    manifest,provenance,datasets,report=verify_dataset(args.data)
    tokenizer=AutoTokenizer.from_pretrained(str(args.data/"tokenizer"),trust_remote_code=False,local_files_only=True)
    manifest,provenance,datasets,report=verify_dataset(args.data,tokenizer=tokenizer)
    print_json("preflight",**report)
    if args.mode=="preflight":return report
    if args.output is None:raise ValueError("--output is required for smoke/train")
    if args.mode=="smoke" and args.evaluate_test:raise ValueError("Smoke never evaluates final test")

    import torch
    from packaging.version import Version
    from transformers import AutoModelForCausalLM,BitsAndBytesConfig,Trainer,TrainingArguments,set_seed
    from peft import PeftModel,prepare_model_for_kbit_training,get_peft_model_state_dict
    from safetensors.torch import load_file
    if not torch.cuda.is_available():raise RuntimeError("Select an NVIDIA CUDA GPU runtime. CPU training is disabled.")
    if Version(torch.__version__.split("+")[0])<Version("2.6"):raise RuntimeError("torch>=2.6 required for safe Trainer checkpoint loading")
    gpu=torch.cuda.get_device_properties(0)
    if gpu.total_memory<14*1024**3:raise RuntimeError("GPU with at least14GiB VRAM required for this checked configuration")
    bf16=native_bf16(torch);dtype=torch.bfloat16 if bf16 else torch.float16
    packages={name:importlib.metadata.version(name) for name in PACKAGES}
    identity={"schema":"bkquiz-completed-sft-run-v1","config":cfg,"mode":args.mode,"compute_dtype":str(dtype),
              "dataset_manifest_sha256":report["dataset_manifest_sha256"],"base_model":MODEL_ID,"base_revision":MODEL_REVISION,
              "cpt_adapter_sha256":CPT_HASHES,"continuation":"continue_same_cpt27_adapter_trainable",
              "packages":packages,"runtime_sha256":{n:sha(root/n) for n in ("train_sft.py","sft_contract.py","config.json","requirements.txt")}}
    output=args.output.resolve();checkpoint=None
    if args.resume:
        if not (output/"run_identity.json").is_file() or load(output/"run_identity.json")!=identity:
            raise ValueError("Resume identity mismatch: keep data/config/model/runtime/packages unchanged")
        if not (output/"completed.json").is_file() and (output/"packaging_report.json").is_file():
            pending=load(output/"packaging_report.json")
            bundle=finalize_artifact(output,pending)
            print_json("packaging_recovered",bundle=str(bundle))
            return pending
        if (output/"completed.json").is_file():
            old=load(output/"completed.json")
            if old.get("status")in {"completed","smoke_only_not_final"}:
                for name,wanted in old["outputs_sha256"].items():
                    if sha(output/name)!=wanted:raise ValueError("Completed output changed: "+name)
                bundle_info=load(output/"RESULT_BUNDLE.json")
                if bundle_info.get("path")!=old["bundle_name"] or sha(output/old["bundle_name"])!=bundle_info.get("sha256"):raise ValueError("Completed result ZIP changed or missing")
                if args.evaluate_test and old.get("test")is None:
                    raise ValueError("This completed run did not evaluate test. Preserve the trained model; use a separate explicit test-only evaluation rather than repeating SFT.")
                print_json("already_completed",report=str(output/"completed.json"),bundle=str(output/old["bundle_name"]))
                return old
        checkpoint=latest_checkpoint(output,require_scaler=not bf16) if args.resume=="latest" else Path(args.resume).resolve()
        if checkpoint.resolve().parent!=output or not complete_checkpoint(checkpoint,require_scaler=not bf16):raise ValueError("Resume needs a complete direct-child checkpoint from this run")
    elif output.exists() and any(output.iterdir()):raise ValueError("Output is nonempty. Use --resume latest or a new output directory.")
    output.mkdir(parents=True,exist_ok=True);save(output/"run_identity.json",identity);save(output/"preflight_report.json",report)
    save(output/"environment.json",{"gpu":gpu.name,"vram_bytes":gpu.total_memory,"compute_dtype":str(dtype),"native_bf16":bf16,
                                 "packages":packages,"started_utc":datetime.now(timezone.utc).isoformat()})
    (output/"pip-freeze.txt").write_text(subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True),encoding="utf-8")
    set_seed(cfg["seed"]);tokenizer.padding_side="right"
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    print_json("loading_student",model=MODEL_ID,revision=MODEL_REVISION,dtype=str(dtype),cpt_adapter="verified bundled CPT27")
    model=AutoModelForCausalLM.from_pretrained(MODEL_ID,revision=MODEL_REVISION,trust_remote_code=False,
                    quantization_config=quant,torch_dtype=dtype,device_map={"":0},attn_implementation="sdpa",low_cpu_mem_usage=True)
    model.config.use_cache=False
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={"use_reentrant":False})
    adapter=verify_adapter(args.data)
    model=PeftModel.from_pretrained(model,str(adapter),is_trainable=True,autocast_adapter_dtype=True)
    model.set_adapter("default");model.print_trainable_parameters()
    trainables=[(name,p) for name,p in model.named_parameters() if p.requires_grad]
    if not trainables or any("lora_"not in name for name,p in trainables):raise ValueError("Only the existing CPT LoRA parameters may be trainable")
    original=load_file(str(adapter/"adapter_model.safetensors"),device="cpu");loaded=get_peft_model_state_dict(model)
    if set(original)!=set(loaded) or any(not torch.equal(original[name].float(),loaded[name].detach().cpu().float()) for name in original):
        raise ValueError("Loaded starting LoRA does not equal the verified CPT27 adapter")
    del original,loaded;gc.collect()
    def adapter_digest():
        import hashlib
        value=hashlib.sha256()
        for name,p in trainables:
            value.update(name.encode());value.update(p.detach().float().cpu().contiguous().numpy().tobytes())
        return value.hexdigest()
    initial_digest=adapter_digest()
    print_json("verified_cpt_start",trainable_parameters=sum(p.numel() for _,p in trainables),adapter_tensor_sha256=initial_digest)

    class ChatDataset(torch.utils.data.Dataset):
        def __init__(self,rows):self.rows=rows
        def __len__(self):return len(self.rows)
        def __getitem__(self,index):return self.rows[index]
    def collate(rows):return {key:torch.tensor(value,dtype=torch.long) for key,value in padded_batch(rows,tokenizer.pad_token_id).items()}
    train=ChatDataset(datasets["train"]);validation=ChatDataset(datasets["validation"]) if datasets["validation"]else None
    interval=min(cfg["save_steps"],max(1,math.ceil(len(train)/(cfg["batch_size"]*cfg["gradient_accumulation_steps"]))))
    use_validation=validation is not None and args.mode=="train"
    settings=TrainingArguments(output_dir=str(output),per_device_train_batch_size=cfg["batch_size"],per_device_eval_batch_size=1,
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],num_train_epochs=cfg["epochs"],
        max_steps=cfg["smoke_steps"]if args.mode=="smoke"else -1,learning_rate=cfg["learning_rate"],weight_decay=cfg["weight_decay"],
        warmup_ratio=cfg["warmup_ratio"],lr_scheduler_type="cosine",optim="adamw_torch",max_grad_norm=1.,
        bf16=bf16,fp16=not bf16,gradient_checkpointing=True,gradient_checkpointing_kwargs={"use_reentrant":False},
        logging_steps=1,save_strategy="steps",save_steps=1 if args.mode=="smoke"else interval,save_total_limit=cfg["save_total_limit"],
        save_safetensors=True,eval_strategy="steps"if use_validation else "no",eval_steps=interval,
        load_best_model_at_end=use_validation,metric_for_best_model="eval_loss"if use_validation else None,greater_is_better=False,
        report_to=[],seed=cfg["seed"],data_seed=cfg["seed"],dataloader_num_workers=0,dataloader_pin_memory=True,
        label_names=["labels"],prediction_loss_only=True,remove_unused_columns=False,save_only_model=False)
    trainer=Trainer(model=model,args=settings,train_dataset=train,eval_dataset=validation if use_validation else None,
                    data_collator=collate,processing_class=tokenizer)
    initial_validation=None
    if use_validation and checkpoint is None:
        initial_validation=trainer.evaluate(metric_key_prefix="initial_validation")
        if not math.isfinite(initial_validation["initial_validation_loss"]):raise RuntimeError("Initial validation loss is nonfinite")
        save(output/"initial_validation.json",initial_validation)
    elif (output/"initial_validation.json").is_file():initial_validation=load(output/"initial_validation.json")
    result=trainer.train(resume_from_checkpoint=str(checkpoint)if checkpoint else None)
    if not math.isfinite(result.training_loss):raise RuntimeError("Nonfinite training loss; do not use this adapter")
    final_digest=adapter_digest()
    if final_digest==initial_digest:raise RuntimeError("No CPT adapter weight changed during SFT")
    destination=output/"adapter";trainer.save_model(str(destination));tokenizer.save_pretrained(destination);trainer.save_state();trainer.save_metrics("train",result.metrics)
    final_validation=trainer.evaluate(metric_key_prefix="validation")if use_validation else None
    if final_validation:
        if not math.isfinite(final_validation["validation_loss"]):raise RuntimeError("Final validation loss is nonfinite")
        trainer.save_metrics("validation",final_validation)
    final_test=None
    if args.evaluate_test:
        if not datasets["test"]:raise ValueError("Explicit test evaluation requested but test split is empty")
        final_test=trainer.evaluate(eval_dataset=ChatDataset(datasets["test"]),metric_key_prefix="test")
        if not math.isfinite(final_test["test_loss"]):raise RuntimeError("Test loss is nonfinite")
        trainer.save_metrics("test",final_test)
    save(output/"MODEL_PROVENANCE.json",{**provenance,"continuation_method":"continued_same_cpt27_adapter_trainable",
         "output_adapter_contains":"complete CPT27 plus SFT update; load once on pinned base, do not stack old CPT adapter",
         "initial_cpt_tensor_sha256":initial_digest,"final_adapter_tensor_sha256":final_digest,
         "dataset_manifest_sha256":report["dataset_manifest_sha256"],"test_used_for_training_or_selection":False})
    (output/"LOAD_ADAPTER.md").write_text("""# Load the result

This adapter includes both the original CPT27 delta and the SFT update.
Load `Qwen/Qwen3-1.7B` at revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, then attach `adapter/` with PeftModel.from_pretrained.
Do not attach the old CPT adapter as well. Use the saved tokenizer and apply_chat_template(enable_thinking=False).
This is an adapter bundle, not standalone full weights or GGUF. Compare held-out quality before replacing a serving model.
Smoke output validates mechanics only and is not a final SFT model.
""",encoding="utf-8")
    bundle_name="smoke_adapter.zip"if args.mode=="smoke"else"sft_completed_adapter.zip"
    keep=[p for p in destination.rglob("*")if p.is_file()]
    keep +=[output/name for name in ("MODEL_PROVENANCE.json","run_identity.json","environment.json","preflight_report.json","pip-freeze.txt","LOAD_ADAPTER.md","train_results.json","trainer_state.json")if(output/name).is_file()]
    keep +=[output/name for name in ("validation_results.json","test_results.json","initial_validation.json")if(output/name).is_file()]
    artifact_hashes={p.relative_to(output).as_posix():sha(p)for p in keep}
    completed={"status":"smoke_only_not_final"if args.mode=="smoke"else"completed","mode":args.mode,"global_step":trainer.state.global_step,
        "epochs_requested":cfg["epochs"],"train_metrics":result.metrics,"initial_validation":initial_validation,"validation":final_validation,
        "test":final_test,"test_evaluation_explicitly_requested":args.evaluate_test,"best_model_checkpoint":trainer.state.best_model_checkpoint,
        "adapter_weights_changed":True,"dataset_manifest_sha256":report["dataset_manifest_sha256"],"bundle_name":bundle_name,
        "outputs_sha256":artifact_hashes,"semantic_improvement_measured":False}
    finalize_artifact(output,completed)
    print_json("finished",report=str(output/"completed.json"),bundle=str(output/bundle_name),mode=args.mode)
    return completed


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--data",type=Path,required=True);p.add_argument("--output",type=Path)
    p.add_argument("--mode",choices=("preflight","smoke","train"),default="train");p.add_argument("--resume")
    p.add_argument("--evaluate-test",action="store_true")
    main(p.parse_args())
