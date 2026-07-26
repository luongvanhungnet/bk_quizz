from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BKQuiz RAG Service"
    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8090, ge=1, le=65535)

    gemini_api_key: str = ""
    gemini_api_base_url: str | None = None
    gemini_model: str
    gemini_temperature: float = Field(default=0.2, ge=0, le=2)
    gemini_max_output_tokens: int = Field(default=2048, ge=1, le=65536)
    gemini_timeout_seconds: float = Field(default=30, gt=0, le=300)
    gemini_max_attempts: int = Field(default=3, ge=1, le=3)
    gemini_max_retries: int | None = Field(default=None, ge=0, le=3)
    gemini_max_concurrency: int = Field(default=2, ge=1, le=20)
    gemini_retry_initial_delay_seconds: float = Field(default=1, ge=0, le=30)

    spring_boot_internal_api_key: str
    spring_boot_previous_internal_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"
    redis_connect_timeout_seconds: float = Field(default=1, gt=0, le=30)
    redis_socket_timeout_seconds: float = Field(default=2, gt=0, le=60)
    index_lock_mode: Literal["auto", "redis", "local"] = "auto"
    index_lock_fallback_cooldown_seconds: int = Field(default=30, ge=1, le=3600)
    celery_queue: str = "rag-indexing"
    celery_worker_pool: Literal["solo"] = "solo"
    celery_worker_concurrency: int = 1    
    celery_worker_heartbeat_key: str = "rag:worker:heartbeat"
    celery_worker_heartbeat_interval_seconds: int = Field(default=10, ge=1, le=60)
    celery_worker_heartbeat_ttl_seconds: int = Field(default=30, ge=5, le=300)
    pending_job_reconcile_seconds: int = Field(default=30, ge=10, le=3600)
    indexing_job_max_attempts: int = Field(default=4, ge=1, le=10)
    indexing_job_stale_seconds: int = Field(default=300, ge=30, le=86400)
    gemini_global_rpm: int = Field(default=10, ge=1, le=10000)
    gemini_user_rpm: int = Field(default=5, ge=1, le=10000)
    ask_user_rpm: int = Field(default=20, ge=1, le=10000)
    upload_user_rpm: int = Field(default=5, ge=1, le=10000)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    circuit_open_seconds: int = Field(default=60, ge=1, le=3600)
    minimum_free_disk_mb: int = Field(default=256, ge=1)
    rag_low_memory_mode: bool = True
    worker_model_idle_seconds: int = Field(default=60, ge=10, le=3600)

    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_backend: Literal["torch", "onnx"] = "onnx"
    embedding_precision: Literal["fp32", "int8"] = "int8"
    embedding_onnx_model_path: Path = Path("data/models/embedding-onnx")
    rag_preload_embedding: bool = True
    rag_cpu_threads: int = Field(default=2, ge=1, le=16)
    system_documents_dir: Path = Path("data/system-documents")
    system_index_dir: Path = Path("data/indexes/system")
    chunk_size_chars: int = Field(default=1200, ge=100, le=10000)
    chunk_overlap_chars: int = Field(default=200, ge=0, le=5000)
    rag_default_top_k: int = Field(default=5, ge=1, le=50)
    rag_max_top_k: int = Field(default=10, ge=1, le=50)
    rag_min_score: float = Field(default=0.25, ge=-1, le=1)

    hybrid_enabled: bool = True
    query_rewrite_enabled: bool = True
    hybrid_vector_candidates: int = Field(default=30, ge=1, le=200)
    hybrid_bm25_candidates: int = Field(default=30, ge=1, le=200)
    hybrid_rrf_k: int = Field(default=60, ge=1, le=1000)
    reranker_enabled: bool = True
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    rerank_candidates: int = Field(default=20, ge=1, le=100)
    rerank_min_candidates: int = Field(default=3, ge=1, le=100)
    rag_max_context_chars: int = Field(default=16000, ge=1000, le=100000)
    rag_quiz_min_useful_chars: int = Field(default=100, ge=1, le=10000)
    rag_debug_api_key: str = ""
    query_embedding_cache_size: int = Field(default=512, ge=1, le=10000)
    retrieval_cache_size: int = Field(default=512, ge=1, le=10000)
    retrieval_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)

    max_upload_size_mb: int = Field(default=20, ge=1, le=100)
    max_documents_per_user: int = Field(default=100, ge=1, le=10000)
    max_storage_mb_per_user: int = Field(default=500, ge=1, le=100000)
    user_upload_dir: Path = Path("data/uploads/users")
    user_index_dir: Path = Path("data/indexes/users")
    database_url: str = "sqlite:///data/rag.db"

    @field_validator("gemini_model", "spring_boot_internal_api_key")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Giá trị cấu hình bắt buộc không được để trống.")
        return normalized

    @field_validator("gemini_api_key")
    @classmethod
    def normalize_optional_secret(cls, value: str) -> str:
        return value.strip()

    @field_validator("gemini_api_base_url")
    @classmethod
    def normalize_optional_url(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @field_validator("rag_debug_api_key")
    @classmethod
    def normalize_debug_secret(cls, value: str) -> str:
        return value.strip()

    @field_validator("embedding_model", "reranker_model")
    @classmethod
    def embedding_model_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("EMBEDDING_MODEL không được để trống.")
        return normalized

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_sqlite(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("sqlite:///"):
            raise ValueError("Phase 3 chỉ hỗ trợ DATABASE_URL SQLite.")
        return normalized

    @model_validator(mode="after")
    def validate_rag_limits(self) -> "Settings":
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS phải nhỏ hơn CHUNK_SIZE_CHARS.")
        if self.rag_default_top_k > self.rag_max_top_k:
            raise ValueError("RAG_DEFAULT_TOP_K không được lớn hơn RAG_MAX_TOP_K.")
        if self.app_env == "production" and self.index_lock_mode == "local":
            raise ValueError("INDEX_LOCK_MODE=local không được phép trong production.")
        if self.celery_worker_heartbeat_ttl_seconds <= self.celery_worker_heartbeat_interval_seconds:
            raise ValueError("CELERY_WORKER_HEARTBEAT_TTL_SECONDS phải lớn hơn heartbeat interval.")
        return self

    @property
    def effective_gemini_max_attempts(self) -> int:
        return (self.gemini_max_retries + 1) if self.gemini_max_retries is not None else self.gemini_max_attempts


@lru_cache
def get_settings() -> Settings:
    return Settings()
