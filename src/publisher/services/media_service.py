"""Media management service handling screenshot validation and LinkedIn media upload protocol."""

import os
from pathlib import Path
from typing import Any
import httpx
from pydantic import BaseModel
from src.publisher.core.config import (
    get_current_linkedin_api_version,
    get_fallback_linkedin_api_version,
)
from src.publisher.core.logging_config import logger


class MediaValidationResult(BaseModel):
    is_valid: bool
    error: str | None = None
    file_path: str
    file_size_mb: float = 0.0
    mime_type: str = ""
    is_video: bool = False


class MediaService:
    """Validates local media files and coordinates with LinkedIn's official image upload protocol."""

    ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
    ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS
    MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024  # 8 MB limit for LinkedIn images
    MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB limit for videos

    @classmethod
    def validate_media(cls, file_path: str) -> MediaValidationResult:
        if not file_path:
            return MediaValidationResult(is_valid=False, error="File path is empty", file_path="")

        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return MediaValidationResult(is_valid=False, error=f"File not found: {file_path}", file_path=file_path)

        ext = p.suffix.lower()
        is_video = ext in cls.ALLOWED_VIDEO_EXTENSIONS
        is_image = ext in cls.ALLOWED_IMAGE_EXTENSIONS

        if not is_video and not is_image:
            allowed = sorted(list(cls.ALLOWED_IMAGE_EXTENSIONS | cls.ALLOWED_VIDEO_EXTENSIONS))
            return MediaValidationResult(
                is_valid=False,
                error=f"Unsupported format '{ext}'. Allowed: {', '.join(allowed)}",
                file_path=file_path,
            )

        size = p.stat().st_size
        size_mb = round(size / (1024 * 1024), 2)
        max_bytes = cls.MAX_VIDEO_SIZE_BYTES if is_video else cls.MAX_FILE_SIZE_BYTES
        max_mb = 100 if is_video else 8

        if size > max_bytes:
            media_type_name = "Video" if is_video else "Image"
            return MediaValidationResult(
                is_valid=False,
                error=f"{media_type_name} size ({size_mb} MB) exceeds maximum {max_mb} MB limit.",
                file_path=file_path,
                file_size_mb=size_mb,
                is_video=is_video,
            )

        if is_video:
            mime = "video/mp4" if ext == ".mp4" else ("video/webm" if ext == ".webm" else "video/quicktime")
        else:
            mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else ("image/gif" if ext == ".gif" else "image/jpeg"))

        return MediaValidationResult(
            is_valid=True,
            file_path=str(p.resolve()),
            file_size_mb=size_mb,
            mime_type=mime,
            is_video=is_video,
        )

    @classmethod
    def validate_image(cls, file_path: str) -> MediaValidationResult:
        if not file_path:
            return MediaValidationResult(is_valid=False, error="File path is empty", file_path="")

        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return MediaValidationResult(is_valid=False, error=f"File not found: {file_path}", file_path=file_path)

        ext = p.suffix.lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            return MediaValidationResult(
                is_valid=False,
                error=f"Unsupported format '{ext}'. Allowed: {', '.join(cls.ALLOWED_EXTENSIONS)}",
                file_path=file_path,
            )

        size = p.stat().st_size
        size_mb = round(size / (1024 * 1024), 2)
        if size > cls.MAX_FILE_SIZE_BYTES:
            return MediaValidationResult(
                is_valid=False,
                error=f"Image size ({size_mb} MB) exceeds maximum 8 MB limit.",
                file_path=file_path,
                file_size_mb=size_mb,
            )

        mime = "image/png" if ext == ".png" else "image/jpeg"
        return MediaValidationResult(
            is_valid=True,
            file_path=str(p.resolve()),
            file_size_mb=size_mb,
            mime_type=mime,
        )

    @classmethod
    async def upload_image_to_linkedin(
        cls,
        file_path: str,
        access_token: str,
        author_urn: str,
    ) -> str:
        """Execute official LinkedIn 2-step image upload protocol:

        Step 1: Initialize upload -> receives uploadUrl and image URN.
        Step 2: PUT raw image binary to uploadUrl.
        Returns: image URN (e.g. 'urn:li:image:D54000123')
        """
        val = cls.validate_image(file_path)
        if not val.is_valid:
            raise ValueError(f"Image validation failed: {val.error}")

        # Step 1: Initialize upload
        init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
        init_payload = {
            "initializeUploadRequest": {
                "owner": author_urn,
            }
        }
        active_version = get_current_linkedin_api_version()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": active_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        logger.info("Initializing image upload with LinkedIn (Version %s) for: %s", active_version, file_path)
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(init_url, headers=headers, json=init_payload)
            if res.status_code == 426:
                fallback_version = get_fallback_linkedin_api_version(active_version)
                if fallback_version != active_version:
                    logger.warning(
                        "LinkedIn image upload initialization version '%s' returned 426. Retrying with '%s'...",
                        active_version,
                        fallback_version,
                    )
                    headers["LinkedIn-Version"] = fallback_version
                    res = await client.post(init_url, headers=headers, json=init_payload)

            if res.status_code != 200:
                raise ValueError(f"LinkedIn image upload initialization failed ({res.status_code}): {res.text[:150]}")

            init_data = res.json()["value"]
            upload_url = init_data["uploadUrl"]
            image_urn = init_data["image"]

            # Step 2: Upload binary bytes
            with open(file_path, "rb") as f:
                img_bytes = f.read()

            upload_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": val.mime_type,
            }
            put_res = await client.put(upload_url, headers=upload_headers, content=img_bytes)
            if put_res.status_code not in {200, 201}:
                raise ValueError(f"Uploading image binary failed ({put_res.status_code}): {put_res.text[:100]}")

            logger.info("Image successfully uploaded to LinkedIn: %s", image_urn)
            return image_urn
