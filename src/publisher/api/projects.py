"""API endpoints for repository analysis, evidence extraction, and draft creation."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger
from src.publisher.db.connection import get_db
from src.publisher.db.models import ProjectStatus
from src.publisher.db.repositories import (
    DraftRepository,
    EvidenceRepository,
    ProjectRepository,
    SettingsRepository,
)
from src.publisher.services.ai.base import PostPreferences
from src.publisher.services.ai.router import AIProviderRouter
from src.publisher.services.credential_manager import credentials
from src.publisher.services.demo_inspector import DemoInspector
from src.publisher.services.evidence_engine import EvidenceEngine
from src.publisher.services.github_service import GitHubClient, GitHubServiceError
from src.publisher.services.media_service import MediaService
from src.publisher.services.web_research import WebResearchService

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class AnalyzeProjectRequest(BaseModel):
    repo_url: str
    demo_url: str | None = None
    user_notes: str | None = None
    enable_web_research: bool = False
    post_style: str = "professional"


class GenerateDraftRequest(BaseModel):
    style: str | None = None
    custom_instructions: str | None = None


@router.post("/analyze")
async def analyze_project(req: AnalyzeProjectRequest, db: Session = Depends(get_db)):
    """Analyze GitHub repository, inspect live demo, perform optional web research, and store evidence."""
    proj_repo = ProjectRepository(db)
    ev_repo = EvidenceRepository(db)

    # 1. GitHub Ingestion
    gh_token = credentials.get_credential("github_pat")
    gh_client = GitHubClient(token=gh_token)
    try:
        repo_info = await gh_client.fetch_repository(req.repo_url)
    except GitHubServiceError as exc:
        raise HTTPException(status_code=exc.status_code or 400, detail=exc.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected GitHub retrieval error: {exc}")

    # 2. Create Project Record
    project = proj_repo.create(
        name=repo_info.repo,
        repo_url=repo_info.html_url,
        demo_url=req.demo_url,
        user_notes=req.user_notes,
        readme_content=repo_info.readme_content,
    )
    proj_repo.update_status(project.id, ProjectStatus.ANALYZING)

    # 3. Demo Inspection (if provided)
    demo_obs = None
    if req.demo_url and req.demo_url.strip():
        inspector = DemoInspector()
        demo_obs = await inspector.inspect(
            url=req.demo_url.strip(), capture_screenshot=True, project_id=project.id
        )

    # 4. Optional Web Research
    web_items = None
    if req.enable_web_research:
        search_service = WebResearchService()
        search_key = credentials.get_credential("search_api_key")
        settings_rec = SettingsRepository(db).get_or_create()
        search_provider = settings_rec.preferences.get("search_provider", "none")
        if search_provider != "none":
            query = f"{repo_info.repo} {repo_info.language or ''} documentation features"
            results = await search_service.search(query, provider=search_provider, api_key=search_key)
            web_items = search_service.to_evidence_items(results)

    # 5. Compile Evidence Pack
    evidence_pack = EvidenceEngine.compile_evidence_pack(
        project=project,
        repo_info=repo_info,
        demo_obs=demo_obs,
        web_items=web_items,
    )

    # 6. Persist Evidence Records
    for item in evidence_pack.items:
        ev_repo.add(
            project_id=project.id,
            source_type=item.source_type,
            content=item.content,
            category=item.category,
            source_url=item.source_url,
            verification_status=item.verification_status,
        )

    proj_repo.update_status(project.id, ProjectStatus.ANALYZED)
    summary = EvidenceEngine.build_structured_summary(evidence_pack)

    return {
        "status": "success",
        "project_id": project.id,
        "name": project.name,
        "repo_url": project.repo_url,
        "demo_url": project.demo_url,
        "summary": summary,
        "screenshot_path": demo_obs.screenshot_path if demo_obs else None,
    }


@router.get("")
async def list_projects(db: Session = Depends(get_db)):
    """List all analyzed projects."""
    proj_repo = ProjectRepository(db)
    projects = proj_repo.list_all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "repo_url": p.repo_url,
            "demo_url": p.demo_url,
            "status": p.status.value,
            "created_at": p.created_at.isoformat(),
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(project_id: int, db: Session = Depends(get_db)):
    """Retrieve full details, evidence items, and draft versions for a project."""
    proj_repo = ProjectRepository(db)
    ev_repo = EvidenceRepository(db)
    draft_repo = DraftRepository(db)

    project = proj_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    evidence = ev_repo.list_for_project(project_id)
    drafts = draft_repo.list_for_project(project_id)

    return {
        "id": project.id,
        "name": project.name,
        "repo_url": project.repo_url,
        "demo_url": project.demo_url,
        "user_notes": project.user_notes,
        "status": project.status.value,
        "created_at": project.created_at.isoformat(),
        "evidence": [
            {
                "id": e.id,
                "source_type": e.source_type,
                "content": e.content,
                "category": e.category,
                "source_url": e.source_url,
                "verification_status": e.verification_status,
            }
            for e in evidence
        ],
        "drafts": [
            {
                "id": d.id,
                "version": d.version,
                "body": d.body,
                "style": d.style,
                "status": d.status.value,
                "screenshot_path": d.screenshot_path,
                "created_at": d.created_at.isoformat(),
            }
            for d in drafts
        ],
    }


@router.get("/{project_id}/available-media")
async def get_project_available_media(project_id: int, db: Session = Depends(get_db)):
    """Retrieve all available system photos, videos, repo images, and demo screenshots for a project."""
    proj_repo = ProjectRepository(db)
    ev_repo = EvidenceRepository(db)

    project = proj_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    evidence = ev_repo.list_for_project(project_id)
    available: list[dict[str, Any]] = []
    seen_urls = set()

    # 1. Evidence items categorized as media or containing screenshots
    for e in evidence:
        url = e.source_url
        if not url:
            continue
        if e.category == "media" or "screenshot" in e.content.lower() or "image" in e.content.lower() or "video" in e.content.lower():
            if url not in seen_urls:
                seen_urls.add(url)
                is_video = any(url.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm", ".mkv"])
                source_label = "Demo Screenshot" if e.source_type == "demo" else "Repository Asset"
                title = e.content.replace("Repository Media Asset: ", "").replace("Observed Demo Screenshot: ", "")
                available.append({
                    "title": title[:60],
                    "url": url,
                    "source": source_label,
                    "is_video": is_video,
                })

    # 2. Local Demo screenshots in data/screenshots
    screenshots_dir = settings.SCREENSHOTS_DIR
    if screenshots_dir.exists():
        for p in screenshots_dir.glob(f"*{project_id}*"):
            if p.is_file() and any(p.name.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                raw_path = f"data/screenshots/{p.name}"
                if raw_path not in seen_urls:
                    seen_urls.add(raw_path)
                    available.append({
                        "title": f"Demo Screenshot ({p.name})",
                        "url": raw_path,
                        "source": "Demo Screenshot",
                        "is_video": False,
                    })

    # 3. Uploaded media in data/media
    media_dir = settings.DATA_DIR / "media"
    if media_dir.exists():
        for p in sorted(media_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)[:15]:
            if p.is_file():
                ext = p.suffix.lower()
                is_video = ext in MediaService.ALLOWED_VIDEO_EXTENSIONS
                is_image = ext in MediaService.ALLOWED_IMAGE_EXTENSIONS
                if is_video or is_image:
                    raw_path = f"data/media/{p.name}"
                    if raw_path not in seen_urls:
                        seen_urls.add(raw_path)
                        available.append({
                            "title": p.name,
                            "url": raw_path,
                            "source": "Uploaded Media",
                            "is_video": is_video,
                        })

    return available


@router.post("/{project_id}/drafts")
async def generate_draft_for_project(
    project_id: int, req: GenerateDraftRequest, db: Session = Depends(get_db)
):
    """Generate a LinkedIn post draft using the active AI inference engine."""
    proj_repo = ProjectRepository(db)
    ev_repo = EvidenceRepository(db)
    draft_repo = DraftRepository(db)
    settings_repo = SettingsRepository(db)

    project = proj_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    evidence_items = ev_repo.list_for_project(project_id)
    settings_rec = settings_repo.get_or_create()

    # Ensure full README content is available
    readme_content = project.readme_content
    if not readme_content and project.repo_url:
        try:
            gh_token = credentials.get_credential("github_pat")
            gh_client = GitHubClient(token=gh_token)
            readme_content = await gh_client.fetch_readme(project.repo_url)
            if readme_content:
                proj_repo.update_readme(project.id, readme_content)
                project.readme_content = readme_content
        except Exception as exc:
            logger.warning("Could not auto-fetch README for draft generation: %s", exc)

    # Reconstruct evidence pack
    from src.publisher.services.ai.base import EvidenceItem, EvidencePack

    pack = EvidencePack(
        project_name=project.name,
        repo_url=project.repo_url,
        demo_url=project.demo_url,
        user_notes=project.user_notes,
        readme_content=readme_content,
        items=[
            EvidenceItem(
                source_type=e.source_type,  # type: ignore
                content=e.content,
                category=e.category,
                source_url=e.source_url,
                verification_status=e.verification_status,  # type: ignore
            )
            for e in evidence_items
        ],
    )

    # Preferences
    prefs_dict = settings_rec.preferences or {}
    preferences = PostPreferences(
        style=req.style or prefs_dict.get("style", "professional"),
        language=prefs_dict.get("language", "English"),
        target_audience=prefs_dict.get("target_audience", "Software Engineers, Tech Leads"),
        max_length=prefs_dict.get("max_length", 2000),
        custom_instructions=req.custom_instructions or prefs_dict.get("custom_instructions", ""),
        hashtag_prefs=prefs_dict.get("hashtag_prefs", "#Python #OpenSource"),
        include_links=prefs_dict.get("include_links", True),
        include_screenshot=prefs_dict.get("include_screenshot", True),
    )

    # Provider Router
    router_inst = AIProviderRouter(settings_rec, credential_resolver=credentials.get_credential)
    try:
        provider = router_inst.get_active_provider()
        draft_output = await provider.generate_linkedin_draft(pack, preferences)
    except Exception as exc:
        logger.error("AI Generation error: %s", exc)
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(exc)}")

    # Locate screenshot or media if available
    screenshot_path = None
    if preferences.include_screenshot:
        # Check if project has an observed screenshot or media asset
        for ev in evidence_items:
            if ev.source_type == "demo" and ("screenshot" in ev.content.lower() or ev.category == "media"):
                screenshot_path = ev.source_url
                break
        if not screenshot_path:
            for ev in evidence_items:
                if ev.category == "media" and ev.source_url:
                    screenshot_path = ev.source_url
                    break

    # Save Draft in SQLite
    draft = draft_repo.create(
        project_id=project.id,
        body=draft_output.post_text,
        style=preferences.style,
        post_metadata={
            "hashtags": draft_output.hashtags,
            "project_links": draft_output.project_links,
            "evidence_references": draft_output.evidence_references,
            "unverified_cautions": draft_output.unverified_cautions,
            "ai_mode": settings_rec.active_ai_mode,
        },
        screenshot_path=screenshot_path,
    )

    # Link evidence
    draft_repo.link_evidence(draft.id, [e.id for e in evidence_items])

    return {
        "status": "success",
        "draft_id": draft.id,
        "version": draft.version,
        "body": draft.body,
        "style": draft.style,
        "state": draft.status.value,
        "metadata": draft.post_metadata,
        "repo_url": project.repo_url,
        "demo_url": project.demo_url,
        "screenshot_path": draft.screenshot_path,
    }

