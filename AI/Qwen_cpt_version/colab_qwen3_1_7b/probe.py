"""Matched HF NF4 baseline/adapter outputs. Export for review, not automatic grading."""
import argparse
import json
import time
from pathlib import Path
from data_utils import load, save, sha


def main(args):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer,BitsAndBytesConfig,set_seed
    from peft import PeftModel
    if not torch.cuda.is_available():raise RuntimeError('NVIDIA GPU required')
    root=Path(__file__).resolve().parent;cfg=load(root/'config.json')
    if args.out.exists():raise ValueError('Probe output already exists; choose a new filename to preserve the baseline.')
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    tokenizer=AutoTokenizer.from_pretrained(cfg['model_id'],revision=cfg['revision'],trust_remote_code=False)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    model=AutoModelForCausalLM.from_pretrained(cfg['model_id'],revision=cfg['revision'],
        quantization_config=quant,torch_dtype=dtype,device_map={'':0},attn_implementation='sdpa',trust_remote_code=False)
    if args.adapter:
        identity=load(args.adapter.parent/'run_identity.json')
        if identity['config']!=cfg:raise ValueError('Adapter/config mismatch')
        model=PeftModel.from_pretrained(model,str(args.adapter),is_trainable=False)
    model.eval();model.config.use_cache=True;results=[]
    cases=load(root/'probes/prompts.json')
    for case in cases:
        set_seed(cfg['seed'])
        prompt=tokenizer.apply_chat_template(case['messages'],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        batch=tokenizer(prompt,return_tensors='pt',add_special_tokens=False).to('cuda')
        start=time.perf_counter()
        with torch.inference_mode():
            output=model.generate(**batch,max_new_tokens=cfg['probe_max_new_tokens'],do_sample=False,
                                   pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
        text=tokenizer.decode(output[0,batch.input_ids.shape[1]:],skip_special_tokens=True)
        try:
            parsed=json.loads(text,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
            strict=isinstance(parsed,dict)
        except (ValueError,TypeError):strict=False
        results.append({'case_id':case['id'],'messages_sha256':case['messages_sha256'],
                        'content':text,'strict_json_object':strict,'seconds':time.perf_counter()-start})
        print(case['id'],'strict JSON:',strict,flush=True)
    save(args.out,{'model_id':cfg['model_id'],'revision':cfg['revision'],'quantization':'bnb NF4 double quant',
         'compute_dtype':str(dtype),'adapter':str(args.adapter) if args.adapter else None,
         'prompts_sha256':sha(root/'probes/prompts.json'),'config':cfg,'results':results,
         'scope':'Task regression probes, not independent held-out evaluation; review content with gold/rubric.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--adapter',type=Path);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
