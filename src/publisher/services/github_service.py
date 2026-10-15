"""Official GitHub REST API integration for repository metadata and README retrieval."""

import base64
import re
from typing import Any
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, Field
from src.publisher.core.logging_config import logger


class GitHubRepoInfo(BaseModel):
    """Structured representation of repository metadata and README contents."""

    owner: str
    repo: str
    full_name: str
    description: str | None = None
    html_url: str
    default_branch: str = "main"
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    topics: list[str] = Field(default_factory=list)
    license_name: str | None = None
    language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    primary_programming_language: str | None = None
    detected_technologies: list[str] = Field(default_factory=list)
    repo_media_urls: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    readme_content: str | None = None
    has_readme: bool = False


class GitHubServiceError(Exception):
    """Custom exception with user-facing actionable error message."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def parse_github_url(url: str) -> tuple[str, str]:
    """Parse and validate a GitHub repository URL into (owner, repo).

    Accepts formats such as:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/
    - https://github.com/owner/repo/tree/main

    Rejects non-GitHub domains and malformed paths.
    """
    if not url or not isinstance(url, str):
        raise GitHubServiceError("A valid GitHub repository URL is required.")

    cleaned = url.strip()
    parsed = urlparse(cleaned)

    if parsed.scheme.lower() not in {"http", "https"}:
        raise GitHubServiceError(f"Invalid URL scheme '{parsed.scheme}'. Must be 'https'.")

    netloc = parsed.netloc.lower()
    if netloc != "github.com" and not netloc.endswith(".github.com"):
        raise GitHubServiceError(f"URL host must be 'github.com', got '{parsed.netloc}'")

    # Match /owner/repo from path
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise GitHubServiceError(
            "Invalid GitHub repository URL path. Expected format: 'https://github.com/owner/repository'"
        )

    owner = path_parts[0]
    repo = path_parts[1]

    # Remove trailing .git
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Validate characters (GitHub username/repo constraints)
    if not re.match(r"^[A-Za-z0-9_\-\.]+$", owner) or not re.match(r"^[A-Za-z0-9_\-\.]+$", repo):
        raise GitHubServiceError(f"Invalid characters in repository path: {owner}/{repo}")

    return owner, repo


class GitHubClient:
    """Client for querying GitHub REST API v3."""

    def __init__(self, token: str | None = None, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHubLinkedInAIPublisher/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def fetch_repository(self, url: str) -> GitHubRepoInfo:
        """Fetch repository metadata and README from official GitHub API."""
        owner, repo = parse_github_url(url)
        logger.info("Fetching GitHub repository details for %s/%s", owner, repo)

        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. Fetch metadata
            repo_api_url = f"{self.base_url}/repos/{owner}/{repo}"
            try:
                res = await client.get(repo_api_url, headers=self._get_headers())
            except httpx.TimeoutException:
                raise GitHubServiceError(
                    f"Connection timed out while reaching GitHub API for '{owner}/{repo}'. Please check your network."
                )
            except httpx.RequestError as exc:
                raise GitHubServiceError(f"Network error contacting GitHub API: {exc}")

            if res.status_code == 404:
                raise GitHubServiceError(
                    f"Repository '{owner}/{repo}' not found. Verify the URL, or supply a GitHub Personal Access Token if it is a private repository.",
                    status_code=404,
                )
            elif res.status_code == 403:
                # Check for rate limit
                rate_remaining = res.headers.get("x-ratelimit-remaining")
                if rate_remaining == "0":
                    reset_time = res.headers.get("x-ratelimit-reset", "soon")
                    raise GitHubServiceError(
                        f"GitHub API unauthenticated rate limit reached (resets at {reset_time}). Add a GitHub PAT in Settings to increase limit to 5,000 req/hr.",
                        status_code=403,
                    )
                raise GitHubServiceError(
                    f"Access forbidden to '{owner}/{repo}'. Ensure proper permissions.", status_code=403
                )
            elif res.status_code == 401:
                raise GitHubServiceError(
                    "Invalid GitHub credentials or expired token. Please update your token in Settings.",
                    status_code=401,
                )
            elif res.status_code >= 400:
                raise GitHubServiceError(
                    f"GitHub API error ({res.status_code}): {res.text[:200]}", status_code=res.status_code
                )

            data = res.json()

            # 2. Fetch README
            readme_api_url = f"{self.base_url}/repos/{owner}/{repo}/readme"
            readme_content: str | None = None
            has_readme = False

            try:
                readme_res = await client.get(readme_api_url, headers=self._get_headers())
                if readme_res.status_code == 200:
                    readme_data = readme_res.json()
                    raw_content = readme_data.get("content", "")
                    encoding = readme_data.get("encoding", "")
                    if encoding == "base64" and raw_content:
                        # Decode base64 bytes to utf-8 string
                        decoded_bytes = base64.b64decode(raw_content)
                        readme_content = decoded_bytes.decode("utf-8", errors="replace")
                        has_readme = True
                    elif raw_content:
                        readme_content = raw_content
                        has_readme = True
                elif readme_res.status_code == 404:
                    logger.info("Repository %s/%s does not contain a README.md file via API.", owner, repo)
            except Exception as exc:
                logger.warning("Could not fetch README for %s/%s: %s", owner, repo, exc)

            # Fallback: fetch raw README if API didn't retrieve it
            if not readme_content:
                default_b = data.get("default_branch", "main")
                for branch in (default_b, "main", "master"):
                    try:
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
                        raw_res = await client.get(raw_url, headers={"User-Agent": "Build2Buzz/1.0"})
                        if raw_res.status_code == 200 and raw_res.text.strip():
                            readme_content = raw_res.text
                            has_readme = True
                            logger.info("Retrieved README for %s/%s via raw fallback (%s)", owner, repo, branch)
                            break
                    except Exception as raw_exc:
                        logger.debug("Raw fallback README fetch failed: %s", raw_exc)

            license_name = None
            if data.get("license") and isinstance(data["license"], dict):
                license_name = data["license"].get("name") or data["license"].get("spdx_id")

            # 3. Fetch all languages breakdown
            languages: dict[str, int] = {}
            primary_prog_lang: str | None = None
            try:
                lang_api_url = f"{self.base_url}/repos/{owner}/{repo}/languages"
                lang_res = await client.get(lang_api_url, headers=self._get_headers())
                if lang_res.status_code == 200 and isinstance(lang_res.json(), dict):
                    raw_langs = lang_res.json()
                    languages = {
                        str(k): int(v)
                        for k, v in raw_langs.items()
                        if isinstance(v, (int, float)) and not isinstance(v, bool)
                    }
            except Exception as exc:
                logger.warning("Could not fetch languages for %s/%s: %s", owner, repo, exc)

            # Determine primary programming language (prioritize non-markup logic languages)
            markup_and_style = {"HTML", "CSS", "SCSS", "Sass", "Less", "Stylus", "Jupyter Notebook", "Makefile", "Dockerfile", "TeX"}
            if languages:
                sorted_langs = sorted(languages.items(), key=lambda x: x[1], reverse=True)
                for lang_name, _ in sorted_langs:
                    if lang_name not in markup_and_style:
                        primary_prog_lang = lang_name
                        break
                if not primary_prog_lang and sorted_langs:
                    primary_prog_lang = sorted_langs[0][0]
            if not primary_prog_lang:
                primary_prog_lang = data.get("language")

            # 4. Inspect repository contents & detect technologies / media
            detected_technologies: set[str] = set()
            repo_media_urls: list[dict[str, Any]] = []

            if primary_prog_lang:
                detected_technologies.add(primary_prog_lang)

            try:
                contents_api_url = f"{self.base_url}/repos/{owner}/{repo}/contents"
                contents_res = await client.get(contents_api_url, headers=self._get_headers())
                if contents_res.status_code == 200 and isinstance(contents_res.json(), list):
                    root_items = contents_res.json()
                    root_names = {item.get("name"): item for item in root_items if isinstance(item, dict)}

                    if "manage.py" in root_names:
                        detected_technologies.add("Django")
                    if "db.sqlite3" in root_names:
                        detected_technologies.add("SQLite")
                    if any(k in root_names for k in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml")):
                        detected_technologies.add("Docker")
                    if "package.json" in root_names:
                        detected_technologies.add("Node.js")

                    # Check requirements.txt or pyproject.toml
                    dep_file = root_names.get("requirements.txt") or root_names.get("pyproject.toml")
                    if dep_file and dep_file.get("download_url"):
                        try:
                            dep_res = await client.get(dep_file["download_url"])
                            if dep_res.status_code == 200:
                                dep_text = dep_res.text.lower()
                                known_python_libs = {
                                    "django": "Django",
                                    "fastapi": "FastAPI",
                                    "flask": "Flask",
                                    "celery": "Celery",
                                    "redis": "Redis",
                                    "psycopg2": "PostgreSQL",
                                    "psycopg": "PostgreSQL",
                                    "asyncpg": "PostgreSQL",
                                    "sqlalchemy": "SQLAlchemy",
                                    "torch": "PyTorch",
                                    "tensorflow": "TensorFlow",
                                    "pandas": "Pandas",
                                    "numpy": "NumPy",
                                    "scikit-learn": "Scikit-Learn",
                                    "pydantic": "Pydantic",
                                    "httpx": "HTTPX",
                                    "stripe": "Stripe",
                                    "pillow": "Pillow",
                                    "channels": "Django Channels (WebSockets)",
                                    "pytest": "Pytest",
                                }
                                for lib_key, lib_name in known_python_libs.items():
                                    if re.search(r"\b" + re.escape(lib_key) + r"\b", dep_text):
                                        detected_technologies.add(lib_name)
                        except Exception:
                            pass

                    # Scan for images in static/images, assets, or screenshots folders
                    image_dirs = ["static/images", "assets", "screenshots", "images", "docs/images"]
                    for img_dir in image_dirs:
                        if len(repo_media_urls) >= 12:
                            break
                        try:
                            dir_url = f"{self.base_url}/repos/{owner}/{repo}/contents/{img_dir}"
                            dir_res = await client.get(dir_url, headers=self._get_headers())
                            if dir_res.status_code == 200 and isinstance(dir_res.json(), list):
                                for f in dir_res.json():
                                    fname = f.get("name", "")
                                    furl = f.get("download_url") or f.get("html_url")
                                    if fname and furl and any(fname.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                                        repo_media_urls.append({
                                            "title": fname,
                                            "url": furl,
                                            "type": "image",
                                            "path": f"{img_dir}/{fname}",
                                        })
                                        if len(repo_media_urls) >= 12:
                                            break
                        except Exception:
                            continue
            except Exception as exc:
                logger.warning("Could not inspect repo contents for %s/%s: %s", owner, repo, exc)

            # Scan README for keywords & images
            if readme_content:
                known_keywords = {
                    "django": "Django",
                    "fastapi": "FastAPI",
                    "flask": "Flask",
                    "postgresql": "PostgreSQL",
                    "postgres": "PostgreSQL",
                    "mysql": "MySQL",
                    "sqlite": "SQLite",
                    "redis": "Redis",
                    "mongodb": "MongoDB",
                    "docker": "Docker",
                    "kubernetes": "Kubernetes",
                    "graphql": "GraphQL",
                    "rest api": "REST API",
                    "websockets": "WebSockets",
                    "celery": "Celery",
                    "react": "React",
                    "next.js": "Next.js",
                    "vue": "Vue",
                    "tailwind": "Tailwind CSS",
                    "bootstrap": "Bootstrap",
                    "pytorch": "PyTorch",
                    "tensorflow": "TensorFlow",
                    "jwt": "JWT Authentication",
                    "stripe": "Stripe",
                }
                readme_lower = readme_content.lower()
                for kw, display_name in known_keywords.items():
                    if re.search(r"\b" + re.escape(kw) + r"\b", readme_lower):
                        detected_technologies.add(display_name)

                # Scan markdown image links
                img_matches = re.findall(r"!\[(.*?)\]\(([^\)\s]+)\)", readme_content)
                for alt, url_or_path in img_matches:
                    clean_path = url_or_path.strip()
                    if any(clean_path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif"]):
                        if clean_path.startswith("http://") or clean_path.startswith("https://"):
                            img_url = clean_path
                        else:
                            clean_rel = clean_path.lstrip("./")
                            branch = data.get("default_branch", "main")
                            img_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{clean_rel}"
                        repo_media_urls.append({
                            "title": alt or Path(clean_path).name or "Repository Screenshot",
                            "url": img_url,
                            "type": "image",
                            "path": clean_path,
                        })

            return GitHubRepoInfo(
                owner=owner,
                repo=repo,
                full_name=data.get("full_name", f"{owner}/{repo}"),
                description=data.get("description"),
                html_url=data.get("html_url", url),
                default_branch=data.get("default_branch", "main"),
                stars=data.get("stargazers_count", 0),
                forks=data.get("forks_count", 0),
                open_issues=data.get("open_issues_count", 0),
                topics=data.get("topics", []),
                license_name=license_name,
                language=data.get("language"),
                languages=languages,
                primary_programming_language=primary_prog_lang,
                detected_technologies=sorted(list(detected_technologies)),
                repo_media_urls=repo_media_urls,
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                readme_content=readme_content,
                has_readme=has_readme,
            )

    async def fetch_readme(self, url: str) -> str | None:
        """Fetch raw or API README content for a repository URL."""
        owner, repo = parse_github_url(url)
        readme_api_url = f"{self.base_url}/repos/{owner}/{repo}/readme"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                readme_res = await client.get(readme_api_url, headers=self._get_headers())
                if readme_res.status_code == 200:
                    readme_data = readme_res.json()
                    raw_content = readme_data.get("content", "")
                    encoding = readme_data.get("encoding", "")
                    if encoding == "base64" and raw_content:
                        return base64.b64decode(raw_content).decode("utf-8", errors="replace")
                    elif raw_content:
                        return raw_content
            except Exception as exc:
                logger.debug("Could not fetch README via API for %s/%s: %s", owner, repo, exc)

            for branch in ("main", "master"):
                try:
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
                    raw_res = await client.get(raw_url, headers={"User-Agent": "Build2Buzz/1.0"})
                    if raw_res.status_code == 200 and raw_res.text.strip():
                        return raw_res.text
                except Exception:
                    pass
        return None

