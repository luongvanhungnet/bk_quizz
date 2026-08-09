import hashlib
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import numpy as np

from app.services.bounded_cache import LruCache


@dataclass(frozen=True)
class CitationInput:
    key: str
    source_id: str
    quote: str


@dataclass(frozen=True)
class CitationMatch:
    key: str
    source_id: str
    canonical_quote: str
    method: str
    score: float


@dataclass(frozen=True)
class _Window:
    source_id: str
    text: str
    start: int
    end: int
    cache_key: str


class CitationMatcher:
    def __init__(
        self,
        *,
        mode: str = "semantic",
        embedding_service: Any | None = None,
        lexical_min_score: float = 0.82,
        semantic_same_source_min_score: float = 0.72,
        semantic_cross_source_min_score: float = 0.80,
        uniqueness_margin: float = 0.08,
        max_window_chars: int = 600,
        max_candidates_per_source: int = 128,
    ) -> None:
        self._mode = mode
        self._embedding = embedding_service
        self._lexical_min_score = lexical_min_score
        self._semantic_same_source_min_score = semantic_same_source_min_score
        self._semantic_cross_source_min_score = semantic_cross_source_min_score
        self._uniqueness_margin = uniqueness_margin
        self._max_window_chars = max_window_chars
        self._max_candidates_per_source = max_candidates_per_source
        self._window_embedding_cache: LruCache[str, np.ndarray] = LruCache(4096)
        self._last_degraded_error_code: str | None = None

    @property
    def last_degraded_error_code(self) -> str | None:
        return self._last_degraded_error_code

    def resolve(
        self,
        citations: list[CitationInput],
        sources: dict[str, Any],
    ) -> list[CitationMatch | None]:
        self._last_degraded_error_code = None
        results: list[CitationMatch | None] = []
        unresolved: list[tuple[int, CitationInput]] = []
        windows = self._windows(sources)
        for index, item in enumerate(citations):
            matched = self._match_normalized(item, sources)
            if matched is None and self._mode in {"lexical", "semantic"}:
                matched = self._match_lexical(item, windows)
            results.append(matched)
            if matched is None:
                unresolved.append((index, item))
        if self._mode == "semantic" and self._embedding is not None and unresolved:
            try:
                semantic = self._match_semantic(
                    [item for _, item in unresolved], windows
                )
            except Exception:
                # Semantic verification improves quality but must never discard an
                # otherwise usable quiz. Exact/normalized/lexical results above
                # remain authoritative and unresolved quotes become warnings.
                self._last_degraded_error_code = "CITATION_SEMANTIC_UNAVAILABLE"
                semantic = [None] * len(unresolved)
            for (index, _), matched in zip(unresolved, semantic, strict=True):
                results[index] = matched
        return results

    def _match_normalized(
        self,
        citation: CitationInput,
        sources: dict[str, Any],
    ) -> CitationMatch | None:
        source = sources.get(citation.source_id)
        if source is None:
            return None
        canonical = self.canonical_span(source.text, citation.quote)
        if canonical is None:
            return None
        return CitationMatch(
            citation.key,
            citation.source_id,
            canonical,
            "NORMALIZED",
            1.0,
        )

    def _match_lexical(
        self,
        citation: CitationInput,
        windows: list[_Window],
    ) -> CitationMatch | None:
        candidates = [item for item in windows if item.source_id == citation.source_id]
        scored = [
            (self._lexical_score(citation.quote, item.text), item)
            for item in candidates
        ]
        best = self._best_unique(scored, self._lexical_min_score)
        if best is None:
            return None
        score, window = best
        return CitationMatch(
            citation.key,
            window.source_id,
            window.text,
            "LEXICAL",
            score,
        )

    def _match_semantic(
        self,
        citations: list[CitationInput],
        windows: list[_Window],
    ) -> list[CitationMatch | None]:
        embedding = self._embedding
        if not windows or embedding is None:
            return [None] * len(citations)
        quote_vectors = self._normalize_vectors(self._encode_batched(
            embedding, [item.quote for item in citations]
        ))
        cached_vectors: list[np.ndarray | None] = [
            self._window_embedding_cache.get(item.cache_key) for item in windows
        ]
        missing_indices = [
            index for index, value in enumerate(cached_vectors) if value is None
        ]
        if missing_indices:
            encoded = self._normalize_vectors(self._encode_batched(
                embedding,
                [windows[index].text for index in missing_indices],
            ))
            for index, vector in zip(missing_indices, encoded, strict=True):
                cached_vectors[index] = vector
                self._window_embedding_cache.put(windows[index].cache_key, vector.copy())
        if any(value is None for value in cached_vectors):
            raise ValueError("CITATION_WINDOW_EMBEDDING_MISSING")
        window_vectors = np.asarray(cached_vectors, dtype=np.float32)
        if window_vectors.ndim != 2 or quote_vectors.ndim != 2:
            raise ValueError("CITATION_EMBEDDING_DIMENSION_INVALID")
        if window_vectors.shape[1] != quote_vectors.shape[1]:
            raise ValueError("CITATION_EMBEDDING_DIMENSION_MISMATCH")
        if not np.isfinite(window_vectors).all() or not np.isfinite(quote_vectors).all():
            raise ValueError("CITATION_EMBEDDING_NON_FINITE")
        results: list[CitationMatch | None] = []
        for citation, quote_vector in zip(citations, quote_vectors, strict=True):
            scores = window_vectors @ quote_vector
            same_source = [
                (float(score), window)
                for score, window in zip(scores, windows, strict=True)
                if window.source_id == citation.source_id
            ]
            best = self._best_unique(
                same_source, self._semantic_same_source_min_score
            )
            method = "SEMANTIC_SAME_SOURCE"
            if best is None:
                best = self._best_unique(
                    list(zip((float(value) for value in scores), windows, strict=True)),
                    self._semantic_cross_source_min_score,
                )
                method = "SEMANTIC_CROSS_SOURCE"
            if best is None:
                results.append(None)
                continue
            score, window = best
            results.append(CitationMatch(
                citation.key,
                window.source_id,
                window.text,
                method,
                score,
            ))
        return results

    @staticmethod
    def _encode_batched(
        embedding: Any, texts: list[str], batch_size: int = 64
    ) -> np.ndarray:
        batches = [
            np.asarray(
                embedding.encode_documents(texts[offset:offset + batch_size]),
                dtype=np.float32,
            )
            for offset in range(0, len(texts), batch_size)
        ]
        if not batches:
            return np.empty((0, 0), dtype=np.float32)
        return np.vstack(batches)

    @staticmethod
    def _normalize_vectors(values: Any) -> np.ndarray:
        vectors = np.asarray(values, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.clip(norms, 1e-12, None)

    def _best_unique(
        self,
        scored: list[tuple[float, _Window]],
        threshold: float,
    ) -> tuple[float, _Window] | None:
        ordered = sorted(scored, key=lambda item: (-item[0], len(item[1].text)))
        if not ordered or ordered[0][0] < threshold:
            return None
        best_score, best_window = ordered[0]
        runner_up = next(
            (
                score
                for score, window in ordered[1:]
                if window.source_id != best_window.source_id
                or self._overlap(window, best_window) < 0.5
            ),
            None,
        )
        if runner_up is not None and best_score - runner_up < self._uniqueness_margin:
            return None
        return best_score, best_window

    def _windows(self, sources: dict[str, Any]) -> list[_Window]:
        windows: list[_Window] = []
        for source_id, source in sources.items():
            chunk = getattr(getattr(source, "candidate", None), "chunk", None)
            chunk_id = getattr(chunk, "chunk_id", None)
            source_fingerprint = str(chunk_id or hashlib.sha256(
                source.text.encode("utf-8")
            ).hexdigest())
            sentences = [
                (match.start(), match.end(), match.group(0).strip())
                for match in re.finditer(
                    r"[^\n.!?…]+(?:[.!?…]+|(?=\n)|$)",
                    source.text,
                    flags=re.UNICODE,
                )
                if match.group(0).strip()
            ]
            source_windows: list[_Window] = []
            for start_index in range(len(sentences)):
                for width in range(1, 4):
                    selected = sentences[start_index : start_index + width]
                    if len(selected) != width:
                        break
                    start = selected[0][0]
                    end = selected[-1][1]
                    text = source.text[start:end].strip()
                    if len(text) < 20 or len(text) > self._max_window_chars:
                        continue
                    source_windows.append(_Window(
                        source_id,
                        text,
                        start,
                        end,
                        f"{source_fingerprint}:{start}:{end}",
                    ))
            windows.extend(source_windows[: self._max_candidates_per_source])
        return windows

    @staticmethod
    def _overlap(left: _Window, right: _Window) -> float:
        if left.source_id != right.source_id:
            return 0.0
        intersection = max(0, min(left.end, right.end) - max(left.start, right.start))
        shortest = max(1, min(left.end - left.start, right.end - right.start))
        return intersection / shortest

    @staticmethod
    def _lexical_score(left: str, right: str) -> float:
        left_tokens = CitationMatcher._tokens(left)
        right_tokens = CitationMatcher._tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        sequence = SequenceMatcher(None, left_tokens, right_tokens).ratio()
        left_set = set(left_tokens)
        right_set = set(right_tokens)
        jaccard = len(left_set & right_set) / len(left_set | right_set)
        return 0.6 * sequence + 0.4 * jaccard

    @staticmethod
    def canonical_span(text: str, quote: str) -> str | None:
        if len(re.sub(r"\s+", " ", quote).strip()) < 8:
            return None
        source_tokens = list(re.finditer(r"\w+", text, flags=re.UNICODE))
        quote_tokens = CitationMatcher._tokens(quote)
        normalized_source = [
            CitationMatcher._normalize(match.group(0)) for match in source_tokens
        ]
        width = len(quote_tokens)
        if width == 0:
            return None
        for start in range(len(source_tokens) - width + 1):
            if normalized_source[start : start + width] == quote_tokens:
                return text[
                    source_tokens[start].start() : source_tokens[start + width - 1].end()
                ]
        return None

    @staticmethod
    def _tokens(value: str) -> list[str]:
        value = unicodedata.normalize("NFKC", value)
        value = value.replace("\u00ad", "").replace("\u200b", "")
        value = re.sub(r"(?<=\w)-\s*(?:\r?\n)\s*(?=\w)", "", value)
        return [
            CitationMatcher._normalize(match.group(0))
            for match in re.finditer(r"\w+", value, flags=re.UNICODE)
        ]

    @staticmethod
    def _normalize(value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        value = value.replace("\u00ad", "").replace("\u200b", "")
        return value.casefold()
