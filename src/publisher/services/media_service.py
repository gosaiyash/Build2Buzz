"""Media management service handling screenshot validation, downloading, and LinkedIn media upload protocol."""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any
import urllib.parse
import httpx
from pydantic import BaseModel
from src.publisher.core.config import (
    settings,
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
    """Validates local and remote media files and coordinates with LinkedIn's official Image and Video upload protocol."""

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
            mime = (
                "image/png"
                if ext == ".png"
                else (
                    "image/webp"
                    if ext == ".webp"
                    else ("image/gif" if ext == ".gif" else "image/jpeg")
                )
            )

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
            allowed = sorted(list(cls.ALLOWED_EXTENSIONS))
            return MediaValidationResult(
                is_valid=False,
                error=f"Unsupported format '{ext}'. Allowed: {', '.join(allowed)}",
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

        if ext == ".png":
            mime = "image/png"
        elif ext == ".gif":
            mime = "image/gif"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            mime = "image/jpeg"

        return MediaValidationResult(
            is_valid=True,
            file_path=str(p.resolve()),
            file_size_mb=size_mb,
            mime_type=mime,
        )

    @classmethod
    async def resolve_media_file(cls, file_path_or_url: str) -> tuple[Path, bool, str]:
        """Resolves local paths or remote URLs to an existing local file on disk,
        determining its media type (video vs image) and MIME type.
        """
        if not file_path_or_url or not str(file_path_or_url).strip():
            raise ValueError("Media file path or URL is empty.")

        target = str(file_path_or_url).strip()

        # Handle Remote URLs (e.g. GitHub raw assets, uploaded URLs)
        if target.startswith("http://") or target.startswith("https://"):
            url_hash = hashlib.sha256(target.encode()).hexdigest()[:12]
            raw_filename = Path(urllib.parse.urlparse(target).path).name or "media_asset"
            safe_filename = "".join(c for c in raw_filename if c.isalnum() or c in "._-") or "media_asset"
            cached_file = settings.DATA_DIR / "media" / f"cached_{url_hash}_{safe_filename}"
            settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
            (settings.DATA_DIR / "media").mkdir(parents=True, exist_ok=True)

            if not cached_file.exists() or cached_file.stat().st_size == 0:
                logger.info("Downloading remote media from %s -> %s", target, cached_file.name)
                async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                    resp = await client.get(target)
                    if resp.status_code != 200:
                        raise ValueError(f"Failed to download remote media from '{target}' (HTTP {resp.status_code})")
                    cached_file.write_bytes(resp.content)

            local_path = cached_file
        else:
            # Handle Local Paths
            clean_local = target.lstrip("/").replace("\\", "/")
            candidates = [
                Path(target),
                Path(clean_local),
                Path.cwd() / clean_local,
                settings.DATA_DIR / clean_local,
                settings.DATA_DIR / "media" / Path(clean_local).name,
                settings.DATA_DIR / "screenshots" / Path(clean_local).name,
                Path(__file__).resolve().parent.parent.parent.parent / clean_local,
            ]
            local_path = None
            for cand in candidates:
                if cand.exists() and cand.is_file():
                    local_path = cand.resolve()
                    break

            if not local_path:
                raise FileNotFoundError(f"Media file not found on disk: {target}")

        ext = local_path.suffix.lower()
        is_video = ext in cls.ALLOWED_VIDEO_EXTENSIONS
        is_image = ext in cls.ALLOWED_IMAGE_EXTENSIONS

        if not is_video and not is_image:
            allowed = sorted(list(cls.ALLOWED_IMAGE_EXTENSIONS | cls.ALLOWED_VIDEO_EXTENSIONS))
            raise ValueError(f"Unsupported media format '{ext}'. Allowed formats: {', '.join(allowed)}")

        size = local_path.stat().st_size
        max_bytes = cls.MAX_VIDEO_SIZE_BYTES if is_video else cls.MAX_FILE_SIZE_BYTES
        max_mb = 100 if is_video else 8
        size_mb = round(size / (1024 * 1024), 2)
        if size > max_bytes:
            media_name = "Video" if is_video else "Image"
            raise ValueError(f"{media_name} size ({size_mb} MB) exceeds maximum {max_mb} MB limit.")

        if is_video:
            mime = "video/mp4" if ext == ".mp4" else ("video/webm" if ext == ".webm" else "video/quicktime")
        else:
            if ext == ".png":
                mime = "image/png"
            elif ext == ".gif":
                mime = "image/gif"
            elif ext == ".webp":
                mime = "image/webp"
            else:
                mime = "image/jpeg"

        return local_path, is_video, mime

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
        local_path, is_video, mime = await cls.resolve_media_file(file_path)
        if is_video:
            return await cls.upload_video_to_linkedin(str(local_path), access_token, author_urn)

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

        logger.info("Initializing image upload with LinkedIn (Version %s) for: %s (%s)", active_version, local_path.name, mime)
        async with httpx.AsyncClient(timeout=45.0) as client:
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
            with open(local_path, "rb") as f:
                img_bytes = f.read()

            upload_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": mime,
            }
            put_res = await client.put(upload_url, headers=upload_headers, content=img_bytes)
            if put_res.status_code not in {200, 201}:
                raise ValueError(f"Uploading image binary failed ({put_res.status_code}): {put_res.text[:100]}")

            logger.info("Image successfully uploaded to LinkedIn: %s", image_urn)
            return image_urn

    @classmethod
    async def upload_video_to_linkedin(
        cls,
        file_path: str,
        access_token: str,
        author_urn: str,
    ) -> str:
        """Execute official LinkedIn chunked video upload protocol:
        Step 1: Initialize upload -> receives video URN and uploadInstructions.
        Step 2: Upload binary chunks via PUT and collect ETag headers.
        Step 3: Finalize upload with uploadedPartIds.
        Step 4: Poll status until AVAILABLE.
        Returns: video URN (e.g. 'urn:li:video:D4D10AQELB1ClVH1Nig')
        """
        local_path, _, mime = await cls.resolve_media_file(file_path)
        file_size = local_path.stat().st_size

        init_url = "https://api.linkedin.com/rest/videos?action=initializeUpload"
        init_payload = {
            "initializeUploadRequest": {
                "owner": author_urn,
                "fileSizeBytes": file_size,
            }
        }
        active_version = get_current_linkedin_api_version()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "LinkedIn-Version": active_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        logger.info("Initializing video upload with LinkedIn (Version %s) for %s (%d bytes)", active_version, local_path.name, file_size)
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(init_url, headers=headers, json=init_payload)
            if res.status_code == 426:
                fallback_version = get_fallback_linkedin_api_version(active_version)
                if fallback_version != active_version:
                    headers["LinkedIn-Version"] = fallback_version
                    res = await client.post(init_url, headers=headers, json=init_payload)

            if res.status_code != 200:
                raise ValueError(f"LinkedIn video upload initialization failed ({res.status_code}): {res.text[:150]}")

            init_data = res.json()["value"]
            video_urn = init_data["video"]
            upload_token = init_data.get("uploadToken", "")
            instructions = init_data.get("uploadInstructions", [])

            if not instructions:
                raise ValueError("LinkedIn did not return upload instructions for video.")

            with open(local_path, "rb") as f:
                video_bytes = f.read()

            uploaded_part_ids = []
            for part in instructions:
                upload_url = part["uploadUrl"]
                first_byte = part["firstByte"]
                last_byte = part["lastByte"]
                chunk = video_bytes[first_byte : last_byte + 1]

                part_headers = {
                    "Content-Type": "application/octet-stream",
                }
                put_res = await client.put(upload_url, headers=part_headers, content=chunk)
                if put_res.status_code not in {200, 201}:
                    raise ValueError(f"Failed to upload video chunk ({put_res.status_code}): {put_res.text[:100]}")

                etag = put_res.headers.get("etag") or put_res.headers.get("ETag") or ""
                uploaded_part_ids.append(etag)

            # Step 3: Finalize upload
            finalize_url = "https://api.linkedin.com/rest/videos?action=finalizeUpload"
            finalize_payload = {
                "finalizeUploadRequest": {
                    "video": video_urn,
                    "uploadToken": upload_token,
                    "uploadedPartIds": uploaded_part_ids,
                }
            }
            fin_headers = {
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": headers["LinkedIn-Version"],
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }
            fin_res = await client.post(finalize_url, headers=fin_headers, json=finalize_payload)
            if fin_res.status_code not in {200, 201}:
                raise ValueError(f"Failed to finalize video upload ({fin_res.status_code}): {fin_res.text[:100]}")

            # Step 4: Poll video status until AVAILABLE (up to 30 seconds)
            encoded_urn = urllib.parse.quote(video_urn, safe="")
            status_url = f"https://api.linkedin.com/rest/videos/{encoded_urn}"
            status_headers = {
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": headers["LinkedIn-Version"],
                "X-Restli-Protocol-Version": "2.0.0",
            }

            for _ in range(15):
                await asyncio.sleep(2.0)
                try:
                    poll_res = await client.get(status_url, headers=status_headers)
                    if poll_res.status_code == 200:
                        status_data = poll_res.json()
                        v_status = status_data.get("status")
                        logger.info("Video %s status: %s", video_urn, v_status)
                        if v_status == "AVAILABLE":
                            break
                        if v_status == "PROCESSING_FAILED":
                            raise ValueError("LinkedIn video processing failed on server.")
                except Exception as poll_err:
                    logger.warning("Error checking video status: %s", poll_err)
                    break

            logger.info("Video successfully uploaded and prepared for LinkedIn: %s", video_urn)
            return video_urn

    @classmethod
    async def upload_media_to_linkedin(
        cls,
        file_path_or_url: str,
        access_token: str,
        author_urn: str,
    ) -> tuple[str, str]:
        """Resolves local or remote media and uploads to LinkedIn via Image or Video protocol.
        Returns: (media_urn, "video" | "image")
        """
        local_path, is_video, _ = await cls.resolve_media_file(file_path_or_url)
        if is_video:
            urn = await cls.upload_video_to_linkedin(str(local_path), access_token, author_urn)
            return urn, "video"
        else:
            urn = await cls.upload_image_to_linkedin(str(local_path), access_token, author_urn)
            return urn, "image"
