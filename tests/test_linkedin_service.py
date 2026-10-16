"""Unit and integration tests for LinkedIn OAuth and publishing workflows."""

from unittest.mock import AsyncMock, patch
import pytest
import httpx
from src.publisher.db.models import Draft, DraftStatus, Project
from src.publisher.services.linkedin_service import (
    LinkedInOAuthService,
    LinkedInPublishingService,
    LinkedInServiceError,
)


def test_generate_code_verifier():
    """Verify code_verifier meets RFC 7636 requirements (URL-safe, 43-128 characters)."""
    verifier = LinkedInOAuthService.generate_code_verifier()
    assert 43 <= len(verifier) <= 128
    # Must contain only unreserved URL characters
    import re
    assert re.match(r"^[A-Za-z0-9_-]+$", verifier) is not None


def test_generate_code_challenge_rfc7636_test_vector():
    """Verify code_challenge derivation against official RFC 7636 & Microsoft Learn test vector."""
    official_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    computed_challenge = LinkedInOAuthService.generate_code_challenge(official_verifier)
    assert computed_challenge == expected_challenge


def test_build_authorization_url():
    """Verify LinkedIn Native PKCE authorization URL format, parameters, and required scopes."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = LinkedInOAuthService.generate_code_challenge(verifier)

    url = LinkedInOAuthService.build_authorization_url(
        client_id="test_client_123",
        redirect_uri="http://127.0.0.1:8000/api/integrations/linkedin/callback",
        state="xyz123state",
        code_challenge=challenge,
    )
    assert "https://www.linkedin.com/oauth/native-pkce/authorization" in url
    assert "client_id=test_client_123" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fintegrations%2Flinkedin%2Fcallback" in url
    assert "state=xyz123state" in url
    assert "w_member_social" in url
    # CRITICAL: Verify openid is NOT in PKCE URL to avoid "Open ID permission is not supported for PKCE flows"
    assert "openid" not in url
    assert "profile" not in url
    assert f"code_challenge={challenge}" in url
    assert "code_challenge_method=S256" in url


def test_build_authorization_url_standard_flow():
    """Verify Standard OAuth authorization URL includes OpenID scopes and uses standard endpoint."""
    url = LinkedInOAuthService.build_authorization_url(
        client_id="test_client_456",
        redirect_uri="http://127.0.0.1:8000/api/integrations/linkedin/callback",
        state="state_std_123",
        use_pkce=False,
    )
    assert "https://www.linkedin.com/oauth/v2/authorization" in url
    assert "client_id=test_client_456" in url
    assert "openid" in url
    assert "profile" in url
    assert "w_member_social" in url
    assert "code_challenge" not in url


@pytest.mark.asyncio
async def test_get_user_profile_fallback_author_urn():
    """Verify fallback author URN works when token only has w_member_social (PKCE flow)."""
    mock_403 = httpx.Response(
        status_code=403,
        json={"error": "ACCESS_DENIED", "message": "Not enough permissions to access: GET /userinfo"},
    )
    with patch("httpx.AsyncClient.get", return_value=mock_403):
        profile = await LinkedInOAuthService.get_user_profile(
            access_token="pkce_token_no_openid",
            fallback_author_urn="urn:li:person:manual_author_123",
        )
        assert profile.sub == "manual_author_123"
        assert profile.author_urn == "urn:li:person:manual_author_123"


@pytest.mark.asyncio
async def test_exchange_code_for_token_pkce_success():
    """Verify Native PKCE token exchange sends code_verifier to LinkedIn."""
    mock_resp = httpx.Response(
        status_code=200,
        headers={"content-type": "application/json"},
        json={"access_token": "mock_pkce_token_123", "expires_in": 5184000},
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        token_data = await LinkedInOAuthService.exchange_code_for_token(
            code="auth_code_xyz",
            client_id="client_789",
            redirect_uri="http://127.0.0.1:8000/api/integrations/linkedin/callback",
            code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        )
        assert token_data["access_token"] == "mock_pkce_token_123"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["data"]["grant_type"] == "authorization_code"
        assert call_kwargs["data"]["code"] == "auth_code_xyz"
        assert call_kwargs["data"]["client_id"] == "client_789"
        assert call_kwargs["data"]["code_verifier"] == "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        assert "client_secret" not in call_kwargs["data"]


@pytest.mark.asyncio
async def test_exchange_code_for_token_pkce_missing_verifier():
    """Verify exchange_code_for_token raises LinkedInServiceError if code_verifier is missing."""
    with pytest.raises(LinkedInServiceError, match="PKCE code_verifier is required"):
        await LinkedInOAuthService.exchange_code_for_token(
            code="code123",
            client_id="client123",
            redirect_uri="http://127.0.0.1:8000/api/integrations/linkedin/callback",
            code_verifier="",
        )


@pytest.mark.asyncio
async def test_exchange_code_for_token_retry_with_client_secret():
    """Verify retry with client_secret if LinkedIn indicates client authentication is needed."""
    first_resp = httpx.Response(
        status_code=401,
        headers={"content-type": "application/json"},
        json={"error": "unauthorized_client", "error_description": "client_secret required"},
    )
    second_resp = httpx.Response(
        status_code=200,
        headers={"content-type": "application/json"},
        json={"access_token": "mock_retry_token_456"},
    )

    with patch("httpx.AsyncClient.post", side_effect=[first_resp, second_resp]) as mock_post:
        token_data = await LinkedInOAuthService.exchange_code_for_token(
            code="auth_code_retry",
            client_id="client_retry",
            redirect_uri="http://127.0.0.1:8000/api/integrations/linkedin/callback",
            code_verifier="test_code_verifier_123456789012345678901234567890",
            client_secret="secret_abc",
        )
        assert token_data["access_token"] == "mock_retry_token_456"
        assert mock_post.call_count == 2
        # First call: no client_secret
        assert "client_secret" not in mock_post.call_args_list[0][1]["data"]
        # Second call: with client_secret
        assert mock_post.call_args_list[1][1]["data"]["client_secret"] == "secret_abc"


@pytest.mark.asyncio
async def test_get_user_profile_mocked():
    """Verify fetching member profile and author URN derivation."""
    mock_resp = httpx.Response(
        status_code=200,
        json={"sub": "abc456sub", "name": "Jane Developer", "email": "jane@example.com"},
    )
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        profile = await LinkedInOAuthService.get_user_profile("mock-token")
        assert profile.sub == "abc456sub"
        assert profile.author_urn == "urn:li:person:abc456sub"
        assert profile.name == "Jane Developer"


@pytest.mark.asyncio
async def test_publishing_blocks_unapproved_draft():
    """Verify publishing is strictly blocked if draft is not in APPROVED state."""
    project = Project(name="TestProj", repo_url="https://github.com/example/test")
    draft = Draft(
        id=1,
        project_id=1,
        body="Draft that is NOT approved yet.",
        status=DraftStatus.GENERATED,
    )

    success, message, err_cat = await LinkedInPublishingService.publish_draft(
        draft=draft,
        project=project,
        access_token="mock-token",
        author_urn="urn:li:person:123",
        submission_id="sub-123",
    )
    assert success is False
    assert err_cat == "ApprovalRequired"
    assert "Explicit human approval is mandatory" in message


@pytest.mark.asyncio
async def test_publishing_approved_draft_success():
    """Verify publishing an approved draft returns the official LinkedIn post URN."""
    project = Project(name="TestProj", repo_url="https://github.com/example/test")
    draft = Draft(
        id=2,
        project_id=1,
        body="Approved post ready for publication. https://github.com/example/test",
        status=DraftStatus.APPROVED,
    )

    mock_resp = httpx.Response(
        status_code=201,
        headers={"x-restli-id": "urn:li:share:987654321"},
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        success, post_urn, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-valid-456",
        )
        assert success is True
        assert post_urn == "urn:li:share:987654321"
        assert err_cat is None


@pytest.mark.asyncio
async def test_publishing_publishing_state_draft_success():
    """Verify publishing is permitted when draft is in PUBLISHING state during the workflow."""
    project = Project(name="TestProj", repo_url="https://github.com/example/test")
    draft = Draft(
        id=3,
        project_id=1,
        body="Approved post currently being published. https://github.com/example/test",
        status=DraftStatus.PUBLISHING,
    )

    mock_resp = httpx.Response(
        status_code=201,
        headers={"x-restli-id": "urn:li:share:1122334455"},
    )

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        success, post_urn, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-valid-789",
        )
        assert success is True
        assert post_urn == "urn:li:share:1122334455"
        assert err_cat is None


def test_linkedin_version_helpers():
    """Verify dynamic active LinkedIn version computation and fallback logic."""
    from src.publisher.core.config import (
        get_current_linkedin_api_version,
        get_fallback_linkedin_api_version,
        settings,
    )

    # Dynamic version format: 6 digits (YYYYMM)
    ver = get_current_linkedin_api_version()
    assert len(ver) == 6
    assert ver.isdigit()

    # Fallback version for YYYYMM
    fallback = get_fallback_linkedin_api_version("202610")
    assert fallback == "202609"

    # January rollover fallback
    jan_fallback = get_fallback_linkedin_api_version("202601")
    assert jan_fallback == "202512"

    # Custom override via settings
    original = settings.LINKEDIN_API_VERSION
    try:
        settings.LINKEDIN_API_VERSION = "202605"
        assert get_current_linkedin_api_version() == "202605"
    finally:
        settings.LINKEDIN_API_VERSION = original


@pytest.mark.asyncio
async def test_publishing_retries_on_426_version_error():
    """Verify publishing retries with fallback version when receiving 426 NONEXISTENT_VERSION."""
    project = Project(name="TestProj", repo_url="https://github.com/example/test")
    draft = Draft(
        id=4,
        project_id=1,
        body="Draft testing 426 upgrade retry.",
        status=DraftStatus.APPROVED,
    )

    resp_426 = httpx.Response(
        status_code=426,
        text='{"status":426,"code":"NONEXISTENT_VERSION","message":"Requested version 20240101 is not active"}',
    )
    resp_201 = httpx.Response(
        status_code=201,
        headers={"x-restli-id": "urn:li:share:retry_success"},
    )

    calls = []

    async def mock_post(url, headers=None, json=None):
        calls.append(headers.get("LinkedIn-Version"))
        if len(calls) == 1:
            return resp_426
        return resp_201

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        success, post_urn, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-426-test",
        )
        assert success is True
        assert post_urn == "urn:li:share:retry_success"
        assert err_cat is None
        assert len(calls) == 2
        # Verify fallback version was attempted on retry
        assert calls[0] != calls[1]


@pytest.mark.asyncio
async def test_publishing_handles_persistent_426():
    """Verify publishing returns VersionUnsupported when 426 persists after retry."""
    project = Project(name="TestProj", repo_url="https://github.com/example/test")
    draft = Draft(
        id=5,
        project_id=1,
        body="Draft testing persistent 426 error.",
        status=DraftStatus.APPROVED,
    )

    resp_426 = httpx.Response(
        status_code=426,
        text='{"status":426,"code":"NONEXISTENT_VERSION","message":"Requested version is not active"}',
    )

    with patch("httpx.AsyncClient.post", return_value=resp_426):
        success, err_msg, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-426-fail",
        )
        assert success is False
        assert err_cat == "VersionUnsupported"
        assert "LinkedIn API version error" in err_msg


@pytest.mark.asyncio
async def test_publishing_with_attached_media_success():
    """Verify publishing attaches media URN to content payload when screenshot_path is set."""
    project = Project(name="Build2Buzz", repo_url="https://github.com/example/repo")
    draft = Draft(
        id=6,
        project_id=1,
        body="Draft with attached media payload.",
        status=DraftStatus.APPROVED,
        screenshot_path="docs/media/build2buzz_preview.gif",
    )

    resp_201 = httpx.Response(
        status_code=201,
        headers={"x-restli-id": "urn:li:share:media_post_123"},
        json={"id": "urn:li:share:media_post_123"},
    )

    posted_payload = {}

    async def mock_post(url, headers=None, json=None):
        nonlocal posted_payload
        posted_payload = json
        return resp_201

    with patch("src.publisher.services.media_service.MediaService.upload_media_to_linkedin", new_callable=AsyncMock) as mock_media, \
         patch("httpx.AsyncClient.post", side_effect=mock_post):
        mock_media.return_value = ("urn:li:image:uploaded_img_789", "image")

        success, post_urn, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-media-test",
        )

        assert success is True
        assert post_urn == "urn:li:share:media_post_123"
        assert err_cat is None
        assert "content" in posted_payload
        assert posted_payload["content"]["media"]["id"] == "urn:li:image:uploaded_img_789"


@pytest.mark.asyncio
async def test_publishing_with_media_upload_failure():
    """Verify publishing fails with MediaUploadFailed when media upload raises an error."""
    project = Project(name="Build2Buzz", repo_url="https://github.com/example/repo")
    draft = Draft(
        id=7,
        project_id=1,
        body="Draft with failing media upload.",
        status=DraftStatus.APPROVED,
        screenshot_path="invalid_path.png",
    )

    with patch("src.publisher.services.media_service.MediaService.upload_media_to_linkedin", new_callable=AsyncMock) as mock_media:
        mock_media.side_effect = ValueError("File corrupted or unreachable")

        success, err_msg, err_cat = await LinkedInPublishingService.publish_draft(
            draft=draft,
            project=project,
            access_token="valid-token",
            author_urn="urn:li:person:123",
            submission_id="sub-media-err",
        )

        assert success is False
        assert err_cat == "MediaUploadFailed"
        assert "Could not upload attached media to LinkedIn" in err_msg



