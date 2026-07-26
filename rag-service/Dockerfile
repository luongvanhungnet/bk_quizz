FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/data/model-cache \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2

ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

RUN groupadd --system rag && useradd --system --gid rag --create-home rag
WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY integration ./integration
RUN mkdir -p /app/data/uploads/users /app/data/indexes/users /app/data/indexes/system /app/data/model-cache /app/models \
    && python scripts/download_onnx_embedding.py --model "${EMBEDDING_MODEL}" --output /app/models/embedding-onnx \
    && chown -R rag:rag /app
USER rag
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
