"""Unit and integration tests for SQLite persistence, models, and repositories."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from src.publisher.db.connection import Base
from src.publisher.db.models import DraftStatus, ProjectStatus, PublishingState
from src.publisher.db.repositories import (
    DraftRepository,
    EvidenceRepository,
    HistoryRepository,
    ProjectRepository,
    SettingsRepository,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database session for testing."""
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_project_crud(db_session: Session):
    """Verify creating, retrieving, and updating a project."""
    repo = ProjectRepository(db_session)
    project = repo.create(
        name="Build2Buzz",
        repo_url="https://github.com/example/build2buzz",
        demo_url="https://demo.example.com",
        user_notes="My notes",
    )
    assert project.id is not None
    assert project.status == ProjectStatus.CREATED

    fetched = repo.get(project.id)
    assert fetched is not None
    assert fetched.name == "Build2Buzz"

    updated = repo.update_status(project.id, ProjectStatus.ANALYZED)
    assert updated.status == ProjectStatus.ANALYZED


def test_evidence_and_draft_cascade(db_session: Session):
    """Verify linking evidence and drafts to project with cascading deletion."""
    proj_repo = ProjectRepository(db_session)
    ev_repo = EvidenceRepository(db_session)
    draft_repo = DraftRepository(db_session)

    project = proj_repo.create("TestRepo", "https://github.com/example/test")
    ev1 = ev_repo.add(project.id, "readme", "FastAPI backend architecture", category="feature")
    ev2 = ev_repo.add(project.id, "demo", "Interactive dashboard loaded", category="observation")

    evidence_list = ev_repo.list_for_project(project.id)
    assert len(evidence_list) == 2

    # Create draft
    draft_v1 = draft_repo.create(project.id, "First version draft", style="developer")
    assert draft_v1.version == 1
    draft_repo.link_evidence(draft_v1.id, [ev1.id, ev2.id])

    # Next draft should have version 2
    draft_v2 = draft_repo.create(project.id, "Second version draft", style="showcase")
    assert draft_v2.version == 2


def test_draft_state_transitions_and_approval_invalidation(db_session: Session):
    """Verify strict state transitions: publishing requires approval, edits invalidate approval."""
    proj_repo = ProjectRepository(db_session)
    draft_repo = DraftRepository(db_session)

    project = proj_repo.create("TestRepo", "https://github.com/example/test")
    draft = draft_repo.create(project.id, "Draft content")

    # Publishing directly from GENERATED must fail
    with pytest.raises(ValueError, match="Cannot publish draft in 'GENERATED' state"):
        draft_repo.set_status(draft.id, DraftStatus.PUBLISHING)

    # Approve draft
    draft_repo.set_status(draft.id, DraftStatus.APPROVED)
    assert draft_repo.get(draft.id).status == DraftStatus.APPROVED

    # Now editing the approved draft must reset status to NEEDS_REVIEW
    updated = draft_repo.update_content(draft.id, "Modified content after approval")
    assert updated.status == DraftStatus.NEEDS_REVIEW

    # Approve again, then publishing is allowed
    draft_repo.set_status(draft.id, DraftStatus.APPROVED)
    publishing = draft_repo.set_status(draft.id, DraftStatus.PUBLISHING)
    assert publishing.status == DraftStatus.PUBLISHING


def test_settings_repository_mode_isolation(db_session: Session):
    """Verify settings repository enforces exclusive modes (cloud vs local)."""
    settings_repo = SettingsRepository(db_session)
    rec = settings_repo.get_or_create()
    assert rec.active_ai_mode == "cloud"

    # Switch to local mode
    updated = settings_repo.update_ai_mode(
        mode="local",
        local_model_path="C:/models/test.gguf",
        local_context_length=8192,
    )
    assert updated.active_ai_mode == "local"
    assert updated.local_model_path == "C:/models/test.gguf"
    assert updated.local_context_length == 8192

    # Invalid mode rejected
    with pytest.raises(ValueError, match="Mode must be 'cloud' or 'local'"):
        settings_repo.update_ai_mode(mode="unknown_mode")


def test_publishing_history(db_session: Session):
    """Verify recording submissions, success, and failure outcomes."""
    proj_repo = ProjectRepository(db_session)
    draft_repo = DraftRepository(db_session)
    hist_repo = HistoryRepository(db_session)

    project = proj_repo.create("TestRepo", "https://github.com/example/test")
    draft = draft_repo.create(project.id, "Draft body")

    # Record submission
    hist = hist_repo.record_submission(draft.id)
    assert hist.status == PublishingState.PENDING
    assert hist.submission_id is not None

    # Record success
    succ = hist_repo.record_success(hist.submission_id, "urn:li:share:123456789")
    assert succ.status == PublishingState.SUCCESS
    assert succ.linkedin_post_id == "urn:li:share:123456789"
    assert succ.published_at is not None

    # Record another failed submission
    hist2 = hist_repo.record_submission(draft.id)
    fail = hist_repo.record_failure(
        hist2.submission_id, "NetworkTimeout", "Failed to reach LinkedIn API"
    )
    assert fail.status == PublishingState.FAILED
    assert fail.error_category == "NetworkTimeout"
