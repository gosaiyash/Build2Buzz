"""Unit tests for media validation and LinkedIn media upload protocol."""

from unittest.mock import AsyncMock, patch
import pytest
import httpx
from src.publisher.services.media_service import MediaService


def test_media_validator_formats(tmp_path):
    """Verify supported and unsupported image extensions."""
    valid_png = tmp_path / "screenshot.png"
    valid_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    res = MediaService.validate_image(str(valid_png))
    assert res.is_valid is True
    assert res.mime_type == "image/png"

    invalid_txt = tmp_path / "notes.txt"
    invalid_txt.write_text("not an image")
    res_bad = MediaService.validate_image(str(invalid_txt))
    assert res_bad.is_valid is False
    assert "Unsupported format" in res_bad.error


def test_media_validator_size_limit(tmp_path):
    """Verify images exceeding 8 MB are rejected."""
    huge_file = tmp_path / "huge.png"
    # Create file just over 8 MB
    huge_file.write_bytes(b"\x00" * (8 * 1024 * 1024 + 1024))

    res = MediaService.validate_image(str(huge_file))
    assert res.is_valid is False
    assert "exceeds maximum 8 MB limit" in res.error


@pytest.mark.asyncio
async def test_upload_image_to_linkedin_mocked(tmp_path):
    """Verify 2-step LinkedIn image upload protocol."""
    test_img = tmp_path / "demo.png"
    test_img.write_bytes(b"\x89PNG" + b"\x00" * 50)

    init_resp = httpx.Response(
        status_code=200,
        json={"value": {"uploadUrl": "https://upload.example.com/binary", "image": "urn:li:image:12345"}},
    )
    put_resp = httpx.Response(status_code=201)

    async def mock_handler(request):
        if "action=initializeUpload" in str(request.url):
            return init_resp
        return put_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=init_resp) as mock_post, \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=put_resp) as mock_put:
        urn = await MediaService.upload_image_to_linkedin(
            file_path=str(test_img),
            access_token="mock-token",
            author_urn="urn:li:person:123",
        )
        assert urn == "urn:li:image:12345"
        # Check that LinkedIn-Version header was sent and is a valid 6-digit YYYYMM format
        call_headers = mock_post.call_args.kwargs["headers"]
        assert "LinkedIn-Version" in call_headers
        assert len(call_headers["LinkedIn-Version"]) == 6
        assert call_headers["LinkedIn-Version"] != "202401"


@pytest.mark.asyncio
async def test_upload_image_retries_on_426_version_error(tmp_path):
    """Verify MediaService retries on 426 NONEXISTENT_VERSION."""
    test_img = tmp_path / "demo.png"
    test_img.write_bytes(b"\x89PNG" + b"\x00" * 50)

    resp_426 = httpx.Response(status_code=426, text='{"status":426,"code":"NONEXISTENT_VERSION"}')
    init_resp = httpx.Response(
        status_code=200,
        json={"value": {"uploadUrl": "https://upload.example.com/binary", "image": "urn:li:image:retry_img"}},
    )
    put_resp = httpx.Response(status_code=200)

    post_calls = []

    async def mock_post(url, headers=None, json=None):
        post_calls.append(headers.get("LinkedIn-Version"))
        if len(post_calls) == 1:
            return resp_426
        return init_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=put_resp):
        urn = await MediaService.upload_image_to_linkedin(
            file_path=str(test_img),
            access_token="mock-token",
            author_urn="urn:li:person:123",
        )
        assert urn == "urn:li:image:retry_img"
        assert len(post_calls) == 2
        assert post_calls[0] != post_calls[1]


@pytest.mark.asyncio
async def test_resolve_media_file_remote(tmp_path):
    """Verify remote URLs are downloaded and cached."""
    mock_resp = httpx.Response(status_code=200, content=b"\x89PNG" + b"\x00" * 30)

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        path, is_video, mime = await MediaService.resolve_media_file("https://example.com/sample.png")
        assert path.exists()
        assert is_video is False
        assert mime == "image/png"


@pytest.mark.asyncio
async def test_upload_video_to_linkedin_mocked(tmp_path):
    """Verify 4-step LinkedIn video upload protocol."""
    test_vid = tmp_path / "launch.mp4"
    test_vid.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200)

    init_resp = httpx.Response(
        status_code=200,
        json={
            "value": {
                "video": "urn:li:video:test_vid_123",
                "uploadToken": "token-xyz",
                "uploadInstructions": [
                    {"uploadUrl": "https://upload.example.com/chunk0", "firstByte": 0, "lastByte": 100},
                    {"uploadUrl": "https://upload.example.com/chunk1", "firstByte": 101, "lastByte": 207},
                ],
            }
        },
    )
    put_resp = httpx.Response(status_code=200, headers={"ETag": '"etag-chunk"'})
    fin_resp = httpx.Response(status_code=200, json={})
    status_resp = httpx.Response(status_code=200, json={"status": "AVAILABLE"})

    async def mock_post(url, headers=None, json=None):
        if "action=initializeUpload" in str(url):
            return init_resp
        return fin_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("httpx.AsyncClient.put", new_callable=AsyncMock, return_value=put_resp), \
         patch("httpx.AsyncClient.get", return_value=status_resp):
        urn = await MediaService.upload_video_to_linkedin(
            file_path=str(test_vid),
            access_token="mock-token",
            author_urn="urn:li:person:123",
        )
        assert urn == "urn:li:video:test_vid_123"


@pytest.mark.asyncio
async def test_upload_media_to_linkedin_dispatcher(tmp_path):
    """Verify upload_media_to_linkedin dispatches based on file extension."""
    test_img = tmp_path / "shot.png"
    test_img.write_bytes(b"\x89PNG" + b"\x00" * 10)

    test_vid = tmp_path / "clip.mp4"
    test_vid.write_bytes(b"\x00" * 50)

    with patch.object(MediaService, "upload_image_to_linkedin", new_callable=AsyncMock, return_value="urn:li:image:999"), \
         patch.object(MediaService, "upload_video_to_linkedin", new_callable=AsyncMock, return_value="urn:li:video:888"):
        urn_img, mtype_img = await MediaService.upload_media_to_linkedin(str(test_img), "tok", "urn:li:person:1")
        assert urn_img == "urn:li:image:999"
        assert mtype_img == "image"

        urn_vid, mtype_vid = await MediaService.upload_media_to_linkedin(str(test_vid), "tok", "urn:li:person:1")
        assert urn_vid == "urn:li:video:888"
        assert mtype_vid == "video"


