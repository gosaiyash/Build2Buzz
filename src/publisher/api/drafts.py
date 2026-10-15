from pathlib import Path
import re
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger
from src.publisher.db.connection import get_db
from src.publisher.db.models import DraftStatus, Project
from src.publisher.db.repositories import (
    DraftRepository,
    HistoryRepository,
    ProjectRepository,
)
from src.publisher.services.credential_manager import credentials
from src.publisher.services.linkedin_service import LinkedInPublishingService
from src.publisher.services.media_service import MediaService
from src.publisher.services.validator import DraftValidator

router = APIRouter(prefix="/api/drafts", tags=["Drafts"])


class UpdateDraftRequest(BaseModel):
    body: str


class UpdateMediaRequest(BaseModel):
    media_path: str | None = None


@router.get("/{draft_id}")
async def get_draft(draft_id: int, db: Session = Depends(get_db)):
    """Retrieve full details of a draft post."""
    draft_repo = DraftRepository(db)
    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    project = db.query(Project).filter(Project.id == draft.project_id).first()

    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "version": draft.version,
        "body": draft.body,
        "style": draft.style,
        "status": draft.status.value,
        "metadata": draft.post_metadata,
        "repo_url": project.repo_url if project else None,
        "demo_url": project.demo_url if project else None,
        "screenshot_path": draft.screenshot_path,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
    }


@router.put("/{draft_id}")
async def update_draft(
    draft_id: int, req: UpdateDraftRequest, db: Session = Depends(get_db)
):
    """Edit draft text. Invalidates previous approval and moves draft back to NEEDS_REVIEW."""
    draft_repo = DraftRepository(db)
    try:
        updated = draft_repo.update_content(draft_id, req.body)
        return {
            "status": "success",
            "message": "Draft updated.",
            "draft_id": updated.id,
            "state": updated.status.value,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{draft_id}/media/upload")
async def upload_draft_media(
    draft_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload external media (photo or video) for a draft post."""
    draft_repo = DraftRepository(db)
    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # Sanitize filename & extension
    original_name = Path(file.filename).name
    ext = Path(file.filename).suffix.lower()
    allowed_exts = MediaService.ALLOWED_IMAGE_EXTENSIONS | MediaService.ALLOWED_VIDEO_EXTENSIONS
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed formats: {', '.join(sorted(list(allowed_exts)))}",
        )

    # Save to data/media
    media_dir = settings.DATA_DIR / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"draft_{draft_id}_{uuid.uuid4().hex[:8]}_{re.sub(r'[^A-Za-z0-9_.-]', '_', original_name)}"
    dest_path = media_dir / safe_name

    try:
        content = await file.read()
        dest_path.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write uploaded media to disk: {exc}")

    # Validate size & media rules
    val = MediaService.validate_media(str(dest_path))
    if not val.is_valid:
        if dest_path.exists():
            dest_path.unlink()
        raise HTTPException(status_code=400, detail=val.error or "Media validation failed.")

    rel_path = f"data/media/{safe_name}"
    updated = draft_repo.update_media(draft_id, rel_path)

    return {
        "status": "success",
        "message": "Media uploaded and attached to draft.",
        "media_path": rel_path,
        "is_video": val.is_video,
        "mime_type": val.mime_type,
        "file_size_mb": val.file_size_mb,
        "draft_state": updated.status.value,
    }


@router.put("/{draft_id}/media")
async def attach_draft_media(
    draft_id: int,
    req: UpdateMediaRequest,
    db: Session = Depends(get_db),
):
    """Attach existing system or repo media to a draft, or modify attached media."""
    draft_repo = DraftRepository(db)
    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    updated = draft_repo.update_media(draft_id, req.media_path)
    return {
        "status": "success",
        "message": "Attached media updated.",
        "media_path": updated.screenshot_path,
        "draft_state": updated.status.value,
    }


@router.delete("/{draft_id}/media")
async def detach_draft_media(
    draft_id: int,
    db: Session = Depends(get_db),
):
    """Remove attached media from a draft post."""
    draft_repo = DraftRepository(db)
    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    updated = draft_repo.update_media(draft_id, None)
    return {
        "status": "success",
        "message": "Attached media removed.",
        "media_path": None,
        "draft_state": updated.status.value,
    }


@router.post("/{draft_id}/validate")
async def validate_draft(draft_id: int, db: Session = Depends(get_db)):
    """Run content and safety validation against the draft."""
    draft_repo = DraftRepository(db)
    proj_repo = ProjectRepository(db)
    hist_repo = HistoryRepository(db)

    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    project = proj_repo.get(draft.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Associated project not found.")

    # Fetch previously published post bodies for duplicate check
    published_records = hist_repo.list_all(limit=100)
    prev_bodies: list[str] = []
    for h in published_records:
        if h.draft and h.status.value == "SUCCESS":
            prev_bodies.append(h.draft.body)

    report = DraftValidator.validate(
        draft=draft,
        project=project,
        previously_published_bodies=prev_bodies,
    )

    # If valid and currently GENERATED, advance to VALIDATED
    if report.is_valid and draft.status == DraftStatus.GENERATED:
        draft_repo.set_status(draft_id, DraftStatus.VALIDATED)

    return report.model_dump()


@router.post("/{draft_id}/approve")
async def approve_draft(draft_id: int, db: Session = Depends(get_db)):
    """Explicit user approval step required before publishing."""
    draft_repo = DraftRepository(db)
    proj_repo = ProjectRepository(db)

    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    project = proj_repo.get(draft.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Associated project not found.")

    # Validate before approval
    report = DraftValidator.validate(draft, project)
    if not report.is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve draft with validation errors: {', '.join(report.errors)}",
        )

    draft_repo.set_status(draft_id, DraftStatus.APPROVED)
    return {"status": "success", "message": f"Draft #{draft_id} is now APPROVED for publishing."}


@router.post("/{draft_id}/publish")
async def publish_draft(draft_id: int, db: Session = Depends(get_db)):
    """Publish an approved draft to LinkedIn using the official REST API."""
    draft_repo = DraftRepository(db)
    proj_repo = ProjectRepository(db)
    hist_repo = HistoryRepository(db)

    draft = draft_repo.get(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")

    # Strict human-in-the-loop requirement: Must be APPROVED
    if draft.status != DraftStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"Publishing blocked: Draft #{draft_id} is in '{draft.status.value}' state. Explicit approval is required.",
        )

    project = proj_repo.get(draft.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Associated project not found.")

    # Retrieve credentials
    access_token = credentials.get_credential("linkedin_access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="LinkedIn is not connected. Please authorize LinkedIn in Integrations first.",
        )

    # Retrieve author URN from LinkedIn profile
    from src.publisher.services.linkedin_service import LinkedInOAuthService

    fallback_urn = credentials.get_credential("linkedin_author_urn")
    try:
        profile = await LinkedInOAuthService.get_user_profile(access_token, fallback_author_urn=fallback_urn)
        author_urn = profile.author_urn
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"Failed to verify LinkedIn account: {exc}"
        )

    # 1. Record submission audit entry
    submission = hist_repo.record_submission(draft_id)
    draft_repo.set_status(draft_id, DraftStatus.PUBLISHING)

    # 2. Call publishing service
    success, post_urn_or_error, err_cat = await LinkedInPublishingService.publish_draft(
        draft=draft,
        project=project,
        access_token=access_token,
        author_urn=author_urn,
        submission_id=submission.submission_id,
    )

    if success:
        hist_repo.record_success(submission.submission_id, post_urn_or_error)
        draft_repo.set_status(draft_id, DraftStatus.PUBLISHED)
        return {
            "status": "success",
            "message": "Post successfully published to LinkedIn!",
            "linkedin_post_id": post_urn_or_error,
            "submission_id": submission.submission_id,
        }
    else:
        hist_repo.record_failure(submission.submission_id, err_cat or "Unknown", post_urn_or_error)
        draft_repo.set_status(draft_id, DraftStatus.PUBLISH_FAILED)
        raise HTTPException(
            status_code=502,
            detail=f"LinkedIn publishing failed: {post_urn_or_error}",
        )
