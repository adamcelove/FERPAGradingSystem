"""Configuration dataclass for Google Drive integration.

This module defines the configuration structure for the Google Drive
integration, including authentication, processing, upload, and rate
limiting settings.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class OAuth2Config:
    """OAuth2 authentication configuration."""

    client_secrets_path: Path = field(default_factory=lambda: Path("client_secrets.json"))
    token_path: Path = field(default_factory=lambda: Path(".gdrive_token.json"))
    scopes: List[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
    ])


@dataclass
class WorkloadIdentityConfig:
    """Workload Identity Federation configuration for GCP deployments."""

    project_id: str = ""
    pool_id: str = ""
    provider_id: str = ""
    service_account_email: str = ""


@dataclass
class AuthConfig:
    """Authentication configuration."""

    method: str = "oauth2"  # "oauth2" or "workload_identity"
    oauth2: OAuth2Config = field(default_factory=OAuth2Config)
    workload_identity: WorkloadIdentityConfig = field(default_factory=WorkloadIdentityConfig)


@dataclass
class ProcessingConfig:
    """Processing configuration for downloads and discovery."""

    max_concurrent_downloads: int = 5
    download_timeout_seconds: int = 60
    discovery_timeout_seconds: int = 120
    max_folder_depth: int = 10


@dataclass
class UploadConfig:
    """Upload configuration."""

    mode: str = "overwrite"  # "overwrite", "version", "skip"
    output_folder_name: str = "pipeline_outputs"
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_100_seconds: int = 900  # Under Google's 1000/100s limit


@dataclass
class DriveConfig:
    """Main configuration for Google Drive integration.

    This dataclass holds all configuration settings for the Google Drive
    integration, including authentication, processing, upload, and rate
    limiting settings.

    Example:
        config = DriveConfig()
        config.auth.method = "oauth2"
        config.processing.max_concurrent_downloads = 10
    """

    auth: AuthConfig = field(default_factory=AuthConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    @classmethod
    def from_dict(cls, data: Dict) -> "DriveConfig":
        """Create a DriveConfig from a dictionary (e.g., from YAML).

        Args:
            data: Dictionary with configuration values.

        Returns:
            DriveConfig instance with values from the dictionary.
        """
        config = cls()

        if "auth" in data:
            auth_data = data["auth"]
            config.auth.method = auth_data.get("method", config.auth.method)

            if "oauth2" in auth_data:
                oauth2_data = auth_data["oauth2"]
                if "client_secrets_path" in oauth2_data:
                    config.auth.oauth2.client_secrets_path = Path(oauth2_data["client_secrets_path"])
                if "token_path" in oauth2_data:
                    config.auth.oauth2.token_path = Path(oauth2_data["token_path"])
                if "scopes" in oauth2_data:
                    config.auth.oauth2.scopes = oauth2_data["scopes"]

            if "workload_identity" in auth_data:
                wif_data = auth_data["workload_identity"]
                config.auth.workload_identity.project_id = wif_data.get("project_id", "")
                config.auth.workload_identity.pool_id = wif_data.get("pool_id", "")
                config.auth.workload_identity.provider_id = wif_data.get("provider_id", "")
                config.auth.workload_identity.service_account_email = wif_data.get(
                    "service_account_email", ""
                )

        if "processing" in data:
            proc_data = data["processing"]
            config.processing.max_concurrent_downloads = proc_data.get(
                "max_concurrent_downloads", config.processing.max_concurrent_downloads
            )
            config.processing.download_timeout_seconds = proc_data.get(
                "download_timeout_seconds", config.processing.download_timeout_seconds
            )
            config.processing.discovery_timeout_seconds = proc_data.get(
                "discovery_timeout_seconds", config.processing.discovery_timeout_seconds
            )
            config.processing.max_folder_depth = proc_data.get(
                "max_folder_depth", config.processing.max_folder_depth
            )

        if "upload" in data:
            upload_data = data["upload"]
            config.upload.mode = upload_data.get("mode", config.upload.mode)
            config.upload.output_folder_name = upload_data.get(
                "output_folder_name", config.upload.output_folder_name
            )
            config.upload.max_retries = upload_data.get("max_retries", config.upload.max_retries)
            config.upload.retry_delay_seconds = upload_data.get(
                "retry_delay_seconds", config.upload.retry_delay_seconds
            )

        if "rate_limit" in data:
            rate_data = data["rate_limit"]
            config.rate_limit.requests_per_100_seconds = rate_data.get(
                "requests_per_100_seconds", config.rate_limit.requests_per_100_seconds
            )

        return config
