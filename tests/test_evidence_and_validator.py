"""Unit tests for EvidenceEngine and DraftValidator."""

import pytest
from src.publisher.db.models import Draft, DraftStatus, Project
from src.publisher.services.demo_inspector import DemoObservation
from src.publisher.services.evidence_engine import EvidenceEngine
from src.publisher.services.github_service import GitHubRepoInfo
from src.publisher.services.validator import DraftValidator


def test_evidence_engine_extraction():
    """Verify evidence engine parses facts from metadata and readme sections."""
    info = GitHubRepoInfo(
        owner="testowner",
        repo="ai-tool",
        full_name="testowner/ai-tool",
        description="A lightweight AI tool for developers",
        html_url="https://github.com/testowner/ai-tool",
        language="Python",
        topics=["ai", "fastapi"],
        license_name="MIT",
        has_readme=True,
        readme_content="""
# AI Tool
## Features
- Async stream processing
- Offline model support
- Clean JSON output
## Tech Stack
Built with Python 3.11 and FastAPI.
        """,
    )

    items = EvidenceEngine.extract_from_github(info)
    assert len(items) >= 4
    contents = [i.content for i in items]
    assert any("Async stream processing" in c for c in contents)
    assert any("Python" in c for c in contents)

    demo_obs = DemoObservation(
        url="https://demo.example.com",
        page_title="Live AI Tool Demo",
        meta_description="Interactive demonstration",
        visible_text_snippet="Real-time dashboard preview",
        load_success=True,
    )
    demo_items = EvidenceEngine.extract_from_demo(demo_obs)
    assert len(demo_items) == 3


def test_validator_detects_secrets():
    """Verify validator blocks drafts containing leaked API keys."""
    project = Project(
        name="TestApp",
        repo_url="https://github.com/example/test",
    )
    leaked_body = "Check out this app! Use my key sk-abcdef1234567890abcdef123456 for testing."
    draft = Draft(
        project_id=1,
        body=leaked_body,
        status=DraftStatus.GENERATED,
    )

    report = DraftValidator.validate(draft, project)
    assert report.is_valid is False
    assert any("security credential" in err.lower() for err in report.errors)


def test_validator_detects_length_violation():
    """Verify validator blocks drafts exceeding 3,000 characters."""
    project = Project(
        name="TestApp",
        repo_url="https://github.com/example/test",
    )
    huge_body = "a" * 3100
    draft = Draft(
        project_id=1,
        body=huge_body,
        status=DraftStatus.GENERATED,
    )

    report = DraftValidator.validate(draft, project)
    assert report.is_valid is False
    assert any("3,000 character limit" in err for err in report.errors)


def test_validator_warns_on_missing_repo_link():
    """Verify validator produces a warning if repo URL is absent."""
    project = Project(
        name="TestApp",
        repo_url="https://github.com/example/my-repo",
    )
    clean_body = "Just launched an exciting new project! Let me know your thoughts."
    draft = Draft(
        project_id=1,
        body=clean_body,
        status=DraftStatus.GENERATED,
    )

    report = DraftValidator.validate(draft, project)
    assert report.is_valid is True  # Warning does not block validity
    assert any("does not include the github repository link" in w.lower() for w in report.warnings)


def test_validator_warns_on_duplicate_publish():
    """Verify validator detects if identical body was previously published."""
    project = Project(
        name="TestApp",
        repo_url="https://github.com/example/my-repo",
    )
    body = "Here is my project: https://github.com/example/my-repo"
    draft = Draft(
        project_id=1,
        body=body,
        status=DraftStatus.GENERATED,
    )

    report = DraftValidator.validate(
        draft, project, previously_published_bodies=[body]
    )
    assert any("already been published" in w.lower() for w in report.warnings)
