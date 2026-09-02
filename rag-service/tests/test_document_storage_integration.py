import os
import uuid
from pathlib import Path

import boto3
import pytest
from botocore.config import Config

from app.services.document_object_storage import R2DocumentObjectStorage


@pytest.mark.integration
def test_s3_compatible_document_storage_round_trip(tmp_path: Path) -> None:
    endpoint = os.getenv("RAG_TEST_S3_ENDPOINT", "").strip()
    if not endpoint:
        pytest.skip("RAG_TEST_S3_ENDPOINT is not configured")
    bucket = os.getenv("RAG_TEST_S3_BUCKET", "bkquiz-rag-test")
    access_key = os.getenv("RAG_TEST_S3_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("RAG_TEST_S3_SECRET_KEY", "minioadmin")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(s3={"addressing_style": "path"}),
    )
    try:
        client.create_bucket(Bucket=bucket)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass
    prefix = f"integration-{uuid.uuid4().hex}"
    storage = R2DocumentObjectStorage(
        client=client,
        bucket=bucket,
        prefix=prefix,
        staging_root=tmp_path / "staging",
    )
    source = tmp_path / "source.txt"
    source.write_text("BKQuiz Cloud Run", encoding="utf-8")
    try:
        storage.store(source, "owner", "document", "original-file")
        assert storage.exists("owner", "document", "original-file")
        with storage.materialize("owner", "document", "original-file") as path:
            assert path.read_text(encoding="utf-8") == "BKQuiz Cloud Run"
        storage.delete_owner("owner")
        assert not storage.exists("owner", "document", "original-file")
    finally:
        storage.close()
