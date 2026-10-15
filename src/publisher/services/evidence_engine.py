"""Evidence compilation engine extracting and structuring facts from GitHub and demo."""

import re
from typing import Any
from src.publisher.db.models import Project
from src.publisher.services.ai.base import EvidenceItem, EvidencePack
from src.publisher.services.demo_inspector import DemoObservation
from src.publisher.services.github_service import GitHubRepoInfo


class EvidenceEngine:
    """Aggregates and categorizes facts from README, demo observations, and user notes."""

    @staticmethod
    def extract_from_github(info: GitHubRepoInfo) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []

        # Description / Purpose
        if info.description:
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"Project Purpose / Description: {info.description}",
                    category="purpose",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        # Primary Programming Language, All Languages & Detected Technologies
        primary_lang = info.primary_programming_language or info.language
        if primary_lang:
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"Primary Programming Language: {primary_lang}",
                    category="technology",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        if info.languages:
            total_bytes = sum(info.languages.values()) or 1
            lang_breakdown = [
                f"{lang} ({round(b / total_bytes * 100)}%)"
                for lang, b in sorted(info.languages.items(), key=lambda x: x[1], reverse=True)
            ]
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"All Repository Languages: {', '.join(lang_breakdown)}",
                    category="technology",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        if info.detected_technologies:
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"Detected Project Technologies & Frameworks: {', '.join(info.detected_technologies)}",
                    category="technology",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        if info.repo_media_urls:
            for media in info.repo_media_urls[:6]:
                items.append(
                    EvidenceItem(
                        source_type="readme",
                        content=f"Repository Media Asset: {media.get('title', 'Screenshot')}",
                        category="media",
                        source_url=media.get("url"),
                        verification_status="documented",
                    )
                )

        if info.topics:
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"Documented Repository Topics: {', '.join(info.topics)}",
                    category="technology",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        if info.license_name:
            items.append(
                EvidenceItem(
                    source_type="readme",
                    content=f"Open Source License: {info.license_name}",
                    category="general",
                    source_url=info.html_url,
                    verification_status="documented",
                )
            )

        # Parse key sections from README
        if info.readme_content:
            readme = info.readme_content
            # Extract features section
            features_match = re.search(
                r"##?\s*(?:Features|Highlights|What it does|Capabilities)(.*?)(?=##|\Z)",
                readme,
                re.DOTALL | re.IGNORECASE,
            )
            if features_match:
                features_text = features_match.group(1).strip()
                # Extract bullet points
                bullets = [b.strip("-* ").strip() for b in features_text.splitlines() if b.strip().startswith(("-", "*"))]
                for bullet in bullets[:8]:
                    if bullet:
                        items.append(
                            EvidenceItem(
                                source_type="readme",
                                content=f"Feature: {bullet}",
                                category="feature",
                                source_url=info.html_url,
                                verification_status="documented",
                            )
                        )

            # Extract tech stack / built with
            tech_match = re.search(
                r"##?\s*(?:Tech Stack|Built With|Technologies|Architecture)(.*?)(?=##|\Z)",
                readme,
                re.DOTALL | re.IGNORECASE,
            )
            if tech_match:
                tech_text = tech_match.group(1).strip()
                items.append(
                    EvidenceItem(
                        source_type="readme",
                        content=f"Documented Tech Stack details: {tech_text[:400]}",
                        category="technology",
                        source_url=info.html_url,
                        verification_status="documented",
                    )
                )

        return items

    @staticmethod
    def extract_from_demo(obs: DemoObservation) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        if not obs.load_success:
            return items

        if obs.page_title:
            items.append(
                EvidenceItem(
                    source_type="demo",
                    content=f"Observed Demo Page Title: '{obs.page_title}'",
                    category="observation",
                    source_url=obs.url,
                    verification_status="observed",
                )
            )

        if obs.meta_description:
            items.append(
                EvidenceItem(
                    source_type="demo",
                    content=f"Demo Meta Description: '{obs.meta_description}'",
                    category="observation",
                    source_url=obs.url,
                    verification_status="observed",
                )
            )

        if obs.visible_text_snippet:
            snippet = obs.visible_text_snippet[:500]
            items.append(
                EvidenceItem(
                    source_type="demo",
                    content=f"Observed Visible Interface Text: {snippet}",
                    category="observation",
                    source_url=obs.url,
                    verification_status="observed",
                )
            )

        if obs.screenshot_path:
            items.append(
                EvidenceItem(
                    source_type="demo",
                    content=f"Observed Demo Screenshot: {obs.screenshot_path}",
                    category="media",
                    source_url=obs.screenshot_path,
                    verification_status="observed",
                )
            )

        return items

    @classmethod
    def compile_evidence_pack(
        cls,
        project: Project,
        repo_info: GitHubRepoInfo,
        demo_obs: DemoObservation | None = None,
        web_items: list[EvidenceItem] | None = None,
    ) -> EvidencePack:
        """Compile a unified evidence pack maintaining source origin and confidence status."""
        items: list[EvidenceItem] = []

        # 1. From GitHub
        items.extend(cls.extract_from_github(repo_info))

        # 2. From Demo
        if demo_obs and demo_obs.load_success:
            items.extend(cls.extract_from_demo(demo_obs))

        # 3. From User Notes
        if project.user_notes:
            items.append(
                EvidenceItem(
                    source_type="user_notes",
                    content=f"Author Developer Note: {project.user_notes}",
                    category="purpose",
                    verification_status="user_supplied",
                )
            )

        # 4. From Web Research (if provided)
        if web_items:
            items.extend(web_items)

        return EvidencePack(
            project_name=project.name,
            repo_url=project.repo_url,
            demo_url=project.demo_url,
            user_notes=project.user_notes,
            readme_content=repo_info.readme_content,
            items=items,
        )

    @staticmethod
    def build_structured_summary(pack: EvidencePack) -> dict[str, Any]:
        """Produce structured project report distinguishing documented facts from observations."""
        documented_facts = [it.content for it in pack.items if it.verification_status == "documented"]
        observed_facts = [it.content for it in pack.items if it.verification_status == "observed"]
        user_facts = [it.content for it in pack.items if it.verification_status == "user_supplied"]
        external_facts = [it.content for it in pack.items if it.verification_status == "external"]

        technologies = [
            it.content.replace("Primary Programming Language: ", "").replace("Documented Repository Topics: ", "")
            for it in pack.items
            if it.category == "technology"
        ]
        features = [
            it.content.replace("Feature: ", "")
            for it in pack.items
            if it.category == "feature"
        ]
        media_assets = [
            {"content": it.content, "url": it.source_url}
            for it in pack.items
            if it.category == "media"
        ]

        return {
            "project_name": pack.project_name,
            "repo_url": pack.repo_url,
            "demo_url": pack.demo_url,
            "documented_facts": documented_facts,
            "observed_facts": observed_facts,
            "user_supplied_facts": user_facts,
            "external_facts": external_facts,
            "technologies": technologies,
            "features": features,
            "media_assets": media_assets,
            "total_evidence_units": len(pack.items),
        }
