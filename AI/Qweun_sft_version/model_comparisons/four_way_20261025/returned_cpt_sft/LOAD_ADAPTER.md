# Load the result

This adapter includes both the original CPT27 delta and the SFT update.
Load `Qwen/Qwen3-1.7B` at revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, then attach `adapter/` with PeftModel.from_pretrained.
Do not attach the old CPT adapter as well. Use the saved tokenizer and apply_chat_template(enable_thinking=False).
This is an adapter bundle, not standalone full weights or GGUF. Compare held-out quality before replacing a serving model.
Smoke output validates mechanics only and is not a final SFT model.
