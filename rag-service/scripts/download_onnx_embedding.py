from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the int8 ONNX embedding model without PyTorch.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output).resolve()
    snapshot_download(
        repo_id=args.model,
        local_dir=output,
        allow_patterns=[
            "config.json",
            "config_sentence_transformers.json",
            "modules.json",
            "sentence_bert_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "1_Pooling/*",
            "onnx/model_quint8_avx2.onnx",
        ],
    )
    downloaded = output / "onnx" / "model_quint8_avx2.onnx"
    target = output / "onnx" / "model_qint8_avx2.onnx"
    if not downloaded.exists():
        raise FileNotFoundError("The model repository does not contain an int8 AVX2 ONNX model.")
    shutil.copy2(downloaded, target)
    print(f"ONNX int8 model ready: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
