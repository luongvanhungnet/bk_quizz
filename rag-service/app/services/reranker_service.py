import logging
from threading import RLock
from typing import Any

LOGGER = logging.getLogger("uvicorn.error")


class RerankerService:
    def __init__(self, model_name: str, enabled: bool, model: Any | None = None) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._model = model
        self._available = model is not None
        self._error_code: str | None = None
        self._lock = RLock()

    @property
    def available(self) -> bool:
        return self.enabled and self._available

    @property
    def error_code(self) -> str | None:
        return self._error_code

    def warmup(self) -> None:
        if not self.enabled or self._available:
            return
        with self._lock:
            if self._available:
                return
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(self.model_name, device="cpu")
                self._available = True
                self._error_code = None
            except Exception as error:
                self._available = False
                self._error_code = "RERANKER_MODEL_UNAVAILABLE"
                LOGGER.warning(
                    "Reranker disabled model=%s error_type=%s",
                    self.model_name,
                    type(error).__name__,
                )

    def score(self, query: str, passages: list[str]) -> list[float] | None:
        if not passages:
            return None
        if self.enabled and not self._available:
            self.warmup()
        if not self.available:
            return None
        model = self._model
        if model is None:
            return None
        try:
            values = model.predict(
                [(query, passage) for passage in passages],
                batch_size=min(16, len(passages)),
                show_progress_bar=False,
            )
            return [float(value) for value in values]
        except Exception as error:
            self._available = False
            self._error_code = "RERANKER_INFERENCE_FAILED"
            LOGGER.warning(
                "Reranker inference disabled model=%s error_type=%s",
                self.model_name,
                type(error).__name__,
            )
            return None
