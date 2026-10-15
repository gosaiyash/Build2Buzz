"""Repository layer implementing clean CRUD operations and strict state transitions."""

from datetime import datetime, timezone
import uuid
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from src.publisher.db.models import (
    Draft,
    DraftSource,
    DraftStatus,
    IntegrationRecord,
    Project,
    ProjectEvidence,
    ProjectStatus,
    PublishingHistory,
    PublishingState,
    SettingsRecord,
)


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        name: str,
        repo_url: str,
        demo_url: str | None = None,
        user_notes: str | None = None,
    ) -> Project:
        project = Project(
            name=name,
            repo_url=repo_url,
            demo_url=demo_url,
            user_notes=user_notes,
            status=ProjectStatus.CREATED,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get(self, project_id: int) -> Project | None:
        return self.db.get(Project, project_id)

    def list_all(self) -> list[Project]:
        stmt = select(Project).order_by(desc(Project.created_at))
        return list(self.db.scalars(stmt).all())

    def update_status(self, project_id: int, status: ProjectStatus) -> Project:
        project = self.get(project_id)
        if not project:
            raise ValueError(f"Project with ID {project_id} not found.")
        project.status = status
        project.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(project)
        return project


class EvidenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(
        self,
        project_id: int,
        source_type: str,
        content: str,
        category: str = "general",
        source_url: str | None = None,
        verification_status: str = "documented",
    ) -> ProjectEvidence:
        evidence = ProjectEvidence(
            project_id=project_id,
            source_type=source_type,
            content=content,
            category=category,
            source_url=source_url,
            verification_status=verification_status,
        )
        self.db.add(evidence)
        self.db.commit()
        self.db.refresh(evidence)
        return evidence

    def list_for_project(self, project_id: int) -> list[ProjectEvidence]:
        stmt = (
            select(ProjectEvidence)
            .where(ProjectEvidence.project_id == project_id)
            .order_by(ProjectEvidence.id)
        )
        return list(self.db.scalars(stmt).all())

    def clear_for_project(self, project_id: int) -> None:
        stmt = select(ProjectEvidence).where(ProjectEvidence.project_id == project_id)
        items = self.db.scalars(stmt).all()
        for item in items:
            self.db.delete(item)
        self.db.commit()


class DraftRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        project_id: int,
        body: str,
        style: str = "professional",
        post_metadata: dict | None = None,
        screenshot_path: str | None = None,
    ) -> Draft:
        # Determine version
        stmt = (
            select(Draft)
            .where(Draft.project_id == project_id)
            .order_by(desc(Draft.version))
        )
        latest = self.db.scalars(stmt).first()
        next_version = (latest.version + 1) if latest else 1

        draft = Draft(
            project_id=project_id,
            version=next_version,
            body=body,
            style=style,
            post_metadata=post_metadata or {},
            screenshot_path=screenshot_path,
            status=DraftStatus.GENERATED,
        )
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def get(self, draft_id: int) -> Draft | None:
        return self.db.get(Draft, draft_id)

    def list_for_project(self, project_id: int) -> list[Draft]:
        stmt = (
            select(Draft)
            .where(Draft.project_id == project_id)
            .order_by(desc(Draft.version))
        )
        return list(self.db.scalars(stmt).all())

    def update_content(
        self, draft_id: int, body: str, post_metadata: dict | None = None
    ) -> Draft:
        draft = self.get(draft_id)
        if not draft:
            raise ValueError(f"Draft with ID {draft_id} not found.")

        draft.body = body
        if post_metadata is not None:
            draft.post_metadata = post_metadata

        # Crucial state invariant: If the draft was previously APPROVED,
        # editing it invalidates approval and moves it back to NEEDS_REVIEW!
        if draft.status == DraftStatus.APPROVED:
            draft.status = DraftStatus.NEEDS_REVIEW

        draft.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def update_media(self, draft_id: int, screenshot_path: str | None) -> Draft:
        draft = self.get(draft_id)
        if not draft:
            raise ValueError(f"Draft with ID {draft_id} not found.")

        draft.screenshot_path = screenshot_path
        if draft.status == DraftStatus.APPROVED:
            draft.status = DraftStatus.NEEDS_REVIEW

        draft.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def set_status(self, draft_id: int, new_status: DraftStatus) -> Draft:
        draft = self.get(draft_id)
        if not draft:
            raise ValueError(f"Draft with ID {draft_id} not found.")

        # Validate transitions
        # Publishing is strictly forbidden unless draft is APPROVED
        if new_status == DraftStatus.PUBLISHING and draft.status != DraftStatus.APPROVED:
            raise ValueError(
                f"Cannot publish draft in '{draft.status.value}' state. Explicit approval is required."
            )

        draft.status = new_status
        draft.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def link_evidence(self, draft_id: int, evidence_ids: list[int]) -> None:
        for eid in evidence_ids:
            link = DraftSource(draft_id=draft_id, evidence_id=eid)
            self.db.add(link)
        self.db.commit()


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self) -> SettingsRecord:
        stmt = select(SettingsRecord)
        rec = self.db.scalars(stmt).first()
        if not rec:
            rec = SettingsRecord(
                active_ai_mode="cloud",
                cloud_provider="openai",
                cloud_model="gpt-4o-mini",
                preferences={
                    "style": "professional",
                    "language": "English",
                    "max_length": 2000,
                    "include_links": True,
                    "include_screenshot": True,
                },
            )
            self.db.add(rec)
            self.db.commit()
            self.db.refresh(rec)
        return rec

    def update_ai_mode(
        self,
        mode: str,
        cloud_provider: str | None = None,
        cloud_model: str | None = None,
        cloud_base_url: str | None = None,
        local_model_path: str | None = None,
        local_context_length: int | None = None,
        local_gpu_layers: int | None = None,
    ) -> SettingsRecord:
        if mode not in {"cloud", "local"}:
            raise ValueError(f"Mode must be 'cloud' or 'local', got '{mode}'")

        rec = self.get_or_create()
        rec.active_ai_mode = mode
        if cloud_provider:
            rec.cloud_provider = cloud_provider
        if cloud_model:
            rec.cloud_model = cloud_model
        if cloud_base_url is not None:
            rec.cloud_base_url = cloud_base_url
        if local_model_path is not None:
            rec.local_model_path = local_model_path
        if local_context_length is not None:
            rec.local_context_length = local_context_length
        if local_gpu_layers is not None:
            rec.local_gpu_layers = local_gpu_layers

        rec.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(rec)
        return rec


class HistoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def record_submission(self, draft_id: int) -> PublishingHistory:
        submission_id = str(uuid.uuid4())
        record = PublishingHistory(
            draft_id=draft_id,
            submission_id=submission_id,
            status=PublishingState.PENDING,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def record_success(self, submission_id: str, linkedin_post_id: str) -> PublishingHistory:
        stmt = select(PublishingHistory).where(PublishingHistory.submission_id == submission_id)
        record = self.db.scalars(stmt).first()
        if not record:
            raise ValueError(f"Submission {submission_id} not found.")

        record.status = PublishingState.SUCCESS
        record.linkedin_post_id = linkedin_post_id
        record.published_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(record)
        return record

    def record_failure(
        self, submission_id: str, error_category: str, sanitized_error: str
    ) -> PublishingHistory:
        stmt = select(PublishingHistory).where(PublishingHistory.submission_id == submission_id)
        record = self.db.scalars(stmt).first()
        if not record:
            raise ValueError(f"Submission {submission_id} not found.")

        record.status = PublishingState.FAILED
        record.error_category = error_category
        record.sanitized_error = sanitized_error
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_all(self, limit: int = 50) -> list[PublishingHistory]:
        stmt = (
            select(PublishingHistory)
            .order_by(desc(PublishingHistory.created_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
