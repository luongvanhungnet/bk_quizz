"""Identical pinned NF4 preparation for all evaluation and inference variants."""
import importlib.metadata
import time
from common import MODEL_ID, REVISION, native_bf16

PACKAGES = ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "huggingface-hub", "tokenizers", "safetensors", "lm-format-enforcer", "interegular", "pydantic")


def environment():
    import torch
    return {"packages": {n: importlib.metadata.version(n) for n in PACKAGES}, "gpu": torch.cuda.get_device_name(0),
            "dtype": "torch.bfloat16" if native_bf16(torch) else "torch.float16"}


def load_model(tokenizer_path, adapter=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed
    from peft import PeftModel, prepare_model_for_kbit_training
    if not torch.cuda.is_available(): raise RuntimeError("Select NVIDIA GPU; CPU inference disabled")
    set_seed(42)
    print('Loading pinned NF4 base; adapter:',str(adapter) if adapter else 'none',flush=True)
    dtype = torch.bfloat16 if native_bf16(torch) else torch.float16
    tok = AutoTokenizer.from_pretrained(str(tokenizer_path), local_files_only=True, trust_remote_code=False)
    tok.padding_side = "left"
    if tok.pad_token_id is None: tok.pad_token = tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=False,
        quantization_config=quant, torch_dtype=dtype, device_map={"": 0}, attn_implementation="sdpa", low_cpu_mem_usage=True)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    if adapter:
        model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False, autocast_adapter_dtype=True)
    model.eval(); model.config.use_cache = True
    print('Model ready:',torch.cuda.get_device_name(0),str(dtype),flush=True)
    return model, tok


class Generator:
    def __init__(self, model, tokenizer):
        from constrained import tokenizer_data
        print('Preparing reusable JSON grammar tokenizer index...',flush=True)
        self.model = model; self.tokenizer = tokenizer; self.data = tokenizer_data(tokenizer)
        print('JSON grammar tokenizer index ready.',flush=True)

    def batch(self, messages, schemas, cap=1536):
        import torch
        from transformers import GenerationConfig
        from constrained import batched_prefix
        tok = self.tokenizer
        prompts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True, enable_thinking=False) for m in messages]
        inputs = tok(prompts, return_tensors="pt", padding=True, truncation=False, add_special_tokens=False).to("cuda:0")
        width = inputs["input_ids"].shape[1]
        if width > 4096: raise ValueError("Overlength prompt, truncation disabled")
        config = GenerationConfig(do_sample=False, num_beams=1, max_new_tokens=cap, use_cache=True,
                                  eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id, repetition_penalty=1.0)
        prefix = batched_prefix(self.data, schemas) if schemas is not None else None
        torch.cuda.synchronize(); start = time.perf_counter()
        with torch.inference_mode():
            output = self.model.generate(**inputs, generation_config=config, prefix_allowed_tokens_fn=prefix)
        torch.cuda.synchronize(); elapsed = time.perf_counter()-start
        records = []
        for sequence in output:
            ids = sequence[width:].tolist()
            if tok.eos_token_id in ids: ids = ids[:ids.index(tok.eos_token_id)+1]
            records.append({"text": tok.decode(ids, skip_special_tokens=True), "raw_text": tok.decode(ids, skip_special_tokens=False),
                "token_ids": ids, "new_tokens": len(ids), "batch_seconds": elapsed, "batch_size": len(messages),
                "length_stop": len(ids) >= cap and ids[-1] != tok.eos_token_id})
        return records

    def one(self, messages, schema, cap=1536):
        return self.batch([messages], [schema] if schema is not None else None, cap)[0]
