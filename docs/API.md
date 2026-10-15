# 📡 API Reference: GitHub LinkedIn AI Publisher

The backend provides a RESTful API with automatic OpenAPI documentation available at:
👉 **[http://127.0.0.1:8000/api/docs](http://127.0.0.1:8000/api/docs)**

---

## 1. Health & Diagnostics

### `GET /api/health`
Return runtime diagnostics and database connectivity.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "app_name": "GitHub LinkedIn AI Publisher",
  "version": "1.0.0",
  "environment": "development",
  "host_binding": "127.0.0.1:8000",
  "platform": "Windows-10-10.0.22631-SP0",
  "uptime_seconds": 124.5,
  "database_connected": true
}
```

---

## 2. Settings

### `GET /api/settings`
Retrieve active AI mode, local model parameters, and masked credential presence flags.

**Response (200 OK):**
```json
{
  "active_mode": "cloud",
  "cloud_provider": "openai",
  "cloud_model": "gpt-4o-mini",
  "cloud_base_url": null,
  "has_cloud_api_key": true,
  "masked_cloud_api_key": "••••••••abcd",
  "local_model_path": null,
  "local_context_length": 4096,
  "local_gpu_layers": 0,
  "has_github_token": true,
  "has_linkedin_token": false,
  "preferences": {
    "style": "professional",
    "language": "English",
    "max_length": 2000
  }
}
```

### `PUT /api/settings/llm`
Update AI provider settings. If `cloud_api_key` is provided, it is securely persisted in Windows Credential Manager.

**Request Body:**
```json
{
  "mode": "cloud",
  "cloud_provider": "openai",
  "cloud_model": "gpt-4o-mini",
  "cloud_base_url": null,
  "cloud_api_key": "sk-proj-...",
  "local_model_path": null,
  "local_context_length": 4096,
  "local_gpu_layers": 0
}
```

### `POST /api/settings/llm/test`
Test connection for the currently active provider.

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Successfully authenticated with openai API."
}
```

---

## 3. Projects

### `POST /api/projects/analyze`
Analyze a GitHub repository and optional demo URL.

**Request Body:**
```json
{
  "repo_url": "https://github.com/tiangolo/fastapi",
  "demo_url": "https://fastapi.tiangolo.com",
  "user_notes": "Emphasize high performance and concurrency.",
  "enable_web_research": false,
  "post_style": "developer"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "project_id": 1,
  "name": "fastapi",
  "repo_url": "https://github.com/tiangolo/fastapi",
  "demo_url": "https://fastapi.tiangolo.com",
  "summary": {
    "project_name": "fastapi",
    "documented_facts": ["Feature: High performance", "Primary Programming Language: Python"],
    "observed_facts": ["Observed Demo Page Title: 'FastAPI'"],
    "total_evidence_units": 6
  },
  "screenshot_path": "data\\screenshots\\demo_p1_1710000000.png"
}
```

### `GET /api/projects`
List all analyzed projects.

### `GET /api/projects/{project_id}`
Retrieve a project and its associated evidence and draft history.

### `POST /api/projects/{project_id}/drafts`
Generate a new draft using the active AI provider.

**Request Body:**
```json
{
  "style": "developer",
  "custom_instructions": "Highlight asynchronous architecture."
}
```

---

## 4. Drafts

### `GET /api/drafts/{draft_id}`
Get draft details.

### `PUT /api/drafts/{draft_id}`
Update draft body text. **Resets approval status to `NEEDS_REVIEW`.**

**Request Body:**
```json
{
  "body": "Updated post text here..."
}
```

### `POST /api/drafts/{draft_id}/validate`
Run content validation checks.

**Response (200 OK):**
```json
{
  "is_valid": true,
  "errors": [],
  "warnings": ["Post character count (2100) exceeds your preferred max length (2000)."],
  "character_count": 2100,
  "max_length_limit": 3000,
  "has_repo_link": true,
  "has_demo_link": true,
  "is_approved": false
}
```

### `POST /api/drafts/{draft_id}/approve`
Explicit user approval. Moves draft to `APPROVED` state.

### `POST /api/drafts/{draft_id}/publish`
Publishes an approved draft to LinkedIn. Returns HTTP 400 if draft is not in `APPROVED` state.

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Post successfully published to LinkedIn!",
  "linkedin_post_id": "urn:li:share:7170000000000000000",
  "submission_id": "c8f2d5a1-4321-4def-9876-123456789abc"
}
```

---

## 5. History

### `GET /api/history`
List publishing audit trail entries.
