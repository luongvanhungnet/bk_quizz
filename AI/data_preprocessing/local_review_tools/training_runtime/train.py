"""QLoRA causal language modeling on accepted course text, with resumable state."""
import argparse
import hashlib
import importlib.metadata
import math
import subprocess
from pathlib import Path
from data_utils import load, save, sha, read_jsonl, padded_batch, latest_checkpoint, complete_checkpoint


def main(args):
    import torch
    from packaging.version import Version
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments, set_seed
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    if not torch.cuda.is_available():
        raise RuntimeError('Select a Colab NVIDIA GPU runtime; CPU training is disabled here.')
    if Version(torch.__version__.split('+')[0]) < Version('2.6'):
        raise RuntimeError('torch >= 2.6 is required, including safe Trainer checkpoint loading.')
    root=Path(__file__).resolve().parent; cfg=load(root/'config.json'); data=load(args.prepared/'manifest.json')
    for key in ['model_id','revision','sequence_length']:
        if cfg[key]!=data[key]:raise ValueError('Re-run prepare.py after changing '+key)
    if sha(root/'data/manifest.json')!=data['dataset_manifest_sha256']:
        raise ValueError('Prepared data belongs to a different bundle')
    for name,digest in data['files_sha256'].items():
        if sha(args.prepared/name)!=digest:raise ValueError('Prepared data changed: '+name)
    rows=read_jsonl(args.prepared/'train.packed.jsonl')
    for r in rows:
        if r['labels']!=r['input_ids'] or r['attention_mask']!=[1]*len(r['input_ids']) or len(r['input_ids'])<2:
            raise ValueError('Invalid causal LM labels/mask or zero-target sequence')
    bf16=torch.cuda.is_bf16_supported(); dtype=torch.bfloat16 if bf16 else torch.float16
    fingerprint={'config':cfg, 'compute_dtype':str(dtype),'prepared_manifest_sha256':sha(args.prepared/'manifest.json'),
                 'mode':args.mode, 'training_code_sha256':sha(Path(__file__)),
                 'packages':{p:importlib.metadata.version(p) for p in ['torch','transformers','peft','accelerate','bitsandbytes']}}
    output=args.output; checkpoint=None
    if args.resume:
        if load(output/'run_identity.json')!=fingerprint:
            raise ValueError('Resume identity mismatch: keep model/data/config/code/library versions unchanged.')
        checkpoint=latest_checkpoint(output) if args.resume=='latest' else Path(args.resume).resolve()
        if checkpoint.parent.resolve()!=output.resolve() or not complete_checkpoint(checkpoint):
            raise ValueError('Resume requires a complete checkpoint from this output directory.')
    elif output.exists() and any(output.iterdir()):
        raise ValueError('Output is nonempty. Set --resume latest or choose a new run directory.')
    output.mkdir(parents=True,exist_ok=True);save(output/'run_identity.json',fingerprint)
    set_seed(cfg['seed'])
    tokenizer=AutoTokenizer.from_pretrained(args.prepared/'tokenizer',trust_remote_code=False)
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    tokenizer.padding_side='right'
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
                            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    model=AutoModelForCausalLM.from_pretrained(cfg['model_id'],revision=cfg['revision'],
        quantization_config=quant,torch_dtype=dtype,device_map={'':0},attn_implementation='sdpa',trust_remote_code=False)
    model.config.use_cache=False
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,
                                         gradient_checkpointing_kwargs={'use_reentrant':False})
    lora=LoraConfig(r=cfg['lora_r'],lora_alpha=cfg['lora_alpha'],lora_dropout=cfg['lora_dropout'],
                    target_modules=cfg['target_modules'],bias='none',task_type='CAUSAL_LM')
    model=get_peft_model(model,lora);model.print_trainable_parameters()
    if any(p.requires_grad and 'lora_' not in n for n,p in model.named_parameters()):
        raise ValueError('Unexpected trainable parameter outside LoRA')
    def adapter_digest():
        digest=hashlib.sha256()
        for name,param in model.named_parameters():
            if param.requires_grad:
                digest.update(name.encode());digest.update(param.detach().float().cpu().contiguous().numpy().tobytes())
        return digest.hexdigest()
    before_digest=adapter_digest() if checkpoint is None else None
    def collate(items):
        return {k:torch.tensor(v,dtype=torch.long) for k,v in padded_batch(items,tokenizer.pad_token_id).items()}
    class TextDataset(torch.utils.data.Dataset):
        def __len__(self):return len(rows)
        def __getitem__(self,index):return rows[index]
    dataset=TextDataset()
    settings=TrainingArguments(output_dir=str(output),per_device_train_batch_size=cfg['batch_size'],
        per_device_eval_batch_size=1,gradient_accumulation_steps=cfg['gradient_accumulation_steps'],
        num_train_epochs=cfg['epochs'],max_steps=cfg['smoke_steps'] if args.mode=='smoke' else -1,
        learning_rate=cfg['learning_rate'],weight_decay=0.01,warmup_ratio=cfg.get('warmup_ratio',0.03),
        lr_scheduler_type='cosine',optim='adamw_torch',max_grad_norm=1.0,
        bf16=bf16,fp16=not bf16,gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant':False},logging_steps=1,
        save_strategy='steps',save_steps=1 if args.mode=='smoke' else cfg['save_steps'],save_total_limit=cfg['save_total_limit'],
        save_safetensors=True,eval_strategy='no',report_to=[],seed=cfg['seed'],data_seed=cfg['seed'],
        dataloader_num_workers=0,dataloader_pin_memory=True,label_names=['labels'],prediction_loss_only=True)
    trainer=Trainer(model=model,args=settings,train_dataset=dataset,data_collator=collate,processing_class=tokenizer)
    diagnostic_set=torch.utils.data.Subset(dataset,list(range(min(len(rows),cfg.get('diagnostic_sequences',64)))))
    save(output/'environment.json',{'gpu':torch.cuda.get_device_name(0),'bf16':bf16,
        'vram_bytes':torch.cuda.get_device_properties(0).total_memory,
        'packages':fingerprint['packages'],'train_only':True,
        'approx_optimizer_steps_per_epoch':math.ceil(len(rows)/(cfg['batch_size']*cfg['gradient_accumulation_steps']))})
    (output/'pip-freeze.txt').write_text(subprocess.check_output(['python','-m','pip','freeze'],text=True),encoding='utf-8')
    initial_diagnostic=trainer.evaluate(eval_dataset=diagnostic_set,metric_key_prefix='initial_train_diagnostic') if checkpoint is None else None
    if initial_diagnostic:save(output/'initial_train_diagnostic.json',initial_diagnostic)
    result=trainer.train(resume_from_checkpoint=str(checkpoint) if checkpoint else None)
    if not math.isfinite(result.training_loss):raise RuntimeError('Nonfinite training loss: do not use this adapter.')
    changed=(adapter_digest()!=before_digest) if before_digest is not None else None
    if changed is False:raise RuntimeError('No LoRA weight changed; smoke/training did not produce an update.')
    adapter=output/'adapter';trainer.save_model(str(adapter));tokenizer.save_pretrained(adapter)
    trainer.save_state();trainer.save_metrics('train',result.metrics)
    # Same training corpus: this measures fitting only, not held-out generalization.
    diagnostic=trainer.evaluate(eval_dataset=diagnostic_set,metric_key_prefix='train_diagnostic')
    trainer.save_metrics('train_diagnostic',diagnostic)
    if not math.isfinite(diagnostic['train_diagnostic_loss']):raise RuntimeError('Nonfinite diagnostic loss')
    save(output/'completed.json',{'mode':args.mode,'global_step':trainer.state.global_step,
        'adapter':str(adapter),'metrics':result.metrics,'train_diagnostic':diagnostic,'initial_train_diagnostic':initial_diagnostic,
        'lora_changed_vs_initial':changed,'validation_or_test_metrics':None,
        'note':'Diagnostic uses the same fixed <=64 train sequences; not a held-out metric. Smoke adapter is not a final CPT result.'})
    print('Finished:',adapter)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['smoke','train'],required=True)
    p.add_argument('--resume',default=None,help='latest or a complete checkpoint directory')
    main(p.parse_args())
