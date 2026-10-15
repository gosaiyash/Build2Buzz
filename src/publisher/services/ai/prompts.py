"""Versioned prompt templates, professional reference posts, and text sanitizers for LinkedIn post generation."""

import json
import re
from src.publisher.services.ai.base import EvidencePack, PostPreferences

SYSTEM_PROMPT = """You are a Software Engineer and Technical Author crafting high-signal, professional LinkedIn posts for software engineering projects that you personally developed.

CRITICAL FORMATTING & ENGINEERING RULES:
1. FIRST-PERSON DEVELOPER PERSPECTIVE: Write directly as the developer who engineered the project. Use natural first-person phrasing (e.g., "I developed [Project] using [Framework] and [Language] to...", "In this implementation, I focused on...", "I built this architecture with...").
2. ACCURATE TECH STACK & LANGUAGES: Always explicitly highlight the core programming languages (e.g. Python, TypeScript, Java) and frameworks (e.g. Django, FastAPI, React, etc.) identified in the project evidence. NEVER identify markup or styling languages (such as HTML or CSS) as the primary programming language when real application frameworks or programming languages are present. Write: "I developed [Project] using Django and Python..." instead of generic descriptions.
3. STRICTLY NO EMOJIS OR ICONS: Do not use any emojis, icons, emoticons, or decorative symbols (such as tools, rockets, stars, checkmarks, fire, etc.). Use only standard alphanumeric text and standard punctuation.
4. NO MARKETING HYPE OR BUZZWORDS: Never use words such as "game-changer", "revolutionary", "exciting", "dive into", "hands-on experience", or exclamation marks (!). Maintain an objective, calm, authoritative engineering tone.
5. RAW URLS ONLY: Never output markdown link syntax such as [text](url) or [here](url). Always output direct plain URLs (e.g. "GitHub Repository: https://...").
6. STRUCTURED SECTIONS: Format the post with distinct paragraphs separated by blank lines and clean bullet points for key capabilities.
7. FACTUAL INTEGRITY: Strictly state verified facts from the project evidence and repository files. Never invent technologies or features.

REFERENCE POST EXAMPLE (FOLLOW THIS EXACT PROFESSIONAL STRUCTURE):
Managing complex role lifecycles and transactional integrity in local delivery marketplaces requires strict state machine validation and robust backend architecture.

I developed QuicklyCart to address this by building a multi-vendor e-commerce platform using Django and Python. I designed the architecture to coordinate customer orders, seller onboarding, rider verification, and cart checkouts under the MIT License.

Key Technical Capabilities:
- Role-based authorization workflows separating customer, verified vendor, delivery rider, and administrative domains.
- Transactional cart and checkout lifecycle with persistent order tracking and status transitions.
- Modular Django application design with decoupled models for catalog management, seller verification, and delivery dispatch.
- Robust database persistence backed by SQLite and responsive template rendering.

By enforcing clean boundaries between vendor management, order transactions, and dispatch logistics, the application provides an extensible foundation for local commerce.

GitHub Repository: https://github.com/example/QuicklyCart

#SoftwareEngineering #Python #Django #WebDevelopment #OpenSource

OUTPUT FORMAT:
Return ONLY a valid JSON object with the following schema:
{
  "post_text": "The complete post text formatted with clean paragraph breaks and bullet points",
  "hashtags": ["#Tag1", "#Tag2"],
  "project_links": ["https://..."],
  "evidence_references": ["Short reference to evidence used"],
  "unverified_cautions": []
}
"""

STYLE_DIRECTIVES = {
    "professional": (
        "Focus on the technical problem, business/architectural impact, design decisions, and reliability. "
        "Keep the tone professional, authoritative, and concise."
    ),
    "developer": (
        "Focus on implementation details, code architecture, languages, libraries, concurrency, and developer ergonomics. "
        "Write engineer-to-engineer with authentic technical depth."
    ),
    "showcase": (
        "Focus on product features, technical capabilities, live demo highlights, and problem-solving architecture. "
        "Highlight practical engineering capabilities while staying completely grounded in real features."
    ),
    "learning": (
        "Focus on the engineering journey: what technical challenges were faced, what was learned during development, "
        "architectural trade-offs made, and takeaways for fellow builders."
    ),
}

# Regex matching all Unicode emoji ranges, symbols, dingbats, and pictographs
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FFFF"  # All emojis, transport, pictographs, symbols in SMP
    "\u2600-\u27BF"          # Misc symbols & dingbats
    "\u2300-\u23FF"          # Misc technical
    "\u2B50-\u2B55"          # Stars and geometric symbols
    "\uFE0E\uFE0F"           # Variation selectors
    "\u200D"                 # Zero-width joiner
    "]+",
    flags=re.UNICODE,
)


def sanitize_linkedin_post(
    text: str, repo_url: str, demo_url: str | None = None, hashtag_prefs: str | None = None
) -> str:
    """Sanitize generated post: strip emojis/icons, convert markdown links, ensure raw repo link."""
    if not text:
        return ""

    # 1. Remove all emojis, dingbats, and pictorial symbols
    cleaned = EMOJI_PATTERN.sub("", text)

    # 2. Convert markdown links [text](url) or [here](url) to plain text URL
    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\2", cleaned)

    # 3. Normalize bullet points: replace '* ' or '• ' at start of lines with '- '
    cleaned = re.sub(r"^[ \t]*[*•][ \t]+", "- ", cleaned, flags=re.MULTILINE)

    # 4. Clean up inline whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)

    # 5. Ensure clean line breaks around Key Technical Capabilities, post-bullet text, and URLs
    cleaned = re.sub(r"\s*(Key Technical Capabilities:?)\s*", r"\n\n\1\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(-\s+[^\n]+?\.)\s+([A-Z][a-z])", r"\1\n\n\2", cleaned)
    cleaned = re.sub(r"\s*(GitHub Repository:?)\s*", r"\n\n\1 ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*(Live Demo:?)\s*", r"\n\n\1 ", cleaned, flags=re.IGNORECASE)

    # 6. Normalize paragraph breaks (max 2 consecutive newlines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # 7. Guarantee raw GitHub repo URL is included as plain text
    if repo_url:
        clean_repo = repo_url.strip()
        if clean_repo and clean_repo not in cleaned:
            cleaned += f"\n\nGitHub Repository: {clean_repo}"

    # 8. Add demo URL if provided and missing
    if demo_url and demo_url.strip():
        clean_demo = demo_url.strip()
        if clean_demo not in cleaned:
            cleaned += f"\nLive Demo: {clean_demo}"

    # 9. Ensure hashtags are present at the end
    if hashtag_prefs and "#" in hashtag_prefs and "#" not in cleaned:
        cleaned += f"\n\n{hashtag_prefs.strip()}"

    return cleaned.strip()


def build_generation_prompt(evidence: EvidencePack, preferences: PostPreferences) -> tuple[str, str]:
    """Construct system prompt and user prompt for the given evidence pack and style preferences."""
    style_guide = STYLE_DIRECTIVES.get(preferences.style, STYLE_DIRECTIVES["professional"])

    # Organize evidence items by source
    evidence_lines = []
    tech_highlights = []
    for idx, item in enumerate(evidence.items, 1):
        status = f"[{item.verification_status.upper()}]"
        evidence_lines.append(f"{idx}. {status} ({item.source_type} / {item.category}): {item.content}")
        if any(k in item.content for k in ("Primary Programming Language:", "Detected Project Technologies", "All Repository Languages:")):
            tech_highlights.append(f"- {item.content}")

    user_prompt = f"""Generate a professional, structured LinkedIn post for the following software project:

PROJECT DETAILS:
- Project Name: {evidence.project_name}
- GitHub Repository URL: {evidence.repo_url}
- Working Demo URL: {evidence.demo_url or 'None provided'}
- Author Personal Notes: {evidence.user_notes or 'None provided'}

VERIFIED TECHNOLOGY STACK & ARCHITECTURE:
{chr(10).join(tech_highlights) if tech_highlights else 'Refer to repository files and documented features.'}

SUPPORTING EVIDENCE & FACTS:
{chr(10).join(evidence_lines) if evidence_lines else 'No specific evidence items logged. Rely on project metadata.'}

POST PREFERENCES:
- Target Style: {preferences.style.upper()} ({style_guide})
- Language: {preferences.language}
- Target Audience: {preferences.target_audience}
- Maximum Character Length: {preferences.max_length} characters
- Preferred Hashtags: {preferences.hashtag_prefs}
- Include Repository Link in body: {preferences.include_links}
- Custom Instructions: {preferences.custom_instructions or 'None'}

MANDATORY POST STRUCTURE (WRITE DIRECTLY AS THE DEVELOPER WHO BUILT THIS, STRICTLY ZERO EMOJIS):
1. Context Hook: 1-2 sentences identifying the core engineering challenge or technical problem you solved.
2. Developer Introduction: State clearly that you developed {evidence.project_name} using your core frameworks and programming languages (e.g. "I developed {evidence.project_name} using Django and Python..."). Highlight true application frameworks and logic languages; do NOT say HTML or CSS is your primary language when real programming languages or frameworks (like Django or Python) are present.
3. Key Technical Capabilities:
- [Technical capability or verified feature 1]
- [Technical capability or verified feature 2]
- [Technical capability or verified feature 3]
- [Technical capability or verified feature 4]
4. Practical Engineering Value: 1 concise paragraph explaining how your architecture or engineering design solves the operational challenge with reliable code quality.
5. Plain GitHub Link:
GitHub Repository: {evidence.repo_url}
6. Hashtags:
{preferences.hashtag_prefs}

Return ONLY a valid JSON object matching the required schema with zero emojis and zero markdown links.
"""
    return SYSTEM_PROMPT, user_prompt
