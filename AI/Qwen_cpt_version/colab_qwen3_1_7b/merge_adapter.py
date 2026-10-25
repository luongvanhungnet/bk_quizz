"""Optional: export a standalone HF model in FP16, without quantized-weight merge."""
import argparse
from pathlib import Path
from data_utils import load,save


def main(a):
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    from peft import PeftModel
    cfg=load(Path(__file__).resolve().parent/'config.json')
    if load(a.adapter.parent/'run_identity.json')['config']!=cfg:raise ValueError('Adapter/config mismatch')
    if a.out.exists() and any(a.out.iterdir()):raise ValueError('Export directory must be empty')
    model=AutoModelForCausalLM.from_pretrained(cfg['model_id'],revision=cfg['revision'],
          torch_dtype=torch.float16,device_map='cpu',low_cpu_mem_usage=True,trust_remote_code=False)
    model=PeftModel.from_pretrained(model,str(a.adapter)).merge_and_unload(safe_merge=True)
    model.save_pretrained(a.out,safe_serialization=True,max_shard_size='2GB')
    AutoTokenizer.from_pretrained(cfg['model_id'],revision=cfg['revision'],trust_remote_code=False).save_pretrained(a.out)
    save(a.out/'cpt_provenance.json',{'base_model':cfg['model_id'],'revision':cfg['revision'],
         'adapter':str(a.adapter),'export':'merged FP16 HF; not GGUF; requires post-export evaluation'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--adapter',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    main(p.parse_args())
