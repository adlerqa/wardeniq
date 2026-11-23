"""S3 storage backend for persisting, retrieving, and managing uploaded documents.

Works with AWS S3 and any S3-compatible store (MinIO, LocalStack, Garage,
Cloudflare R2, ...) when an endpoint URL is configured.
"""
import os
import re
import time
import uuid
from typing import Optional, Dict, Any


def _truthy(v: Optional[str]) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class S3StorageManager:
    """Manages document file storage in Amazon Web Services (AWS) S3 buckets."""

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
        prefix: Optional[str] = None,
        enabled: Optional[bool] = None,
        endpoint_url: Optional[str] = None,
        force_path_style: Optional[bool] = None,
    ):
        self._endpoint_url = endpoint_url
        self._force_path_style = force_path_style
        self._bucket = bucket
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._session_token = session_token
        self._prefix = prefix.strip("/") if prefix else None
        self._enabled = enabled

    def _get_config(self) -> Dict[str, Any]:
        """Resolves configuration from constructor args, store settings, or env vars."""
        s = {}
        try:
            import main
            s = main.store.get_settings()
        except (ImportError, AttributeError):
            pass

        bucket = (
            self._bucket
            or s.get("s3_bucket")
            or os.getenv("AWS_S3_BUCKET", "")
        ).strip()

        region = (
            self._region
            or s.get("s3_region")
            or os.getenv("AWS_S3_REGION", os.getenv("AWS_REGION", "us-east-1"))
        ).strip()

        access_key = (
            self._access_key_id
            or s.get("s3_access_key_id")
            or os.getenv("AWS_ACCESS_KEY_ID", "")
        ).strip()

        secret_key = self._secret_access_key
        if not secret_key:
            if s.get("s3_secret_access_key_enc"):
                from crypto import decrypt
                secret_key = decrypt(s.get("s3_secret_access_key_enc"))
            else:
                secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "")

        session_token = (
            self._session_token
            or os.getenv("AWS_SESSION_TOKEN", "")
        ).strip()

        enabled = (
            self._enabled
            if self._enabled is not None
            else s.get("s3_enabled", bool(bucket))
        )

        prefix = (
            self._prefix
            or s.get("s3_prefix")
            or "documents"
        ).strip("/")

        endpoint_url = (
            self._endpoint_url
            if self._endpoint_url is not None
            else (s.get("s3_endpoint_url") or os.getenv("AWS_S3_ENDPOINT_URL", ""))
        ).strip()

        if self._force_path_style is not None:
            force_path_style = bool(self._force_path_style)
        elif s.get("s3_force_path_style") is not None:
            force_path_style = bool(s.get("s3_force_path_style"))
        elif os.getenv("AWS_S3_FORCE_PATH_STYLE", "").strip():
            force_path_style = _truthy(os.getenv("AWS_S3_FORCE_PATH_STYLE"))
        else:
            # Most self-hosted stores (MinIO, LocalStack, Garage) need path-style.
            force_path_style = bool(endpoint_url)

        return {
            "bucket": bucket,
            "region": region,
            "endpoint_url": endpoint_url,
            "force_path_style": force_path_style,
            "access_key_id": access_key,
            "secret_access_key": secret_key,
            "session_token": session_token,
            "enabled": bool(enabled and bucket),
            "prefix": prefix,
        }

    def is_configured(self) -> bool:
        """Returns True if S3 document storage is enabled and configured with a bucket name."""
        cfg = self._get_config()
        return cfg["enabled"] and bool(cfg["bucket"])

    def _get_client(self, config: Optional[Dict[str, Any]] = None):
        """Initializes a boto3 S3 client with configured credentials."""
        import boto3

        cfg = config or self._get_config()
        kw = {}
        if cfg.get("region"):
            kw["region_name"] = cfg["region"]
        if cfg.get("access_key_id") and cfg.get("secret_access_key"):
            kw["aws_access_key_id"] = cfg["access_key_id"]
            kw["aws_secret_access_key"] = cfg["secret_access_key"]
            if cfg.get("session_token"):
                kw["aws_session_token"] = cfg["session_token"]

        session = boto3.session.Session(**kw)
        client_kw = {}
        if cfg.get("endpoint_url"):
            # S3-compatible stores (MinIO, LocalStack, Garage, R2, ...).
            client_kw["endpoint_url"] = cfg["endpoint_url"]
        if cfg.get("force_path_style"):
            from botocore.config import Config
            client_kw["config"] = Config(
                signature_version="s3v4", s3={"addressing_style": "path"}
            )
        return session.client("s3", **client_kw)

    def test_connection(
        self,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        force_path_style: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Tests accessibility and permissions of the specified S3 bucket."""
        cfg = self._get_config()
        if endpoint_url is not None:
            cfg["endpoint_url"] = endpoint_url.strip()
            cfg["force_path_style"] = (
                bool(cfg["endpoint_url"]) if force_path_style is None else bool(force_path_style)
            )
        elif force_path_style is not None:
            cfg["force_path_style"] = bool(force_path_style)
        if bucket is not None:
            cfg["bucket"] = bucket.strip()
        if region is not None:
            cfg["region"] = region.strip()
        if access_key_id is not None:
            cfg["access_key_id"] = access_key_id.strip()
        if secret_access_key is not None:
            cfg["secret_access_key"] = secret_access_key.strip()

        if not cfg["bucket"]:
            return {"ok": False, "error": "AWS S3 bucket name is required"}

        try:
            client = self._get_client(cfg)
            # Ping bucket using head_bucket or list_objects_v2
            client.head_bucket(Bucket=cfg["bucket"])
            return {
                "ok": True,
                "message": (
                    f"Successfully connected to S3 bucket '{cfg['bucket']}' at {cfg['endpoint_url']}"
                    if cfg.get("endpoint_url")
                    else f"Successfully connected to AWS S3 bucket '{cfg['bucket']}' in region '{cfg['region']}'"
                ),
                "bucket": cfg["bucket"],
                "region": cfg["region"],
            }
        except Exception as e:
            err_msg = str(e)
            return {
                "ok": False,
                "error": f"Failed to access S3 bucket '{cfg['bucket']}': {err_msg}",
            }

    def upload_document(
        self,
        filename: str,
        content: bytes,
        content_type: Optional[str] = None,
        project_id: Optional[str] = None,
        feature_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads document bytes to AWS S3 bucket.

        Returns metadata dict including s3_key, bucket, region, size_bytes, filename.
        """
        cfg = self._get_config()
        if not cfg["enabled"] or not cfg["bucket"]:
            raise ValueError("AWS S3 document storage is not configured or enabled")

        client = self._get_client(cfg)

        sanitized_filename = re.sub(r"[^a-zA-Z0-9_\.\-]", "_", filename or "unnamed_doc")
        unique_id = uuid.uuid4().hex[:12]
        proj_part = project_id or "global"
        s3_key = f"{cfg['prefix']}/{proj_part}/{unique_id}_{sanitized_filename}"

        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        client.put_object(
            Bucket=cfg["bucket"],
            Key=s3_key,
            Body=content,
            Metadata={
                "original_filename": filename or "doc",
                "project_id": project_id or "",
                "feature_id": feature_id or "",
                "uploaded_at": str(time.time()),
            },
            **extra_args,
        )

        return {
            "s3_key": s3_key,
            "s3_bucket": cfg["bucket"],
            "s3_region": cfg["region"],
            "filename": filename,
            "content_type": content_type or "application/octet-stream",
            "size_bytes": len(content),
            "created_at": time.time(),
        }

    def download_document(
        self, s3_key: str, bucket: Optional[str] = None
    ) -> bytes:
        """Retrieves raw document bytes from AWS S3."""
        cfg = self._get_config()
        b_name = bucket or cfg["bucket"]
        if not b_name:
            raise ValueError("AWS S3 bucket name is required")

        client = self._get_client(cfg)
        resp = client.get_object(Bucket=b_name, Key=s3_key)
        return resp["Body"].read()

    def generate_presigned_url(
        self,
        s3_key: str,
        bucket: Optional[str] = None,
        expires_in: int = 3600,
    ) -> str:
        """Generates a secure presigned URL for direct AWS S3 document download/viewing."""
        cfg = self._get_config()
        b_name = bucket or cfg["bucket"]
        if not b_name:
            raise ValueError("AWS S3 bucket name is required")

        client = self._get_client(cfg)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": b_name, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url

    def delete_document(
        self, s3_key: str, bucket: Optional[str] = None
    ) -> bool:
        """Deletes a document object from AWS S3."""
        cfg = self._get_config()
        b_name = bucket or cfg["bucket"]
        if not b_name:
            return False

        try:
            client = self._get_client(cfg)
            client.delete_object(Bucket=b_name, Key=s3_key)
            return True
        except Exception:
            return False


# Singleton instance
s3_storage = S3StorageManager()
