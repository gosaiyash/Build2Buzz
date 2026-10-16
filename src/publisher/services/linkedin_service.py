"""Official LinkedIn OAuth 2.0 authorization and Posts API publishing service."""

import base64
from datetime import datetime, timezone
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import quote, urlencode
import httpx
from pydantic import BaseModel
from src.publisher.core.config import (
    get_current_linkedin_api_version,
    get_fallback_linkedin_api_version,
)
from src.publisher.core.logging_config import logger
from src.publisher.db.models import Draft, DraftStatus, Project


class LinkedInUserProfile(BaseModel):
    """Authenticated LinkedIn user profile details."""

    sub: str
    name: str
    email: str | None = None
    picture: str | None = None
    author_urn: str  # Format: "urn:li:person:{sub}"


class LinkedInServiceError(Exception):
    """Custom exception with actionable LinkedIn troubleshooting details."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class LinkedInOAuthService:
    """Manages official OAuth 2.0 Native PKCE and Standard authorization flows for LinkedIn API."""

    NATIVE_AUTH_URL = "https://www.linkedin.com/oauth/native-pkce/authorization"
    STANDARD_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
    AUTH_URL = NATIVE_AUTH_URL

    TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
    USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

    # NOTE: LinkedIn strictly forbids OpenID permissions ("openid", "profile") on PKCE flows.
    # PKCE flows only accept standard Member permissions such as "w_member_social".
    PKCE_SCOPES = ["w_member_social"]
    STANDARD_SCOPES = ["openid", "profile", "w_member_social"]
    REQUIRED_SCOPES = PKCE_SCOPES

    @classmethod
    def generate_state(cls) -> str:
        """Generate a cryptographically secure state token to prevent CSRF."""
        return secrets.token_urlsafe(32)

    @classmethod
    def generate_code_verifier(cls) -> str:
        """Generate an RFC 7636 compliant cryptographic code verifier (43-128 chars)."""
        # secrets.token_urlsafe(64) produces 86 URL-safe characters, well within [43, 128]
        return secrets.token_urlsafe(64)

    @classmethod
    def generate_code_challenge(cls, code_verifier: str) -> str:
        """Derive the S256 code challenge from the code verifier (Base64URL without padding)."""
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    @classmethod
    def build_authorization_url(
        cls,
        client_id: str,
        redirect_uri: str,
        state: str,
        code_challenge: str | None = None,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
    ) -> str:
        """Build the official LinkedIn authorization consent URL."""
        if not client_id:
            raise LinkedInServiceError("LinkedIn Client ID is missing. Please configure it in Integrations.")

        if use_pkce:
            if not code_challenge:
                raise LinkedInServiceError("PKCE code challenge is required for Native OAuth.")
            # For PKCE, OpenID permissions (openid, profile) are rejected by LinkedIn.
            # Only member permissions (w_member_social) are permitted.
            active_scopes = scopes or cls.PKCE_SCOPES
            auth_endpoint = cls.NATIVE_AUTH_URL
            params: dict[str, str] = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": " ".join(active_scopes),
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        else:
            active_scopes = scopes or cls.STANDARD_SCOPES
            auth_endpoint = cls.STANDARD_AUTH_URL
            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": " ".join(active_scopes),
            }

        return f"{auth_endpoint}?{urlencode(params, quote_via=quote)}"

    @classmethod
    async def exchange_code_for_token(
        cls,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        client_secret: str | None = None,
    ) -> dict[str, Any]:
        """Exchange authorization code for an OAuth access token."""
        if not code_verifier and not client_secret:
            raise LinkedInServiceError("PKCE code_verifier is required when client_secret is not provided.")

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        elif client_secret:
            data["client_secret"] = client_secret

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Exchanging LinkedIn authorization code for access token...")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(cls.TOKEN_URL, data=data, headers=headers)

                # Retry with client_secret if missing from native request but required
                if (
                    res.status_code != 200
                    and client_secret
                    and "client_secret" not in data
                    and ("client_secret" in res.text.lower() or "unauthorized_client" in res.text.lower())
                ):
                    logger.info("Retrying LinkedIn token exchange with client_secret included...")
                    retry_data = dict(data)
                    retry_data["client_secret"] = client_secret
                    res = await client.post(cls.TOKEN_URL, data=retry_data, headers=headers)

                if res.status_code != 200:
                    err_json = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    err_desc = err_json.get("error_description", res.text[:200])
                    raise LinkedInServiceError(
                        f"LinkedIn token exchange failed ({res.status_code}): {err_desc}",
                        status_code=res.status_code,
                    )
                return res.json()
        except httpx.RequestError as exc:
            raise LinkedInServiceError(f"Network error communicating with LinkedIn: {exc}")

    @classmethod
    async def get_user_profile(
        cls,
        access_token: str,
        fallback_author_urn: str | None = None,
    ) -> LinkedInUserProfile:
        """Fetch the authenticated member's profile and construct person URN."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Build2Buzz/1.0",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Try OpenID userinfo endpoint (available when openid scope was granted)
                res = await client.get(cls.USERINFO_URL, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    sub = data.get("sub")
                    if sub:
                        return LinkedInUserProfile(
                            sub=sub,
                            name=data.get("name", "LinkedIn Member"),
                            email=data.get("email"),
                            picture=data.get("picture"),
                            author_urn=f"urn:li:person:{sub}",
                        )

                # 2. Try legacy /v2/me endpoint (available if r_liteprofile was granted)
                res_me = await client.get("https://api.linkedin.com/v2/me", headers=headers)
                if res_me.status_code == 200:
                    data_me = res_me.json()
                    person_id = data_me.get("id")
                    if person_id:
                        fname = data_me.get("localizedFirstName", "")
                        lname = data_me.get("localizedLastName", "")
                        full_name = f"{fname} {lname}".strip() or "LinkedIn Member"
                        return LinkedInUserProfile(
                            sub=person_id,
                            name=full_name,
                            author_urn=f"urn:li:person:{person_id}",
                        )

                # 3. If token only has w_member_social (PKCE flow without OpenID),
                # use stored author URN if provided or saved in credentials
                if fallback_author_urn:
                    clean_urn = fallback_author_urn.strip()
                    if not clean_urn.startswith("urn:li:person:") and not clean_urn.startswith("urn:li:organization:"):
                        clean_urn = f"urn:li:person:{clean_urn}"
                    sub_val = clean_urn.split(":")[-1]
                    return LinkedInUserProfile(
                        sub=sub_val,
                        name="Authenticated LinkedIn Publisher (PKCE)",
                        author_urn=clean_urn,
                    )

                if res.status_code == 401:
                    raise LinkedInServiceError("LinkedIn access token is invalid or expired.", status_code=401)

                # Return valid connected profile for PKCE flow where OpenID was excluded
                return LinkedInUserProfile(
                    sub="connected",
                    name="Connected LinkedIn Member (PKCE)",
                    author_urn="urn:li:person:connected",
                )
        except httpx.RequestError as exc:
            raise LinkedInServiceError(f"Network error querying LinkedIn userinfo: {exc}")


class LinkedInPublishingService:
    """Service publishing approved drafts using LinkedIn's official REST API."""

    POSTS_API_URL = "https://api.linkedin.com/rest/posts"
    API_VERSION: str | None = None

    @classmethod
    def get_api_version(cls) -> str:
        """Resolve active LinkedIn API version."""
        if cls.API_VERSION:
            return cls.API_VERSION
        return get_current_linkedin_api_version()

    @classmethod
    async def publish_draft(
        cls,
        draft: Draft,
        project: Project,
        access_token: str,
        author_urn: str,
        submission_id: str,
    ) -> tuple[bool, str, str | None]:
        """Publish an approved draft to LinkedIn.

        Enforces:
        - Strict human approval check: Draft MUST be in APPROVED state.
        - Non-empty body.
        - Official LinkedIn REST Posts schema.
        - Returns (success, linkedin_post_id_or_error, error_category).
        """
        # Invariant 1: Approval check
        if draft.status not in (DraftStatus.APPROVED, DraftStatus.PUBLISHING):
            return (
                False,
                f"Publishing blocked: Draft #{draft.id} is in '{draft.status.value}' state. "
                "Explicit human approval is mandatory before publishing.",
                "ApprovalRequired",
            )

        if not access_token:
            return (
                False,
                "LinkedIn access token is missing. Please connect your LinkedIn account in Integrations.",
                "Unauthenticated",
            )

        if not author_urn or author_urn == "urn:li:person:connected":
            return (
                False,
                "LinkedIn publishing requires your Author Person URN (e.g. 'urn:li:person:abcdef' or your Member ID). "
                "Please configure it in the Integrations tab before publishing.",
                "AuthorUrnRequired",
            )

        # Invariant 2: Construct official payload
        body_text = draft.body.strip()
        payload: dict[str, Any] = {
            "author": author_urn,
            "commentary": body_text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        # Media Upload (Image, GIF, Video, or Multi-Image)
        meta = draft.post_metadata or {}
        media_paths: list[str] = meta.get("media_paths") or ([draft.screenshot_path] if draft.screenshot_path else [])
        if media_paths:
            try:
                from src.publisher.services.media_service import MediaService

                resolved_items = []
                for m_path in media_paths:
                    p, is_vid, mime = await MediaService.resolve_media_file(m_path)
                    resolved_items.append((m_path, p, is_vid, mime))

                # If 1 item or any item is a video:
                if len(resolved_items) == 1 or any(item[2] for item in resolved_items):
                    target_item = next((item for item in resolved_items if item[2]), resolved_items[0])
                    media_urn, media_type = await MediaService.upload_media_to_linkedin(
                        file_path_or_url=target_item[0],
                        access_token=access_token,
                        author_urn=author_urn,
                    )
                    payload["content"] = {
                        "media": {
                            "id": media_urn,
                            "title": project.name,
                        }
                    }
                    logger.info(
                        "Attached single %s (%s) to LinkedIn post payload for Draft #%d",
                        media_type,
                        media_urn,
                        draft.id,
                    )
                else:
                    # Multi-image: 2 to 20 images uploaded in exact specified sequence
                    uploaded_images = []
                    for target_path, _, _, _ in resolved_items[:20]:
                        img_urn = await MediaService.upload_image_to_linkedin(
                            file_path=target_path,
                            access_token=access_token,
                            author_urn=author_urn,
                        )
                        uploaded_images.append({
                            "id": img_urn,
                            "altText": project.name,
                        })

                    payload["content"] = {
                        "multiImage": {
                            "images": uploaded_images,
                        }
                    }
                    logger.info(
                        "Attached multiImage (%d images in sequence) to LinkedIn post payload for Draft #%d",
                        len(uploaded_images),
                        draft.id,
                    )
            except Exception as media_err:
                logger.error("Could not upload attached media to LinkedIn: %s", media_err)
                return (
                    False,
                    f"Publishing failed: Could not upload attached media to LinkedIn ({media_err}). "
                    "Please check the media format or detach media in the editor to publish text-only.",
                    "MediaUploadFailed",
                )

        active_version = cls.get_api_version()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": active_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
            "User-Agent": "Build2Buzz/1.0",
            "X-RestLi-Idempotency-Key": submission_id,
        }

        logger.info(
            "Submitting LinkedIn post for Draft #%d (Submission: %s, Author: %s, Version: %s)",
            draft.id,
            submission_id,
            author_urn,
            active_version,
        )

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(cls.POSTS_API_URL, headers=headers, json=payload)

                # Fallback on 426 (NONEXISTENT_VERSION): retry once with adjacent fallback active version
                if res.status_code == 426:
                    fallback_version = get_fallback_linkedin_api_version(active_version)
                    if fallback_version != active_version:
                        logger.warning(
                            "LinkedIn API version '%s' returned 426 (%s). Retrying with fallback version '%s'...",
                            active_version,
                            res.text[:120],
                            fallback_version,
                        )
                        headers["LinkedIn-Version"] = fallback_version
                        res = await client.post(cls.POSTS_API_URL, headers=headers, json=payload)

                # LinkedIn REST Posts API returns 201 Created on success
                if res.status_code == 201:
                    # Identifier is typically returned in x-restli-id header
                    post_urn = res.headers.get("x-restli-id") or res.headers.get("x-linkedin-id")
                    if not post_urn:
                        try:
                            data = res.json()
                            post_urn = data.get("id")
                        except Exception:
                            post_urn = f"urn:li:share:published_{submission_id[:8]}"

                    logger.info("Successfully published LinkedIn post: %s", post_urn)
                    return True, post_urn, None

                elif res.status_code == 401:
                    logger.error("LinkedIn publishing rejected: Token unauthorized or expired.")
                    return False, "LinkedIn access token expired or revoked. Please reconnect.", "Unauthorized"

                elif res.status_code == 403:
                    logger.error("LinkedIn publishing rejected: Missing 'w_member_social' permission.")
                    return (
                        False,
                        "Permission denied. Ensure your LinkedIn Developer app has 'Share on LinkedIn' (w_member_social) enabled.",
                        "PermissionDenied",
                    )

                elif res.status_code == 426:
                    logger.error("LinkedIn API version unsupported: %s", res.text[:200])
                    return (
                        False,
                        f"LinkedIn API version error: The requested API version is not active. Response: {res.text[:200]}",
                        "VersionUnsupported",
                    )

                elif res.status_code == 429:
                    logger.error("LinkedIn rate limit exceeded.")
                    return False, "LinkedIn API rate limit reached. Please wait before retrying.", "RateLimited"

                else:
                    err_msg = f"LinkedIn API returned status {res.status_code}: {res.text[:200]}"
                    logger.error(err_msg)
                    return False, err_msg, "APIError"

        except httpx.TimeoutException:
            logger.error("Publishing request timed out.")
            return (
                False,
                "Connection to LinkedIn API timed out. The draft has NOT been marked as published.",
                "NetworkTimeout",
            )
        except Exception as exc:
            logger.error("Unexpected error publishing to LinkedIn: %s", exc)
            return False, f"Unexpected publishing error: {str(exc)}", "InternalError"
