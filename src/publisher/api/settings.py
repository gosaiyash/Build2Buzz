"""API endpoints for managing application settings, AI mode, and preferences."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.publisher.core.security import mask_secret
from src.publisher.db.connection import get_db
from src.publisher.db.repositories import SettingsRepository
from src.publisher.services.ai.router import AIProviderRouter
from src.publisher.services.credential_manager import credentials

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingsResponse(BaseModel):
    active_mode: str
    cloud_provider: str
    cloud_model: str
    cloud_base_url: str | None = None
    has_cloud_api_key: bool
    masked_cloud_api_key: str
    local_model_path: str | None = None
    local_context_length: int
    local_gpu_layers: int
    has_github_token: bool
    has_linkedin_token: bool
    preferences: dict[str, Any]


class UpdateLlmSettingsRequest(BaseModel):
    mode: str = Field(description="'cloud' or 'local'")
    cloud_provider: str | None = None
    cloud_model: str | None = None
    cloud_base_url: str | None = None
    cloud_api_key: str | None = None  # Saved to keyring
    cloud_timeout: int | None = Field(default=120, description="Timeout in seconds for cloud inference")
    local_model_path: str | None = None
    local_context_length: int | None = None
    local_gpu_layers: int | None = None


class UpdatePreferencesRequest(BaseModel):
    preferences: dict[str, Any]


@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    """Retrieve non-secret settings and masked credential statuses."""
    repo = SettingsRepository(db)
    rec = repo.get_or_create()

    has_ai_key = credentials.has_credential("ai_api_key")
    masked_ai_key = credentials.get_masked_credential("ai_api_key")
    has_gh_token = credentials.has_credential("github_pat")
    has_li_token = credentials.has_credential("linkedin_access_token")

    return SettingsResponse(
        active_mode=rec.active_ai_mode,
        cloud_provider=rec.cloud_provider,
        cloud_model=rec.cloud_model,
        cloud_base_url=rec.cloud_base_url,
        has_cloud_api_key=has_ai_key,
        masked_cloud_api_key=masked_ai_key,
        local_model_path=rec.local_model_path,
        local_context_length=rec.local_context_length,
        local_gpu_layers=rec.local_gpu_layers,
        has_github_token=has_gh_token,
        has_linkedin_token=has_li_token,
        preferences=rec.preferences or {},
    )


@router.put("/llm")
async def update_llm_settings(
    req: UpdateLlmSettingsRequest, db: Session = Depends(get_db)
):
    """Update active AI mode and provider configurations with mutually exclusive enforcement."""
    repo = SettingsRepository(db)

    # If an API key was submitted, save it securely in Windows Credential Manager
    if req.cloud_api_key is not None:
        if req.cloud_api_key.strip():
            credentials.set_credential("ai_api_key", req.cloud_api_key.strip())

    try:
        updated = repo.update_ai_mode(
            mode=req.mode,
            cloud_provider=req.cloud_provider,
            cloud_model=req.cloud_model,
            cloud_base_url=req.cloud_base_url,
            local_model_path=req.local_model_path,
            local_context_length=req.local_context_length,
            local_gpu_layers=req.local_gpu_layers,
        )
        if req.cloud_timeout is not None:
            prefs = dict(updated.preferences or {})
            prefs["cloud_timeout"] = req.cloud_timeout
            updated.preferences = prefs
            db.commit()

        return {
            "status": "success",
            "message": f"AI mode set to '{updated.active_ai_mode}'.",
            "active_mode": updated.active_ai_mode,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/llm/key")
async def delete_ai_api_key():
    """Remove AI API key from Windows Credential Manager."""
    credentials.delete_credential("ai_api_key")
    return {"status": "success", "message": "Cloud AI API key removed from secure storage."}


@router.post("/llm/test")
async def test_llm_connection(db: Session = Depends(get_db)):
    """Test connectivity or model availability of the active AI provider."""
    repo = SettingsRepository(db)
    rec = repo.get_or_create()
    router_inst = AIProviderRouter(rec, credential_resolver=credentials.get_credential)

    try:
        provider = router_inst.get_active_provider()
        ok, msg = await provider.test_connection()
        if not ok:
            return {"status": "error", "message": msg}
        return {"status": "success", "message": msg}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.put("/preferences")
async def update_preferences(
    req: UpdatePreferencesRequest, db: Session = Depends(get_db)
):
    """Update user post preferences (style, language, length, custom instructions)."""
    repo = SettingsRepository(db)
    rec = repo.get_or_create()
    rec.preferences = req.preferences
    db.commit()
    return {"status": "success", "preferences": rec.preferences}
