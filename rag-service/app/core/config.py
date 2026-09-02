import hashlib
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

RAG_SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = RAG_SERVICE_ROOT / ".env"


class GeminiConfigConflictError(RuntimeError):
    code = "GEMINI_CONFIG_CONFLICT"


@dataclass(frozen=True)
class GeminiCredentialDiagnostics:
    source: str
    fingerprint: str | None
    length: int
    process_configured: bool
    dotenv_configured: bool


def _secret_fingerprint(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def gemini_credential_diagnostics(
    settings: "Settings",
    *,
    env_file: Path = DEFAULT_ENV_FILE,
) -> GeminiCredentialDiagnostics:
    process_key = os.getenv("GEMINI_API_KEY", "").strip()
    dotenv_key = str(dotenv_values(env_file).get("GEMINI_API_KEY") or "").strip()
    selected_key = settings.gemini_api_key.strip()
    if process_key and dotenv_key and process_key == dotenv_key:
        source = "process_env_and_dotenv"
    elif process_key and selected_key == process_key:
        source = "process_env"
    elif dotenv_key and selected_key == dotenv_key:
        source = "dotenv"
    elif selected_key:
        source = "injected"
    else:
        source = "not_configured"
    return GeminiCredentialDiagnostics(
        source=source,
        fingerprint=_secret_fingerprint(selected_key),
        length=len(selected_key),
        process_configured=bool(process_key),
        dotenv_configured=bool(dotenv_key),
    )


def _validate_gemini_credential_sources(
    settings: "Settings",
    *,
    env_file: Path,
) -> None:
    if settings.app_env != "development":
        return
    process_key = os.getenv("GEMINI_API_KEY", "").strip()
    dotenv_key = str(dotenv_values(env_file).get("GEMINI_API_KEY") or "").strip()
    if process_key and dotenv_key and process_key != dotenv_key:
        raise GeminiConfigConflictError(
            "GEMINI_CONFIG_CONFLICT: GEMINI_API_KEY trong process environment "
            "khác với dotenv của rag-service. Hãy xóa biến môi trường cũ hoặc "
            "đồng bộ hai nguồn trước khi khởi động. "
            f"processFingerprint={_secret_fingerprint(process_key)} "
            f"dotenvFingerprint={_secret_fingerprint(dotenv_key)}"
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BKQuiz RAG Service"
    app_build_revision: str = "development"
    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8090, ge=1, le=65535)

    gemini_api_key: str = ""
    gemini_api_base_url: str | None = None
    gemini_model: str
    gemini_temperature: float = Field(default=0.2, ge=0, le=2)
    gemini_max_output_tokens: int = Field(default=32768, ge=1, le=65536)
    gemini_timeout_seconds: float = Field(default=120, gt=0, le=300)
    gemini_max_attempts: int = Field(default=3, ge=1, le=3)
    gemini_max_retries: int | None = Field(default=None, ge=0, le=3)
    gemini_max_concurrency: int = Field(default=2, ge=1, le=20)
    gemini_retry_initial_delay_seconds: float = Field(default=1, ge=0, le=30)
    llm_fallback_enabled: bool = True
    gemini_oauth_enabled: bool = True
    gemini_oauth_model: str = "gemini-3.6-flash"
    gemini_oauth_quota_project: str = ""
    gemini_oauth_timeout_seconds: float = Field(default=120, gt=0, le=300)
    gemini_batch_size: int = Field(default=10, ge=1, le=20)
    math_vision_enabled: bool = True
    math_vision_model: str = "gemini-3.5-flash-lite"
    math_vision_timeout_seconds: float = Field(default=60, gt=0, le=300)
    math_extraction_version: str = "pdf-math-v1"
    ollama_enabled: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_timeout_seconds: float = Field(default=180, gt=0, le=600)
    ollama_context_size: int = Field(default=4096, ge=1024, le=40960)
    ollama_max_output_tokens: int = Field(default=2400, ge=256, le=8192)
    ollama_temperature: float = Field(default=0.1, ge=0, le=2)
    ollama_keep_alive: str = "60s"
    ollama_max_questions_per_call: int = Field(default=2, ge=1, le=4)
    ollama_batch_max_retries: int = Field(default=1, ge=0, le=3)
    llm_circuit_breaker_failure_threshold: int = Field(default=1, ge=1, le=100)
    llm_circuit_breaker_cooldown_seconds: int = Field(default=300, ge=1, le=3600)

    spring_boot_internal_api_key: str
    spring_boot_previous_internal_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"
    redis_connect_timeout_seconds: float = Field(default=1, gt=0, le=30)
    redis_socket_timeout_seconds: float = Field(default=2, gt=0, le=60)
    cache_redis_provider: Literal["redis", "upstash"] = "redis"
    cache_redis_url: str = ""
    cache_redis_max_connections: int = Field(default=10, ge=1, le=100)
    index_lock_mode: Literal["auto", "redis", "local"] = "auto"
    index_lock_fallback_cooldown_seconds: int = Field(default=30, ge=1, le=3600)
    job_dispatch_backend: Literal["celery", "gcp"] = "celery"
    gcp_project_id: str = ""
    gcp_region: str = ""
    pubsub_indexing_topic: str = "bkquiz-rag-indexing"
    cloud_tasks_queue: str = "bkquiz-rag-indexing"
    cloud_tasks_worker_url: str = ""
    cloud_tasks_oidc_audience: str = ""
    cloud_tasks_service_account_email: str = ""
    cloud_tasks_dispatch_deadline_seconds: int = Field(default=900, ge=30, le=1800)
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
    citation_match_mode: Literal["exact", "lexical", "semantic"] = "semantic"
    citation_lexical_min_score: float = Field(default=0.82, ge=0, le=1)
    citation_semantic_same_source_min_score: float = Field(default=0.72, ge=0, le=1)
    citation_semantic_cross_source_min_score: float = Field(default=0.80, ge=0, le=1)
    citation_uniqueness_margin: float = Field(default=0.08, ge=0, le=1)
    citation_max_window_chars: int = Field(default=600, ge=50, le=2000)
    citation_max_candidates_per_source: int = Field(default=128, ge=1, le=1000)
    rag_debug_api_key: str = ""
    query_embedding_cache_size: int = Field(default=512, ge=1, le=10000)
    retrieval_cache_size: int = Field(default=512, ge=1, le=10000)
    retrieval_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)

    max_upload_size_mb: int = Field(default=20, ge=1, le=100)
    max_documents_per_user: int = Field(default=100, ge=1, le=10000)
    max_storage_mb_per_user: int = Field(default=500, ge=1, le=100000)
    user_upload_dir: Path = Path("data/uploads/users")
    user_index_dir: Path = Path("data/indexes/users")
    document_staging_dir: Path = Path("data/tmp/rag-documents")
    document_storage_backend: Literal["local", "r2"] = "local"
    document_storage_endpoint: str = ""
    document_storage_bucket: str = ""
    document_storage_access_key: str = ""
    document_storage_secret_key: str = ""
    document_storage_region: str = "auto"
    document_storage_prefix: str = "rag-documents"
    database_url: str = "sqlite:///data/rag.db"
    database_pool_size: int = Field(default=4, ge=1, le=20)
    database_max_overflow: int = Field(default=2, ge=0, le=20)
    database_pool_timeout_seconds: int = Field(default=10, ge=1, le=120)
    database_pool_recycle_seconds: int = Field(default=300, ge=30, le=3600)
    database_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    vector_store_backend: Literal["faiss", "qdrant"] = "faiss"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "bkquiz_chunks"
    qdrant_timeout_seconds: float = Field(default=15, gt=0, le=120)
    qdrant_upsert_batch_size: int = Field(default=128, ge=1, le=1000)

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

    @field_validator("redis_url", "cache_redis_url")
    @classmethod
    def redis_url_must_use_redis_scheme(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and urlsplit(normalized).scheme not in {"redis", "rediss"}:
            raise ValueError("Redis URL phải dùng scheme redis:// hoặc rediss://.")
        return normalized

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_ollama_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL phải là URL HTTP hợp lệ.")
        return normalized

    @field_validator("gemini_oauth_quota_project")
    @classmethod
    def normalize_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("rag_debug_api_key")
    @classmethod
    def normalize_debug_secret(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "embedding_model",
        "reranker_model",
        "gemini_oauth_model",
        "ollama_model",
        "ollama_keep_alive",
    )
    @classmethod
    def embedding_model_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("EMBEDDING_MODEL không được để trống.")
        return normalized

    @field_validator("database_url")
    @classmethod
    def database_url_must_be_supported(cls, value: str) -> str:
        normalized = value.strip()
        try:
            backend = make_url(normalized).get_backend_name()
        except Exception as error:
            raise ValueError("DATABASE_URL không hợp lệ.") from error
        if backend not in {"sqlite", "postgresql"}:
            raise ValueError("DATABASE_URL chỉ hỗ trợ SQLite hoặc PostgreSQL.")
        if backend == "postgresql" and make_url(normalized).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL PostgreSQL phải dùng scheme postgresql+psycopg://.")
        return normalized

    @field_validator("qdrant_url")
    @classmethod
    def qdrant_url_must_be_http(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("QDRANT_URL phải là URL HTTP hợp lệ.")
        return normalized

    @field_validator("qdrant_api_key")
    @classmethod
    def normalize_qdrant_secret(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "document_storage_endpoint",
        "document_storage_bucket",
        "document_storage_access_key",
        "document_storage_secret_key",
        "document_storage_region",
        "document_storage_prefix",
    )
    @classmethod
    def normalize_document_storage_text(cls, value: str) -> str:
        return value.strip().strip("/")

    @field_validator("qdrant_collection")
    @classmethod
    def qdrant_collection_must_be_safe(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", normalized):
            raise ValueError("QDRANT_COLLECTION chỉ được chứa chữ, số, _ hoặc -.")
        return normalized

    @model_validator(mode="after")
    def validate_rag_limits(self) -> "Settings":
        if not self.cache_redis_url:
            self.cache_redis_url = self.redis_url
        if self.chunk_overlap_chars >= self.chunk_size_chars:
            raise ValueError("CHUNK_OVERLAP_CHARS phải nhỏ hơn CHUNK_SIZE_CHARS.")
        if self.rag_default_top_k > self.rag_max_top_k:
            raise ValueError("RAG_DEFAULT_TOP_K không được lớn hơn RAG_MAX_TOP_K.")
        if self.app_env == "production" and self.index_lock_mode == "local":
            raise ValueError("INDEX_LOCK_MODE=local không được phép trong production.")
        if self.app_env == "production":
            database = make_url(self.database_url)
            if database.get_backend_name() != "postgresql":
                raise ValueError("DATABASE_URL production phải dùng PostgreSQL/Neon.")
            query = {str(key).lower(): str(value).lower() for key, value in database.query.items()}
            if query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("DATABASE_URL production phải bật sslmode=require hoặc mạnh hơn.")
            if self.vector_store_backend != "qdrant":
                raise ValueError("VECTOR_STORE_BACKEND production phải là qdrant.")
            if not self.qdrant_url.startswith("https://"):
                raise ValueError("QDRANT_URL production phải dùng HTTPS.")
            if not self.qdrant_api_key:
                raise ValueError("QDRANT_API_KEY production không được để trống.")
            if self.document_storage_backend != "r2":
                raise ValueError("DOCUMENT_STORAGE_BACKEND production phải là r2.")
            if not self.document_storage_endpoint.startswith("https://"):
                raise ValueError("DOCUMENT_STORAGE_ENDPOINT production phải dùng HTTPS.")
            if not all(
                (
                    self.document_storage_bucket,
                    self.document_storage_access_key,
                    self.document_storage_secret_key,
                )
            ):
                raise ValueError("Cấu hình R2 document storage production chưa đầy đủ.")
            if self.ollama_enabled:
                raise ValueError("OLLAMA_ENABLED phải là false trong production Cloud Run.")
            if self.cache_redis_provider == "upstash":
                cache_redis = urlsplit(self.cache_redis_url)
                if cache_redis.scheme != "rediss":
                    raise ValueError("CACHE_REDIS_URL Upstash production phải dùng rediss://.")
                if not cache_redis.hostname or not cache_redis.hostname.endswith(".upstash.io"):
                    raise ValueError("CACHE_REDIS_URL không phải endpoint Upstash hợp lệ.")
                if not cache_redis.password:
                    raise ValueError("CACHE_REDIS_URL Upstash phải chứa credential trong Secret Manager.")
            if self.job_dispatch_backend == "gcp":
                if not all((
                    self.gcp_project_id,
                    self.gcp_region,
                    self.pubsub_indexing_topic,
                    self.cloud_tasks_queue,
                    self.cloud_tasks_worker_url,
                    self.cloud_tasks_oidc_audience,
                    self.cloud_tasks_service_account_email,
                )):
                    raise ValueError("Cấu hình Pub/Sub và Cloud Tasks production chưa đầy đủ.")
                if not self.cloud_tasks_worker_url.startswith("https://"):
                    raise ValueError("CLOUD_TASKS_WORKER_URL production phải dùng HTTPS.")
                if not self.cloud_tasks_oidc_audience.startswith("https://"):
                    raise ValueError("CLOUD_TASKS_OIDC_AUDIENCE production phải dùng HTTPS.")
        if self.celery_worker_heartbeat_ttl_seconds <= self.celery_worker_heartbeat_interval_seconds:
            raise ValueError("CELERY_WORKER_HEARTBEAT_TTL_SECONDS phải lớn hơn heartbeat interval.")
        if (
            self.app_env == "production"
            and self.llm_fallback_enabled
            and not (self.gemini_api_key or self.gemini_oauth_enabled or self.ollama_enabled)
        ):
            raise ValueError("LLM fallback được bật nhưng không có provider sinh quiz nào khả dụng.")
        return self

    @property
    def effective_gemini_max_attempts(self) -> int:
        return (self.gemini_max_retries + 1) if self.gemini_max_retries is not None else self.gemini_max_attempts


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def load_settings(*, env_file: Path = DEFAULT_ENV_FILE) -> Settings:
    settings = Settings(_env_file=env_file)
    _validate_gemini_credential_sources(settings, env_file=env_file)
    return settings
