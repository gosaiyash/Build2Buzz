"""Comprehensive end-to-end API integration tests covering the complete publisher workflow."""

import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from starlette.testclient import TestClient
from src.publisher.db.connection import Base, get_engine
from src.publisher.main import app
from src.publisher.services.github_service import GitHubRepoInfo


@pytest.fixture
def api_client():
    """Test client using in-memory SQLite database."""
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        yield client


def test_settings_api_flow(api_client: TestClient):
    """Verify settings retrieval, updates, and masked display."""
    # GET settings
    res = api_client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["active_mode"] in {"cloud", "local"}

    # PUT settings
    put_res = api_client.put(
        "/api/settings/llm",
        json={
            "mode": "cloud",
            "cloud_provider": "openai",
            "cloud_model": "gpt-4o-mini",
            "cloud_api_key": "sk-mock-key-12345",
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "success"

    # Verify secret is never returned in plaintext
    get_res = api_client.get("/api/settings")
    assert get_res.json()["has_cloud_api_key"] is True
    assert "sk-mock-key-12345" not in get_res.json()["masked_cloud_api_key"]
    assert "•" in get_res.json()["masked_cloud_api_key"]


def test_complete_end_to_end_project_workflow(api_client: TestClient):
    """End-to-end integration test: Analyze -> Generate Draft -> Edit -> Validate -> Approve -> Publish."""
    # 1. Mock GitHub API and Demo Inspector
    mock_repo_info = GitHubRepoInfo(
        owner="testuser",
        repo="ai-publisher",
        full_name="testuser/ai-publisher",
        description="Autonomous LinkedIn publisher for developers",
        html_url="https://github.com/testuser/ai-publisher",
        language="Python",
        topics=["ai", "fastapi"],
        has_readme=True,
        readme_content="# AI Publisher\n## Features\n- Automated evidence aggregation\n- Human approval workflow",
    )

    with patch("src.publisher.services.github_service.GitHubClient.fetch_repository", new_callable=AsyncMock, return_value=mock_repo_info):
        analyze_res = api_client.post(
            "/api/projects/analyze",
            json={
                "repo_url": "https://github.com/testuser/ai-publisher",
                "demo_url": None,
                "user_notes": "Built to automate technical branding",
            },
        )
        assert analyze_res.status_code == 200
        proj_data = analyze_res.json()
        project_id = proj_data["project_id"]
        assert proj_data["name"] == "ai-publisher"

    # 2. List Projects
    list_res = api_client.get("/api/projects")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Generate Draft with Mocked AI response
    from src.publisher.services.ai.base import GeneratedDraftOutput
    mock_ai_output = GeneratedDraftOutput(
        post_text="Excited to share AI Publisher! Built with Python & FastAPI. Check it out: https://github.com/testuser/ai-publisher",
        hashtags=["#Python", "#AI"],
        project_links=["https://github.com/testuser/ai-publisher"],
        evidence_references=["README: Automated evidence aggregation"],
    )

    with patch("src.publisher.services.ai.cloud_provider.CloudAPIProvider.generate_linkedin_draft", new_callable=AsyncMock, return_value=mock_ai_output):
        draft_res = api_client.post(
            f"/api/projects/{project_id}/drafts",
            json={"style": "developer"},
        )
        assert draft_res.status_code == 200
        draft_data = draft_res.json()
        draft_id = draft_data["draft_id"]
        assert draft_data["state"] == "GENERATED"
        assert "Excited to share AI Publisher" in draft_data["body"]

    # 4. Attempt to publish before approval MUST BE BLOCKED
    publish_premature = api_client.post(f"/api/drafts/{draft_id}/publish")
    assert publish_premature.status_code == 400
    assert "Explicit approval is required" in publish_premature.json()["detail"]

    # 5. Validate Draft
    val_res = api_client.post(f"/api/drafts/{draft_id}/validate")
    assert val_res.status_code == 200
    assert val_res.json()["is_valid"] is True

    # 6. Edit Draft
    edit_res = api_client.put(
        f"/api/drafts/{draft_id}",
        json={"body": "Refined post text: Check out https://github.com/testuser/ai-publisher for details."},
    )
    assert edit_res.status_code == 200

    # 7. Approve Draft
    approve_res = api_client.post(f"/api/drafts/{draft_id}/approve")
    assert approve_res.status_code == 200
    assert "APPROVED" in approve_res.json()["message"]

    # 8. Publish Draft with Mocked LinkedIn API
    from src.publisher.services.linkedin_service import LinkedInUserProfile
    mock_profile = LinkedInUserProfile(
        sub="mock-sub-123",
        name="Test Engineer",
        author_urn="urn:li:person:mock-sub-123",
    )

    with patch("src.publisher.services.credential_manager.credentials.get_credential", return_value="mock-token"), \
         patch("src.publisher.services.linkedin_service.LinkedInOAuthService.get_user_profile", new_callable=AsyncMock, return_value=mock_profile), \
         patch("src.publisher.services.linkedin_service.LinkedInPublishingService.publish_draft", new_callable=AsyncMock, return_value=(True, "urn:li:share:11223344", None)):
        
        pub_res = api_client.post(f"/api/drafts/{draft_id}/publish")
        assert pub_res.status_code == 200
        pub_data = pub_res.json()
        assert pub_data["status"] == "success"
        assert pub_data["linkedin_post_id"] == "urn:li:share:11223344"

    # 9. Verify History
    hist_res = api_client.get("/api/history")
    assert hist_res.status_code == 200
    history_items = hist_res.json()
    assert len(history_items) >= 1
    assert any(h["linkedin_post_id"] == "urn:li:share:11223344" for h in history_items)


def test_linkedin_oauth_pkce_api_flow(api_client: TestClient):
    """Verify LinkedIn Native OAuth 2.0 PKCE connect, authorization URL, and callback flow."""
    # 1. Initiate Connect
    connect_res = api_client.post(
        "/api/integrations/linkedin/connect",
        json={
            "client_id": "test_app_pkce_client",
            "redirect_uri": "http://127.0.0.1:8000/api/integrations/linkedin/callback",
        },
    )
    assert connect_res.status_code == 200
    connect_data = connect_res.json()
    assert connect_data["status"] == "success"
    auth_url = connect_data["authorization_url"]
    state = connect_data["state"]

    # Invariants for Native PKCE
    assert "https://www.linkedin.com/oauth/native-pkce/authorization" in auth_url
    assert "client_id=test_app_pkce_client" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert "w_member_social" in auth_url
    assert "openid" not in auth_url
    assert f"state={state}" in auth_url

    # 2. Mock Token Exchange and Callback
    mock_token_data = {"access_token": "pkce_mock_access_token_999", "expires_in": 5184000}
    with patch(
        "src.publisher.services.linkedin_service.LinkedInOAuthService.exchange_code_for_token",
        new_callable=AsyncMock,
        return_value=mock_token_data,
    ) as mock_exchange:
        callback_res = api_client.get(
            f"/api/integrations/linkedin/callback?code=mock_code_123&state={state}",
            follow_redirects=False,
        )
        assert callback_res.status_code == 307
        assert callback_res.headers["location"] == "/?linkedin_success=1"
        mock_exchange.assert_called_once()
        call_kwargs = mock_exchange.call_args[1]
        assert call_kwargs["code"] == "mock_code_123"
        assert call_kwargs["client_id"] == "test_app_pkce_client"
        assert len(call_kwargs["code_verifier"]) >= 43


def test_linkedin_standard_oauth_api_flow(api_client: TestClient):
    """Verify LinkedIn Standard OAuth flow generates standard authorization URL with OpenID scopes."""
    connect_res = api_client.post(
        "/api/integrations/linkedin/connect",
        json={
            "client_id": "test_app_standard_client",
            "client_secret": "test_secret_xyz",
            "redirect_uri": "http://127.0.0.1:8000/api/integrations/linkedin/callback",
            "flow_type": "standard",
        },
    )
    assert connect_res.status_code == 200
    connect_data = connect_res.json()
    auth_url = connect_data["authorization_url"]
    assert "https://www.linkedin.com/oauth/v2/authorization" in auth_url
    assert "client_id=test_app_standard_client" in auth_url
    assert "openid" in auth_url
    assert "profile" in auth_url
    assert "w_member_social" in auth_url
    assert "code_challenge" not in auth_url


def test_github_status_endpoints(api_client: TestClient):
    """Verify /api/integrations/github/status returns accurate masked token and connection state."""
    # 1. Save GitHub PAT
    save_res = api_client.post("/api/integrations/github/token", json={"token": "ghp_abcdef1234567890xyz"})
    assert save_res.status_code == 200

    # 2. Check status
    stat_res = api_client.get("/api/integrations/github/status")
    assert stat_res.status_code == 200
    stat_data = stat_res.json()
    assert stat_data["connected"] is True
    assert stat_data["has_token"] is True
    assert "0xyz" in stat_data["masked_token"]
    assert "ghp_abcdef" not in stat_data["masked_token"]

    # 3. Delete PAT
    del_res = api_client.delete("/api/integrations/github/token")
    assert del_res.status_code == 200

    # 4. Check status again
    stat_res2 = api_client.get("/api/integrations/github/status")
    assert stat_res2.status_code == 200
    assert stat_res2.json()["connected"] is False
    assert stat_res2.json()["has_token"] is False


def test_linkedin_status_pkce_connected_without_openid(api_client: TestClient):
    """Verify LinkedIn status shows connected even when PKCE excludes OpenID permissions."""
    from src.publisher.services.credential_manager import credentials

    credentials.set_credential("linkedin_access_token", "mock_pkce_member_token")
    credentials.set_credential("linkedin_client_id", "client_pkce_123")

    try:
        # Mock userinfo returning 403 Forbidden (normal for PKCE flow with only w_member_social)
        mock_403 = httpx.Response(status_code=403, json={"error": "ACCESS_DENIED"})
        with patch("httpx.AsyncClient.get", return_value=mock_403):
            res = api_client.get("/api/integrations/linkedin/status")
            assert res.status_code == 200
            data = res.json()
            assert data["connected"] is True
            assert "PKCE" in data["member_name"]
            assert data["client_id"] == "client_pkce_123"

        # Save Author URN and verify status includes it
        urn_res = api_client.post(
            "/api/integrations/linkedin/author-urn",
            json={"author_urn": "urn:li:person:yash12345"},
        )
        assert urn_res.status_code == 200
        assert urn_res.json()["author_urn"] == "urn:li:person:yash12345"

        with patch("httpx.AsyncClient.get", return_value=mock_403):
            res2 = api_client.get("/api/integrations/linkedin/status")
            assert res2.status_code == 200
            assert res2.json()["author_urn"] == "urn:li:person:yash12345"
    finally:
        credentials.delete_credential("linkedin_access_token")
        credentials.delete_credential("linkedin_client_id")
        credentials.delete_credential("linkedin_author_urn")


def test_draft_media_management_flow(api_client: TestClient, tmp_path):
    """Verify uploading media, choosing system/repo media, and removing media from drafts."""
    # Create project and draft
    mock_repo_info = GitHubRepoInfo(
        owner="mediauser",
        repo="media-project",
        full_name="mediauser/media-project",
        description="Demo project with rich media",
        html_url="https://github.com/mediauser/media-project",
        language="Python",
        languages={"Python": 80000, "HTML": 20000},
        primary_programming_language="Python",
        detected_technologies=["Django", "Python"],
        repo_media_urls=[{"title": "demo.png", "url": "https://example.com/demo.png", "type": "image"}],
        has_readme=True,
    )

    with patch("src.publisher.services.github_service.GitHubClient.fetch_repository", new_callable=AsyncMock, return_value=mock_repo_info):
        proj_res = api_client.post(
            "/api/projects/analyze",
            json={"repo_url": "https://github.com/mediauser/media-project"},
        )
        assert proj_res.status_code == 200
        proj_id = proj_res.json()["project_id"]

    # Generate draft
    with patch("src.publisher.services.ai.cloud_provider.CloudAPIProvider.generate_linkedin_draft", new_callable=AsyncMock) as mock_gen:
        from src.publisher.services.ai.base import GeneratedDraftOutput
        mock_gen.return_value = GeneratedDraftOutput(
            post_text="I developed media-project using Django and Python.",
            hashtags=["#Python", "#Django"],
            project_links=["https://github.com/mediauser/media-project"],
        )
        draft_res = api_client.post(f"/api/projects/{proj_id}/drafts", json={})
        assert draft_res.status_code == 200
        draft_id = draft_res.json()["draft_id"]

    # 1. Query available media
    avail_res = api_client.get(f"/api/projects/{proj_id}/available-media")
    assert avail_res.status_code == 200
    avail_items = avail_res.json()
    assert len(avail_items) >= 1
    assert any("demo.png" in item["title"] for item in avail_items)

    # 2. Upload photo
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    upload_res = api_client.post(
        f"/api/drafts/{draft_id}/media/upload",
        files={"file": ("screenshot.png", fake_png, "image/png")},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert upload_data["status"] == "success"
    assert upload_data["is_video"] is False
    assert "data/media" in upload_data["media_path"]

    # Verify draft now has media
    draft_get = api_client.get(f"/api/drafts/{draft_id}")
    assert draft_get.status_code == 200
    assert draft_get.json()["screenshot_path"] == upload_data["media_path"]

    # 3. Select repo media
    put_res = api_client.put(
        f"/api/drafts/{draft_id}/media",
        json={"media_path": "https://example.com/repo_img.png"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["media_path"] == "https://example.com/repo_img.png"

    # 4. Detach media
    del_res = api_client.delete(f"/api/drafts/{draft_id}/media")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    draft_get2 = api_client.get(f"/api/drafts/{draft_id}")
    assert draft_get2.json()["screenshot_path"] is None


def test_multi_media_selection_and_ordering_api_workflow(api_client: TestClient):
    """Verify selecting multiple media items with custom ordering [1, 4, 2] is preserved through the API."""
    # 1. Create project and draft with mocked GitHub repo
    mock_repo = GitHubRepoInfo(
        owner="testuser",
        repo="multi-media-proj",
        full_name="testuser/multi-media-proj",
        description="Multi-media test repository",
        html_url="https://github.com/testuser/multi-media-proj",
        language="Python",
        topics=["ai"],
        has_readme=True,
        readme_content="# Multi Media Test",
    )

    with patch("src.publisher.services.github_service.GitHubClient.fetch_repository", new_callable=AsyncMock, return_value=mock_repo):
        proj_res = api_client.post(
            "/api/projects/analyze",
            json={"repo_url": "https://github.com/testuser/multi-media-proj"},
        )
        assert proj_res.status_code == 200
        project_id = proj_res.json()["project_id"]

    from src.publisher.services.ai.base import GeneratedDraftOutput
    mock_ai = GeneratedDraftOutput(
        post_text="Multi-media draft showcase post",
        hashtags=["#Python"],
        project_links=[],
        evidence_references=[],
    )
    with patch("src.publisher.services.ai.cloud_provider.CloudAPIProvider.generate_linkedin_draft", new_callable=AsyncMock, return_value=mock_ai):
        draft_res = api_client.post(
            f"/api/projects/{project_id}/drafts",
            json={"style": "developer"},
        )
        assert draft_res.status_code == 200
        draft_id = draft_res.json()["draft_id"]

    # 2. Attach multiple media paths in specific user sequence: [img1, img4, img2]
    custom_order = [
        "https://example.com/asset1.png",
        "https://example.com/asset4.png",
        "https://example.com/asset2.png",
    ]
    put_res = api_client.put(
        f"/api/drafts/{draft_id}/media",
        json={"media_path": custom_order[0], "media_paths": custom_order},
    )
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["screenshot_path"] == "https://example.com/asset1.png"
    assert put_data["media_paths"] == custom_order

    # 3. Retrieve draft via GET and assert exact sequence order is preserved
    get_res = api_client.get(f"/api/drafts/{draft_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["media_paths"] == [
        "https://example.com/asset1.png",
        "https://example.com/asset4.png",
        "https://example.com/asset2.png",
    ]

    # 4. Reorder items to [asset4, asset2, asset1]
    reordered = [
        "https://example.com/asset4.png",
        "https://example.com/asset2.png",
        "https://example.com/asset1.png",
    ]
    reorder_res = api_client.put(
        f"/api/drafts/{draft_id}/media",
        json={"media_path": reordered[0], "media_paths": reordered},
    )
    assert reorder_res.status_code == 200
    assert reorder_res.json()["media_paths"] == reordered
    assert reorder_res.json()["screenshot_path"] == "https://example.com/asset4.png"

    # 5. Delete and verify both screenshot_path and media_paths are cleared
    del_res = api_client.delete(f"/api/drafts/{draft_id}/media")
    assert del_res.status_code == 200

    get_res2 = api_client.get(f"/api/drafts/{draft_id}")
    assert get_res2.status_code == 200
    assert get_res2.json()["screenshot_path"] is None
    assert get_res2.json()["media_paths"] == []


