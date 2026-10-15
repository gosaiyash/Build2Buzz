"""API endpoints for reviewing publishing audit history."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.publisher.db.connection import get_db
from src.publisher.db.repositories import HistoryRepository

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("")
async def get_history(db: Session = Depends(get_db)):
    """Retrieve publishing audit records and outcomes."""
    hist_repo = HistoryRepository(db)
    items = hist_repo.list_all(limit=50)

    result = []
    for h in items:
        proj_name = h.draft.project.name if (h.draft and h.draft.project) else "Unknown"
        ai_mode = h.draft.post_metadata.get("ai_mode", "cloud") if (h.draft and h.draft.post_metadata) else "cloud"

        result.append(
            {
                "id": h.id,
                "draft_id": h.draft_id,
                "project_name": proj_name,
                "submission_id": h.submission_id,
                "linkedin_post_id": h.linkedin_post_id,
                "status": h.status.value,
                "ai_mode": ai_mode,
                "created_at": h.created_at.isoformat(),
                "published_at": h.published_at.isoformat() if h.published_at else None,
                "error_category": h.error_category,
                "sanitized_error": h.sanitized_error,
            }
        )
    return result
