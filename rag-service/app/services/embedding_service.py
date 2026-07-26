import gc
import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from prometheus_client import Counter

from app.core.exceptions import ServiceError
from app.services.bounded_cache import LruCache

LOGGER = logging.getLogger("uvicorn.error")
QUERY_EMBEDDING_CACHE = Counter(
    "rag_query_embedding_cache_total",
    "Query embedding cache lookups",
    ["result"],
)


class _OnnxEmbeddingModel:
    def __init__(self, model_path: Path, precision: str) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        config = json.loads((model_path / "config.json").read_text(encoding="utf-8"))
        self._dimension = int(config["hidden_size"])
        tokenizer_config = json.loads(
            (model_path / "tokenizer_config.json").read_text(encoding="utf-8")
        )
        self._tokenizer = Tokenizer.from_file(str(model_path / "tokenizer.json"))
        pad_token = str(tokenizer_config.get("pad_token", "<pad>"))
        pad_id = self._tokenizer.token_to_id(pad_token)
        if pad_id is None:
            raise ValueError("ONNX tokenizer không có pad token.")
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=pad_token)
        self._tokenizer.enable_truncation(max_length=512)
        options = ort.SessionOptions()
        threads = max(1, int(os.getenv("RAG_CPU_THREADS", "2")))
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self._session = ort.InferenceSession(
            str(
                model_path
                / "onnx"
                / ("model_qint8_avx2.onnx" if precision == "int8" else "model.onnx")
            ),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {item.name for item in self._session.get_inputs()}

    def get_embedding_dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int,
        **_: Any,
    ) -> np.ndarray:
        batches: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            encoded = self._tokenizer.encode_batch(texts[start : start + batch_size])
            input_ids = np.asarray([item.ids for item in encoded], dtype=np.int64)
            attention_mask = np.asarray(
                [item.attention_mask for item in encoded], dtype=np.int64
            )
            token_type_ids = np.asarray(
                [item.type_ids for item in encoded], dtype=np.int64
            )
            values = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            }
            inputs = {
                key: np.asarray(value, dtype=np.int64)
                for key, value in values.items()
                if key in self._input_names
            }
            hidden = np.asarray(self._session.run(None, inputs)[0], dtype=np.float32)
            mask = attention_mask.astype(np.float32)[..., None]
            pooled = (hidden * mask).sum(axis=1) / np.clip(mask.sum(axis=1), 1e-9, None)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            batches.append(pooled / np.clip(norms, 1e-12, None))
        return np.ascontiguousarray(np.vstack(batches), dtype=np.float32)


class EmbeddingService:
    def __init__(
        self,
        model_name: str,
        query_cache_size: int = 512,
        *,
        backend: str = "torch",
        precision: str = "fp32",
        onnx_model_path: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.backend = backend
        self.precision = precision
        self.onnx_model_path = onnx_model_path
        self.effective_backend = "unloaded"
        self._model: Any | None = None
        self._lock = Lock()
        self._query_cache: LruCache[tuple[str, str], np.ndarray] = LruCache(
            query_cache_size
        )

    @property
    def dimension(self) -> int:
        model = self._get_model()
        dimension = model.get_embedding_dimension()
        if not dimension:
            raise ServiceError(
                503,
                "EMBEDDING_MODEL_UNAVAILABLE",
                "Không xác định được số chiều của model embedding.",
            )
        return int(dimension)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def runtime_fingerprint(self) -> str:
        if self.effective_backend != "unloaded":
            return self.effective_backend
        return f"{self.backend}:{self.precision if self.backend == 'onnx' else 'fp32'}"

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self.effective_backend = "unloaded"
            self._query_cache.clear()
        gc.collect()

    def encode_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        return self._encode(texts)

    def encode_query(self, text: str) -> np.ndarray:
        key = (self.model_name, text)
        cached = self._query_cache.get(key)
        if cached is not None:
            QUERY_EMBEDDING_CACHE.labels("hit").inc()
            return cached.copy()
        QUERY_EMBEDDING_CACHE.labels("miss").inc()
        value = self._encode([text])
        self._query_cache.put(key, value.copy())
        return value

    def _encode(self, texts: list[str]) -> np.ndarray:
        try:
            values = self._get_model().encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as error:
            raise ServiceError(
                503,
                "EMBEDDING_MODEL_UNAVAILABLE",
                "Không thể tạo embedding bằng model local.",
            ) from error
        array = np.asarray(values, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        return np.ascontiguousarray(array)

    def _get_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        backend = self.backend
                        if backend == "onnx":
                            prepared = self.onnx_model_path
                            if prepared is None or not prepared.exists():
                                LOGGER.warning(
                                    "embedding_onnx_fallback code=ONNX_MODEL_NOT_PREPARED path=%s",
                                    prepared,
                                )
                                backend = "torch"
                            else:
                                self._model = _OnnxEmbeddingModel(prepared, self.precision)
                        if backend == "torch":
                            from sentence_transformers import SentenceTransformer

                            self._model = SentenceTransformer(
                                self.model_name,
                                device="cpu",
                                backend="torch",
                            )
                        self.effective_backend = (
                            f"{backend}:{self.precision if backend == 'onnx' else 'fp32'}"
                        )
                    except Exception as error:
                        raise ServiceError(
                            503,
                            "EMBEDDING_MODEL_UNAVAILABLE",
                            "Không thể tải model embedding local.",
                        ) from error
        return self._model
