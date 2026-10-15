"""Post draft validation service ensuring factuality, length limits, and secret safeguards."""

from pathlib import Path
import re
from urllib.parse import urlparse
from pydantic import BaseModel, Field
from src.publisher.core.logging_config import SECRET_PATTERNS
from src.publisher.db.models import Draft, DraftStatus, Project


class ValidationReport(BaseModel):
    """Detailed validation analysis for a LinkedIn draft."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    character_count: int = 0
    max_length_limit: int = 3000
    has_repo_link: bool = False
    has_demo_link: bool = False
    is_approved: bool = False


class DraftValidator:
    """Validates generated and edited drafts against LinkedIn and security constraints."""

    LINKEDIN_CHAR_LIMIT = 3000

    @classmethod
    def validate(
        cls,
        draft: Draft,
        project: Project,
        max_configured_length: int = 2500,
        previously_published_bodies: list[str] | None = None,
    ) -> ValidationReport:
        errors: list[str] = []
        warnings: list[str] = []

        body = (draft.body or "").strip()
        char_count = len(body)

        # 1. Non-empty check
        if not body:
            errors.append("Draft post text cannot be empty.")

        # 2. Length check
        if char_count > cls.LINKEDIN_CHAR_LIMIT:
            errors.append(
                f"Post exceeds LinkedIn's 3,000 character limit ({char_count} chars). Please shorten the text."
            )
        elif char_count > max_configured_length:
            warnings.append(
                f"Post character count ({char_count}) exceeds your preferred max length ({max_configured_length})."
            )

        # 3. Project URL inclusion checks
        has_repo = project.repo_url in body
        has_demo = (project.demo_url in body) if project.demo_url else True

        if not has_repo:
            warnings.append(f"Post does not include the GitHub repository link: {project.repo_url}")
        if project.demo_url and not has_demo:
            warnings.append(f"Post does not include the working demo link: {project.demo_url}")

        # 4. Secret / Token disclosure scan
        for pattern in SECRET_PATTERNS:
            if pattern.search(body):
                errors.append(
                    "Potential security credential or API key detected in post body. Please remove it before publishing."
                )
                break

        # Check for generic token markers
        if re.search(r"\b(ghp_[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-\.]{25,})\b", body):
            errors.append("Potential access token or JWT detected in post text.")

        # 5. Media validation
        if draft.screenshot_path:
            p = Path(draft.screenshot_path)
            if not p.exists():
                warnings.append(f"Referenced screenshot file not found on disk: {draft.screenshot_path}")

        # 6. Duplicate publishing check
        if previously_published_bodies:
            for prev_body in previously_published_bodies:
                if body == prev_body.strip():
                    warnings.append(
                        "This exact post body has already been published to LinkedIn previously."
                    )
                    break

        # 7. Unverified claims warning check
        metadata = draft.post_metadata or {}
        unverified_cautions = metadata.get("unverified_cautions", [])
        if unverified_cautions:
            for caution in unverified_cautions:
                warnings.append(f"Caution: {caution}")

        is_valid = len(errors) == 0

        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            character_count=char_count,
            max_length_limit=cls.LINKEDIN_CHAR_LIMIT,
            has_repo_link=has_repo,
            has_demo_link=has_demo,
            is_approved=(draft.status == DraftStatus.APPROVED),
        )
