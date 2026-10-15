"""SQLAlchemy database models for projects, evidence, drafts, settings, and history."""

from datetime import datetime, timezone
import enum
from typing import Any
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.publisher.db.connection import Base


def utc_now() -> datetime:
    """Return current timestamp in UTC timezone."""
    return datetime.now(timezone.utc)


class ProjectStatus(str, enum.Enum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"


class DraftStatus(str, enum.Enum):
    GENERATED = "GENERATED"
    VALIDATED = "VALIDATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PUBLISH_FAILED = "PUBLISH_FAILED"


class PublishingState(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class Project(Base):
    """Project entity representing a GitHub repository analyzed for LinkedIn posts."""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    demo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.CREATED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    evidence_items: Mapped[list["ProjectEvidence"]] = relationship(
        "ProjectEvidence", back_populates="project", cascade="all, delete-orphan"
    )
    drafts: Mapped[list["Draft"]] = relationship(
        "Draft", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectEvidence(Base):
    """Extracted evidence units from README, demo observations, user notes, or web research."""
    __tablename__ = "project_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # readme, demo, user_notes, web
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general")  # feature, tech, caution, purpose
    verification_status: Mapped[str] = mapped_column(
        String(50), default="documented"
    )  # documented, observed, user_supplied, unverified
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="evidence_items")
    draft_links: Mapped[list["DraftSource"]] = relationship(
        "DraftSource", back_populates="evidence", cascade="all, delete-orphan"
    )


class Draft(Base):
    """Generated or edited LinkedIn post draft."""
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str] = mapped_column(String(50), default="professional")
    post_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[DraftStatus] = mapped_column(
        Enum(DraftStatus), default=DraftStatus.GENERATED, nullable=False, index=True
    )
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="drafts")
    sources: Mapped[list["DraftSource"]] = relationship(
        "DraftSource", back_populates="draft", cascade="all, delete-orphan"
    )
    publishing_history: Mapped[list["PublishingHistory"]] = relationship(
        "PublishingHistory", back_populates="draft", cascade="all, delete-orphan"
    )


class DraftSource(Base):
    """Many-to-many relationship linking specific drafts to supporting evidence items."""
    __tablename__ = "draft_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project_evidence.id", ondelete="CASCADE"), nullable=False, index=True
    )

    draft: Mapped["Draft"] = relationship("Draft", back_populates="sources")
    evidence: Mapped["ProjectEvidence"] = relationship("ProjectEvidence", back_populates="draft_links")


class SettingsRecord(Base):
    """Non-secret application configuration persisted locally."""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_ai_mode: Mapped[str] = mapped_column(String(20), default="cloud")  # strictly cloud or local
    cloud_provider: Mapped[str] = mapped_column(String(50), default="openai")
    cloud_model: Mapped[str] = mapped_column(String(100), default="gpt-4o-mini")
    cloud_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    local_model_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    local_context_length: Mapped[int] = mapped_column(Integer, default=4096)
    local_gpu_layers: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class IntegrationRecord(Base):
    """Non-secret integration state metadata."""
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # github, linkedin, search
    status: Mapped[str] = mapped_column(String(50), default="disconnected")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublishingHistory(Base):
    """Audit log of publishing submissions and outcomes."""
    __tablename__ = "publishing_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    linkedin_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[PublishingState] = mapped_column(
        Enum(PublishingState), default=PublishingState.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sanitized_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    draft: Mapped["Draft"] = relationship("Draft", back_populates="publishing_history")
