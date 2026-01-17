"""Google Drive authentication for the FERPA feedback pipeline.

This module provides authentication strategies for the Google Drive API:
- OAuth2Authenticator: For local development with user consent flow
- WorkloadIdentityAuthenticator: For production GCP deployments (Phase 2)

Example:
    from ferpa_feedback.gdrive.auth import OAuth2Authenticator, create_authenticator

    # For development
    auth = OAuth2Authenticator(
        client_secrets_path=Path("client_secrets.json"),
        token_path=Path(".gdrive_token.json"),
    )
    service = auth.get_service()

    # Or use factory function
    auth = create_authenticator(config)
    service = auth.get_service()
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Protocol

from googleapiclient.discovery import Resource, build

from ferpa_feedback.gdrive.config import DriveConfig
from ferpa_feedback.gdrive.errors import AuthenticationError

# Google Drive API version
DRIVE_API_VERSION = "v3"
DRIVE_API_SERVICE = "drive"

# Default scopes for Drive access
DEFAULT_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


class DriveAuthenticator(Protocol):
    """Protocol for Drive authentication strategies.

    This protocol defines the interface that all authentication strategies
    must implement. Use this for type hints when accepting any authenticator.
    """

    def get_service(self) -> Resource:
        """Return authenticated Drive API service.

        Returns:
            Authenticated googleapiclient Resource for Drive API.

        Raises:
            AuthenticationError: If authentication fails.
        """
        ...

    @property
    def service_account_email(self) -> str:
        """Return the service account email for sharing instructions.

        For OAuth2, this returns the authenticated user's email.
        For service accounts/WIF, this returns the SA email.

        Returns:
            Email address to share folders with.
        """
        ...


class OAuth2Authenticator:
    """Development authenticator using OAuth2 flow.

    This authenticator uses the installed application OAuth2 flow, which
    requires user interaction on first run to authorize the application.
    Tokens are cached locally for subsequent runs.

    Attributes:
        client_secrets_path: Path to the OAuth2 client secrets JSON file.
        token_path: Path where the access/refresh tokens will be stored.
        scopes: List of OAuth2 scopes to request.
    """

    def __init__(
        self,
        client_secrets_path: Path,
        token_path: Optional[Path] = None,
        scopes: Optional[List[str]] = None,
    ) -> None:
        """Initialize OAuth2 authenticator.

        Args:
            client_secrets_path: Path to OAuth2 client secrets JSON file.
                Download this from Google Cloud Console.
            token_path: Path to store/load refresh token. Defaults to
                .gdrive_token.json in the same directory as client_secrets.
            scopes: OAuth2 scopes to request. Defaults to drive.readonly
                and drive.file.
        """
        self._client_secrets_path = Path(client_secrets_path)
        self._token_path = token_path or self._client_secrets_path.parent / ".gdrive_token.json"
        self._scopes = scopes or DEFAULT_SCOPES.copy()
        self._service: Optional[Resource] = None
        self._credentials: Optional[Any] = None
        self._user_email: Optional[str] = None

    def get_service(self) -> Resource:
        """Return authenticated Drive API service.

        On first call, this will:
        1. Check for existing valid token
        2. Refresh expired token if refresh token exists
        3. Run OAuth2 flow if no valid credentials

        Returns:
            Authenticated googleapiclient Resource for Drive API.

        Raises:
            AuthenticationError: If authentication fails or is cancelled.
        """
        if self._service is not None and self._credentials is not None:
            # Check if credentials need refresh
            if hasattr(self._credentials, "expired") and self._credentials.expired:
                self._refresh_credentials()
            return self._service

        self._authenticate()
        return self._service

    def _authenticate(self) -> None:
        """Perform OAuth2 authentication flow."""
        # Import here to avoid loading Google auth libraries until needed
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        creds: Optional[Credentials] = None

        # Check for existing token
        if self._token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                    str(self._token_path), self._scopes
                )
            except Exception:
                # Token file is invalid, will re-authenticate
                creds = None

        # If no valid credentials, authenticate
        if creds is None or not creds.valid:
            if creds is not None and creds.expired and creds.refresh_token:
                # Refresh the token
                try:
                    creds.refresh(Request())  # type: ignore[no-untyped-call]
                except Exception as e:
                    raise AuthenticationError(
                        f"Failed to refresh OAuth2 token: {e}",
                        auth_method="oauth2",
                    ) from e
            else:
                # Run the OAuth2 flow
                if not self._client_secrets_path.exists():
                    raise AuthenticationError(
                        f"Client secrets file not found: {self._client_secrets_path}. "
                        "Download from Google Cloud Console.",
                        auth_method="oauth2",
                    )

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self._client_secrets_path), self._scopes
                    )
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    raise AuthenticationError(
                        f"OAuth2 flow failed: {e}",
                        auth_method="oauth2",
                    ) from e

            # Save the credentials for next run
            try:
                self._token_path.parent.mkdir(parents=True, exist_ok=True)
                self._token_path.write_text(creds.to_json())
            except Exception:
                # Non-fatal: we have valid creds, just can't cache them
                pass

        self._credentials = creds

        # Build the service
        try:
            self._service = build(
                DRIVE_API_SERVICE,
                DRIVE_API_VERSION,
                credentials=creds,
            )
        except Exception as e:
            raise AuthenticationError(
                f"Failed to build Drive API service: {e}",
                auth_method="oauth2",
            ) from e

        # Get user email for sharing instructions
        self._fetch_user_email()

    def _refresh_credentials(self) -> None:
        """Refresh expired credentials."""
        from google.auth.transport.requests import Request

        if self._credentials is None:
            self._authenticate()
            return

        try:
            self._credentials.refresh(Request())  # type: ignore[no-untyped-call]
            # Update cached token
            self._token_path.write_text(self._credentials.to_json())
        except Exception:
            # Re-authenticate if refresh fails
            self._credentials = None
            self._service = None
            self._authenticate()

    def _fetch_user_email(self) -> None:
        """Fetch the authenticated user's email address."""
        if self._service is None:
            return

        try:
            about = self._service.about().get(fields="user").execute()
            self._user_email = about.get("user", {}).get("emailAddress", "")
        except Exception:
            # Non-fatal: email is for display purposes
            self._user_email = "unknown"

    @property
    def service_account_email(self) -> str:
        """Return the authenticated user's email for sharing instructions.

        For OAuth2, this returns the user's Google account email.
        Share folders with this email to grant access.

        Returns:
            Email address of the authenticated user.
        """
        if self._user_email is None:
            if self._service is None:
                return "Not authenticated - call get_service() first"
            self._fetch_user_email()
        return self._user_email or "unknown"


def create_authenticator(
    config: Optional[DriveConfig] = None,
) -> DriveAuthenticator:
    """Factory function to create appropriate authenticator.

    Detects environment and returns:
    - WorkloadIdentityAuthenticator in Cloud Run (K_SERVICE env var present)
    - OAuth2Authenticator for local development

    Args:
        config: Optional DriveConfig with authentication settings.
            If not provided, uses sensible defaults.

    Returns:
        Appropriate DriveAuthenticator implementation.

    Raises:
        AuthenticationError: If configuration is invalid.
    """
    # Check if running in Cloud Run
    is_cloud_run = os.environ.get("K_SERVICE") is not None

    if config is None:
        config = DriveConfig()

    # For POC, only OAuth2 is implemented
    # WIF will be added in Phase 2
    if is_cloud_run and config.auth.method == "workload_identity":
        # TODO: Implement WorkloadIdentityAuthenticator in Phase 2
        raise AuthenticationError(
            "Workload Identity Federation not yet implemented. "
            "Use OAuth2 for development or wait for Phase 2.",
            auth_method="workload_identity",
        )

    # Default to OAuth2
    oauth2_config = config.auth.oauth2
    return OAuth2Authenticator(
        client_secrets_path=oauth2_config.client_secrets_path,
        token_path=oauth2_config.token_path,
        scopes=oauth2_config.scopes,
    )
