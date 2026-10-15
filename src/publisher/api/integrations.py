"""API endpoints for managing GitHub, LinkedIn OAuth, and search integrations."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger
from src.publisher.db.connection import get_db
from src.publisher.db.repositories import SettingsRepository
from src.publisher.services.credential_manager import credentials
from src.publisher.services.github_service import GitHubClient
from src.publisher.services.linkedin_service import (
    LinkedInOAuthService,
    LinkedInServiceError,
)

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

# In-memory storage mapping active OAuth state tokens to PKCE code_verifiers
_active_oauth_pkce: dict[str, str] = {}


class SaveGithubTokenRequest(BaseModel):
    token: str


class LinkedInCredentialsRequest(BaseModel):
    client_id: str
    client_secret: str | None = None
    redirect_uri: str | None = None
    flow_type: str = "native_pkce"  # "native_pkce" or "standard"
    author_urn: str | None = None


class SearchSettingsRequest(BaseModel):
    provider: str
    api_key: str | None = None


@router.post("/github/token")
async def save_github_token(req: SaveGithubTokenRequest):
    """Save GitHub Personal Access Token in Windows Credential Manager."""
    if not req.token or not req.token.strip():
        credentials.delete_credential("github_pat")
        return {"status": "success", "message": "GitHub token removed."}

    credentials.set_credential("github_pat", req.token.strip())
    return {"status": "success", "message": "GitHub token saved securely."}


@router.delete("/github/token")
async def delete_github_token():
    """Remove GitHub token from Windows Credential Manager."""
    credentials.delete_credential("github_pat")
    return {"status": "success", "message": "GitHub token removed."}


@router.get("/github/status")
async def get_github_status():
    """Check GitHub PAT status and return masked token."""
    token = credentials.get_credential("github_pat")
    has_token = bool(token and token.strip())
    masked_token = credentials.get_masked_credential("github_pat") if has_token else ""
    return {
        "connected": has_token,
        "has_token": has_token,
        "masked_token": masked_token,
        "auth_type": "Personal Access Token" if has_token else "Public (Unauthenticated)",
    }


@router.post("/github/test")
async def test_github_connection():
    """Test GitHub API access with current token."""
    token = credentials.get_credential("github_pat")
    client = GitHubClient(token=token)
    try:
        # Test query public repo
        info = await client.fetch_repository("https://github.com/octocat/Hello-World")
        return {
            "status": "success",
            "message": f"GitHub API connection verified. {'Authenticated with PAT' if token else 'Public unauthenticated access (60 req/hr)'}.",
            "authenticated": bool(token),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/linkedin/connect")
async def connect_linkedin(req: LinkedInCredentialsRequest):
    """Initiate LinkedIn OAuth flow and return consent redirect URL."""
    if not req.client_id or not req.client_id.strip():
        raise HTTPException(
            status_code=400,
            detail="LinkedIn Client ID is required.",
        )

    # Determine loopback redirect_uri (default or user-specified)
    target_redirect_uri = (
        req.redirect_uri.strip()
        if (req.redirect_uri and req.redirect_uri.strip())
        else settings.LINKEDIN_REDIRECT_URI
    )

    client_id = req.client_id.strip()
    credentials.set_credential("linkedin_client_id", client_id)
    credentials.set_credential("linkedin_redirect_uri", target_redirect_uri)

    if req.client_secret and req.client_secret.strip():
        credentials.set_credential("linkedin_client_secret", req.client_secret.strip())

    if req.author_urn and req.author_urn.strip():
        credentials.set_credential("linkedin_author_urn", req.author_urn.strip())

    state = LinkedInOAuthService.generate_state()
    use_pkce = req.flow_type != "standard"

    if use_pkce:
        code_verifier = LinkedInOAuthService.generate_code_verifier()
        code_challenge = LinkedInOAuthService.generate_code_challenge(code_verifier)
        _active_oauth_pkce[state] = code_verifier
        credentials.set_credential("linkedin_code_verifier", code_verifier)

        auth_url = LinkedInOAuthService.build_authorization_url(
            client_id=client_id,
            redirect_uri=target_redirect_uri,
            state=state,
            code_challenge=code_challenge,
            use_pkce=True,
        )
    else:
        # Standard OAuth flow (OpenID Connect + w_member_social)
        _active_oauth_pkce[state] = ""
        auth_url = LinkedInOAuthService.build_authorization_url(
            client_id=client_id,
            redirect_uri=target_redirect_uri,
            state=state,
            use_pkce=False,
        )

    return {
        "status": "success",
        "authorization_url": auth_url,
        "redirect_uri": target_redirect_uri,
        "state": state,
    }


@router.get("/linkedin/callback")
async def linkedin_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    """Handle OAuth redirect callback from LinkedIn."""
    if error:
        logger.error("LinkedIn OAuth error: %s (%s)", error, error_description)
        return RedirectResponse(url="/?linkedin_error=" + (error_description or error))

    if not code or not state:
        return RedirectResponse(url="/?linkedin_error=Missing+authorization+code+or+state")

    # Match state and retrieve corresponding PKCE code_verifier (if any)
    code_verifier = _active_oauth_pkce.pop(state, None)
    if code_verifier is None and not credentials.get_credential("linkedin_code_verifier"):
        logger.warning("Rejected callback: state token not found or expired: %s", state)
        return RedirectResponse(url="/?linkedin_error=Invalid+or+expired+state+parameter")

    if not code_verifier:
        code_verifier = credentials.get_credential("linkedin_code_verifier")

    client_id = credentials.get_credential("linkedin_client_id") or settings.LINKEDIN_CLIENT_ID
    client_secret = credentials.get_credential("linkedin_client_secret")
    redirect_uri = credentials.get_credential("linkedin_redirect_uri") or settings.LINKEDIN_REDIRECT_URI

    if not client_id:
        return RedirectResponse(url="/?linkedin_error=Missing+stored+client+credentials")

    try:
        token_data = await LinkedInOAuthService.exchange_code_for_token(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier if code_verifier else None,
            client_secret=client_secret,
        )
        access_token = token_data.get("access_token")
        if access_token:
            credentials.set_credential("linkedin_access_token", access_token)
            credentials.delete_credential("linkedin_code_verifier")
            logger.info("LinkedIn OAuth flow completed successfully.")
            return RedirectResponse(url="/?linkedin_success=1")
        else:
            return RedirectResponse(url="/?linkedin_error=No+access+token+in+response")
    except LinkedInServiceError as exc:
        logger.error("LinkedIn token exchange error: %s", exc.message)
        return RedirectResponse(url=f"/?linkedin_error={exc.message}")


class LinkedInAuthorUrnRequest(BaseModel):
    author_urn: str


@router.get("/linkedin/status")
async def get_linkedin_status():
    """Check LinkedIn connection status without exposing tokens."""
    token = credentials.get_credential("linkedin_access_token")
    stored_client_id = credentials.get_credential("linkedin_client_id") or ""
    stored_author_urn = credentials.get_credential("linkedin_author_urn") or ""

    if not token:
        return {
            "connected": False,
            "member_name": None,
            "author_urn": stored_author_urn,
            "client_id": stored_client_id,
        }

    try:
        profile = await LinkedInOAuthService.get_user_profile(token, fallback_author_urn=stored_author_urn)
        return {
            "connected": True,
            "member_name": profile.name,
            "author_urn": profile.author_urn,
            "client_id": stored_client_id,
        }
    except LinkedInServiceError as exc:
        if exc.status_code == 401:
            return {
                "connected": False,
                "member_name": None,
                "author_urn": stored_author_urn,
                "client_id": stored_client_id,
                "error": exc.message,
            }
        return {
            "connected": True,
            "member_name": "Connected Member (Native PKCE)",
            "author_urn": stored_author_urn or "urn:li:person:connected",
            "client_id": stored_client_id,
            "note": exc.message,
        }
    except Exception as exc:
        return {
            "connected": True,
            "member_name": "Connected Member",
            "author_urn": stored_author_urn or "urn:li:person:connected",
            "client_id": stored_client_id,
            "warning": str(exc),
        }


@router.post("/linkedin/author-urn")
async def save_linkedin_author_urn(req: LinkedInAuthorUrnRequest):
    """Save or update LinkedIn Author Person URN."""
    clean_urn = req.author_urn.strip() if req.author_urn else ""
    if clean_urn:
        if not clean_urn.startswith("urn:li:person:") and not clean_urn.startswith("urn:li:organization:"):
            clean_urn = f"urn:li:person:{clean_urn}"
        credentials.set_credential("linkedin_author_urn", clean_urn)
        return {"status": "success", "message": f"LinkedIn Author URN set to '{clean_urn}'.", "author_urn": clean_urn}
    else:
        credentials.delete_credential("linkedin_author_urn")
        return {"status": "success", "message": "LinkedIn Author URN cleared.", "author_urn": ""}



@router.post("/linkedin/disconnect")
async def disconnect_linkedin():
    """Revoke local LinkedIn tokens."""
    credentials.delete_credential("linkedin_access_token")
    credentials.delete_credential("linkedin_refresh_token")
    credentials.delete_credential("linkedin_client_secret")
    credentials.delete_credential("linkedin_code_verifier")
    return {"status": "success", "message": "LinkedIn credentials removed."}


@router.post("/search/settings")
async def save_search_settings(
    req: SearchSettingsRequest, db: Session = Depends(get_db)
):
    """Save search provider preference and API key."""
    if req.api_key:
        credentials.set_credential("search_api_key", req.api_key.strip())

    repo = SettingsRepository(db)
    rec = repo.get_or_create()
    rec.preferences["search_provider"] = req.provider
    db.commit()
    return {"status": "success", "provider": req.provider}
