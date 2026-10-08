import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3
import botocore.session
from botocore.config import Config

from shockt.settings import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

ISOLATED_AWS_CONFIG = Path(__file__).with_name("isolated_aws_config.ini")


def sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def object_key(dataset: str, partition_key: str, filename: str) -> str:
    return f"raw/{dataset}/{partition_key}/{filename}"


class Archive(Protocol):
    def put(self, key: str, body: bytes, content_type: str) -> str:
        """Store `body` at `key` and return its SHA-256."""
        ...

    def get(self, key: str) -> bytes: ...


class NeonArchive:
    """Archive in Neon Object Storage through its S3-compatible API.

    Credentials come only from `Settings`, never from the AWS environment or `~/.aws`, so a
    developer's own AWS profile can't reach the Neon endpoint.
    """

    def __init__(self, settings: Settings) -> None:
        missing = [
            name
            for name, value in (
                ("NEON_S3_ENDPOINT_URL", settings.neon_s3_endpoint_url),
                ("NEON_S3_ACCESS_KEY_ID", settings.neon_s3_access_key_id),
                ("NEON_S3_SECRET_ACCESS_KEY", settings.neon_s3_secret_access_key),
            )
            if not value
        ]
        if missing or settings.neon_s3_secret_access_key is None:
            raise ValueError(f"Object storage settings missing: {', '.join(missing)}")
        # Ignore AWS_PROFILE and ~/.aws so only the Neon credentials below are used.
        core = botocore.session.Session()
        core.set_config_variable("profile", "default")
        core.set_config_variable("config_file", str(ISOLATED_AWS_CONFIG))
        core.set_config_variable("credentials_file", os.devnull)
        session = boto3.session.Session(
            botocore_session=core,
            aws_access_key_id=settings.neon_s3_access_key_id,
            aws_secret_access_key=settings.neon_s3_secret_access_key.get_secret_value(),
            region_name=settings.neon_s3_region,
        )
        self._bucket = settings.archive_bucket
        self._client: S3Client = session.client(
            "s3",
            endpoint_url=settings.neon_s3_endpoint_url,
            config=Config(
                s3={"addressing_style": "path"},
                retries={"mode": "standard", "max_attempts": 6},
            ),
        )

    @property
    def client(self) -> "S3Client":
        return self._client

    def put(self, key: str, body: bytes, content_type: str) -> str:
        digest = sha256_hex(body)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return digest

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
