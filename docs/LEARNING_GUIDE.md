# 🎓 Beginner-Friendly Learning Guide: GitHub LinkedIn AI Publisher

Welcome to the comprehensive learning guide for **GitHub LinkedIn AI Publisher**! 

Whether you are new to FastAPI, browser automation, or on-device AI inference, this guide explains every part of the system in plain English.

---

## 1. Why Did We Choose These Technologies?

| Technology | What it does | Why we chose it |
|---|---|---|
| **Python 3.11** | The core programming language | Ultra-fast execution, robust typing, and broad compatibility with C++ wheels (like `llama-cpp-python`). |
| **FastAPI** | Web framework for our backend | Extremely fast, built-in asynchronous support (`async`/`await`), and automatic OpenAPI documentation. |
| **Pydantic 2.x** | Data validation & schemas | Guarantees that every request, response, and settings object matches our exact expectations before code runs. |
| **SQLAlchemy 2.0 & SQLite** | Local database | Serverless, zero configuration, stores all project evidence and draft history right on your computer in a single `.db` file. |
| **Playwright** | Browser automation | Controls a headless Chromium browser to view live project demos and capture real screenshots safely. |
| **Keyring (Windows Credential Manager)** | Secure OS password vault | Protects your API keys and tokens using your Windows login security, rather than saving them in plaintext files. |
| **Vanilla CSS & Jinja2** | User Interface | Lightweight, fast, glassmorphic dark theme without requiring heavy Node.js or Webpack build pipelines. |

---

## 2. Walkthrough: Tracing a Project from URL to LinkedIn Post

Here is the exact journey of a project when you use the app:

### Step 1: Input & URL Parsing
You enter `https://github.com/tiangolo/fastapi` and click **Start Analysis**.
- `github_service.py` receives the URL.
- `parse_github_url()` uses Python's `urllib.parse` to extract the owner (`tiangolo`) and the repository name (`fastapi`).

### Step 2: GitHub API Ingestion
- `GitHubClient` calls GitHub's official REST API: `GET https://api.github.com/repos/tiangolo/fastapi`.
- It also calls `GET .../readme` to get `README.md`.
- Because GitHub encodes files in Base64 for safe transport, our code decodes it into readable Markdown text.

### Step 3: Controlled Demo Inspection (Playwright)
- If you supplied a demo link (e.g. `https://fastapi.tiangolo.com`), `demo_inspector.py` checks the address against our SSRF firewall.
- Playwright opens a hidden Chromium browser, loads the page, takes a snapshot screenshot (`data/screenshots/demo_p1_xxx.png`), and reads the page title.

### Step 4: Evidence Compilation
- `evidence_engine.py` reads the README text and looks for sections like `## Features` and `## Tech Stack`.
- It creates structured `EvidenceItem` records tagged as `documented` (facts directly from README) vs `observed` (facts seen on the demo screen).
- Everything is saved into SQLite.

### Step 5: AI Post Generation
- You choose a post style (e.g. **Developer-Focused**).
- `prompts.py` builds a structured prompt containing only verified facts.
- The `AIProviderRouter` checks your active mode:
  - If **Cloud**: Sends prompt to OpenAI or Gemini via HTTPS.
  - If **Local**: Passes prompt to your local GGUF model.
- The AI returns clean JSON with post text, suggested hashtags, and link references.

### Step 6: Post Editor & Validation
- The draft appears on your screen in the Post Editor.
- You can tweak the text, add personal thoughts, or adjust hashtags.
- `validator.py` checks that:
  - You haven't accidentally pasted an API key or password (`sk-...`).
  - The post is under LinkedIn's 3,000-character limit.
  - The project link is included.

### Step 7: Approval & Publishing
- You click **Approve Post** -> status becomes `APPROVED`.
- You click **Publish to LinkedIn**.
- `linkedin_service.py` sends the official payload to LinkedIn's REST Posts API.
- LinkedIn creates the post on your profile and returns a permanent post identifier!

---

## 3. How to Test Without Real API Credentials

You do not need to spend money or sign up for third-party services to test this project:

1. **GitHub Works Unauthenticated:**
   You can analyze any public GitHub repository without an API key (GitHub provides 60 free queries per hour).
2. **Automated Test Suite Uses Mocks:**
   When you run `test.bat`, every single test uses realistic mock objects (`AsyncMock` and `httpx.Response`). No real API keys are ever needed for running tests.
3. **Local LLM Mode Works Completely Offline:**
   If you have a `.gguf` file (e.g., from HuggingFace), you can run inference completely on your machine without an internet connection.

---

## 4. Hands-On Debugging Exercises

Try these 3 fun exercises to understand how the system defends itself:

### Exercise 1: Test the SSRF Defense
1. In the Projects tab, enter `https://github.com/octocat/Hello-World` as the GitHub URL.
2. In the Demo URL field, enter `http://127.0.0.1:8000/api/health` or `http://localhost`.
3. Click **Start Analysis**.
4. **Observation:** Notice how the application immediately rejects the demo URL with: `Security restriction: Access to localhost/loopback address is prohibited for security.` The browser is never even launched!

### Exercise 2: Test the Secret Leaker Blocker
1. Go to the Post Editor tab.
2. In the post text, deliberately type: `Here is my key: sk-abcdef1234567890abcdef123456`.
3. Click **Validate Draft**.
4. **Observation:** The validator flags an immediate red alert: `Potential security credential or API key detected in post body. Please remove it before publishing.` The approval button remains blocked until the secret is removed!

### Exercise 3: Test Approval Invalidation
1. Validate and click **Approve Post** (badge turns green: `Draft: APPROVED`).
2. Now type an extra character into the post text and click **Save Draft**.
3. **Observation:** The badge immediately resets to `Draft: NEEDS_REVIEW` and the Publish button is disabled. This guarantees you never publish changes you haven't reviewed!
