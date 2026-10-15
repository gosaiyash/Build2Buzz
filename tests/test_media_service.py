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
