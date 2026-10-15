# 🏗️ Architecture Specification: GitHub LinkedIn AI Publisher

## 1. Architectural Philosophy & Principles

GitHub LinkedIn AI Publisher is structured as a **modular monolith** running locally on the user's Windows machine.

Key architectural tenets:
1. **Local-First & Offline-Capable:** Core data, draft history, models, and evidence stay on the local machine.
2. **Separation of Concerns:** Network integrations (GitHub, Playwright, LinkedIn, Web Search) are completely decoupled from persistence and business rules.
3. **Mutual Exclusivity:** The AI system enforces strictly one active inference provider at a time with zero silent fallback.
4. **Factual Grounding:** Prompts operate on structured, categorized evidence packages to prevent hallucination.
5. **Human-in-the-Loop:** Automated publishing is mathematically and structurally blocked without an explicit transition to `APPROVED`.

---

## 2. Component Diagram

```mermaid
graph LR
    subgraph UI Layer
        WebBrowser[Desktop Browser] --> Static[Static Assets: CSS/JS]
        WebBrowser --> Jinja[Jinja2 HTML Templates]
    end

    subgraph API Layer
        FastAPIApp[FastAPI / Uvicorn Server]
        Middleware[Host Header & SSRF Validation]
        APIRouters[Projects / Drafts / Settings / Integrations / History]
    end

    subgraph Business Logic & Services
        GHSvc[GitHub REST Client]
        DemoSvc[Demo Inspector / Playwright]
        WebSvc[Web Research Service]
        EvEng[Evidence Engine]
        ValSvc[Draft Validator]
        AuthSvc[LinkedIn OAuth 2.0]
        PubSvc[LinkedIn Posts Publisher]
        MediaSvc[Media Upload Service]
        CredMgr[Windows Credential Manager]
    end

    subgraph AI Provider Layer
        Router[AI Provider Router]
        CloudAPI[Cloud API Adapter]
        LocalLLM[Local GGUF Adapter]
    end

    subgraph Persistence Layer
        DB[(SQLite / SQLAlchemy 2.0)]
        FS[(Local File Storage: Screenshots)]
    end

    WebBrowser <--> FastAPIApp
    FastAPIApp --> Middleware --> APIRouters
    APIRouters --> GHSvc & DemoSvc & WebSvc & EvEng & ValSvc & AuthSvc & PubSvc & CredMgr
    APIRouters --> Router
    Router --> CloudAPI & LocalLLM
    APIRouters --> DB
    DemoSvc --> FS
```

---

## 3. Module Responsibilities

| Module | Location | Responsibility |
|---|---|---|
| **Core Config & Security** | `src/publisher/core/` | Pydantic settings schema, localhost constraint, logging with regex secret masking, and SSRF URL validator. |
| **Database & Persistence** | `src/publisher/db/` | SQLAlchemy 2.0 declarative models, connection sessionmaker, and CRUD repository pattern enforcing state transitions. |
| **GitHub Integration** | `src/publisher/services/github_service.py` | Official GitHub REST API client for metadata retrieval and Base64 README decoding. |
| **Demo Inspector** | `src/publisher/services/demo_inspector.py` | Headless Playwright Chromium automation with timeout safeguards and screenshot capture. |
| **Evidence Engine** | `src/publisher/services/evidence_engine.py` | Aggregates and categorizes facts into documented, observed, user-supplied, and external units. |
| **AI Provider Router** | `src/publisher/services/ai/` | Abstract provider interface, Cloud API adapter, Local GGUF adapter, and exclusive mode router. |
| **Draft Validator** | `src/publisher/services/validator.py` | Validates post length, links, secret leakage, and checks for previously published duplicate content. |
| **Credential Manager** | `src/publisher/services/credential_manager.py` | OS-level secret storage using `keyring` (Windows Credential Manager). |
| **LinkedIn Integration** | `src/publisher/services/linkedin_service.py` | OAuth 2.0 with PKCE/state verification, user profile extraction, and REST Posts publishing. |
| **Media Service** | `src/publisher/services/media_service.py` | Image validation and official LinkedIn 2-step media upload protocol. |

---

## 4. Database Schema (Entity Relationship Diagram)

```mermaid
erDiagram
    PROJECTS ||--o{ PROJECT_EVIDENCE : "has"
    PROJECTS ||--o{ DRAFTS : "generates"
    DRAFTS ||--o{ DRAFT_SOURCES : "cites"
    PROJECT_EVIDENCE ||--o{ DRAFT_SOURCES : "supports"
    DRAFTS ||--o{ PUBLISHING_HISTORY : "audits"

    PROJECTS {
        int id PK
        string name
        string repo_url
        string demo_url
        text user_notes
        string status
        datetime created_at
        datetime updated_at
    }

    PROJECT_EVIDENCE {
        int id PK
        int project_id FK
        string source_type
        string source_url
        text content
        string category
        string verification_status
        datetime retrieved_at
    }

    DRAFTS {
        int id PK
        int project_id FK
        int version
        text body
        string style
        json post_metadata
        string status
        string screenshot_path
        datetime created_at
        datetime updated_at
    }

    DRAFT_SOURCES {
        int id PK
        int draft_id FK
        int evidence_id FK
    }

    SETTINGS {
        int id PK
        string active_ai_mode
        string cloud_provider
        string cloud_model
        string cloud_base_url
        string local_model_path
        int local_context_length
        int local_gpu_layers
        json preferences
        datetime updated_at
    }

    INTEGRATIONS {
        int id PK
        string provider
        string status
        json metadata_json
        datetime last_check_at
        datetime expires_at
    }

    PUBLISHING_HISTORY {
        int id PK
        int draft_id FK
        string submission_id
        string linkedin_post_id
        string status
        datetime created_at
        datetime published_at
        string error_category
        text sanitized_error
    }
```

---

## 5. State Machine Invariants

### Project State Machine
```mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> ANALYZING: User triggers analysis
    ANALYZING --> ANALYZED: GitHub & Demo inspection succeed
    ANALYZING --> ANALYSIS_FAILED: Invalid repo / network error
    ANALYSIS_FAILED --> ANALYZING: User retries
```

### Draft State Machine
```mermaid
stateDiagram-v2
    [*] --> GENERATED: AI Model returns structured draft
    GENERATED --> VALIDATED: DraftValidator checks pass
    VALIDATED --> APPROVED: Explicit human user approval
    VALIDATED --> NEEDS_REVIEW: Validation warnings flagged
    NEEDS_REVIEW --> APPROVED: Explicit human user approval
    APPROVED --> NEEDS_REVIEW: User edits draft text!
    APPROVED --> PUBLISHING: User clicks Publish
    PUBLISHING --> PUBLISHED: LinkedIn returns 201 Created
    PUBLISHING --> PUBLISH_FAILED: LinkedIn returns 4xx / 5xx / timeout
    PUBLISH_FAILED --> APPROVED: User approves retry
```

> **Crucial Rule:** Any modification made to an `APPROVED` draft immediately transitions the draft back to `NEEDS_REVIEW`. Publishing cannot occur without re-approval.
