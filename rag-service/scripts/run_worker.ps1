param(
    [ValidateSet("INFO", "DEBUG", "WARNING")]
    [string]$LogLevel = "INFO"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Không tìm thấy virtual environment tại $python"
}

Push-Location $projectRoot
try {
    & $python -c "from app.core.config import Settings; from redis import Redis; s=Settings(); r=Redis.from_url(s.redis_url, socket_connect_timeout=s.redis_connect_timeout_seconds); assert r.ping(); print(f'Redis UP | queue={s.celery_queue} | pool={s.celery_worker_pool} | concurrency={s.celery_worker_concurrency}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Redis chưa hoạt động. Hãy khởi động Redis trước khi chạy RAG worker."
    }
    & $python -m celery -A app.worker.celery_app:celery_app worker `
        "--loglevel=$LogLevel" --pool=solo --concurrency=1
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
