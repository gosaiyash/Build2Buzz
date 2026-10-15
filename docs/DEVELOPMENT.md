# 💻 Developer Guide: GitHub LinkedIn AI Publisher

## 1. Development Environment Setup

1. **Clone or Open the Repository:**
   Ensure you are in the project root containing `requirements.txt` and batch scripts.

2. **Activate the Virtual Environment:**
   ```cmd
   .venv\Scripts\activate.bat
   ```

3. **Install Editable / Dev Packages:**
   All core dependencies are installed in `.venv`. To add a development dependency:
   ```cmd
   pip install <package-name>
   pip freeze > requirements.txt
   ```

---

## 2. Running Automated Tests

Run the full pytest suite:
```cmd
test.bat
```
Or directly via Python:
```cmd
.venv\Scripts\pytest -v --tb=short
```

Run targeted test modules:
```cmd
.venv\Scripts\pytest tests/test_security_foundation.py
.venv\Scripts\pytest tests/test_github_service.py
.venv\Scripts\pytest tests/test_demo_inspector.py
.venv\Scripts\pytest tests/test_ai_router.py
.venv\Scripts\pytest tests/test_api_integration.py
```

---

## 3. How to Add a New AI Provider

1. Open `src/publisher/services/ai/base.py` and inspect the abstract `LLMProvider` interface.
2. Create a new adapter class inheriting from `LLMProvider`:
   ```python
   from src.publisher.services.ai.base import LLMProvider, EvidencePack, PostPreferences, GeneratedDraftOutput

   class CustomProvider(LLMProvider):
       def __init__(self, api_key: str):
           self.api_key = api_key

       def validate_configuration(self) -> tuple[bool, str]:
           return bool(self.api_key), "API Key required"

       async def test_connection(self) -> tuple[bool, str]:
           # verify connection
           return True, "Connected"

       async def generate_linkedin_draft(self, evidence: EvidencePack, preferences: PostPreferences) -> GeneratedDraftOutput:
           # construct prompt using build_generation_prompt(evidence, preferences)
           # call your model and return GeneratedDraftOutput
           ...
   ```
3. Register the new provider inside `src/publisher/services/ai/router.py` in `AIProviderRouter.get_active_provider()`.
4. Add the option to the AI Settings dropdown in `src/publisher/templates/dashboard.html`.

---

## 4. Code Quality & Conventions

- **Type Hints:** All public functions, methods, and FastAPI routes must use standard Python 3.11 type annotations.
- **Error Handling:** Network errors must be caught and re-raised as domain-specific exceptions (`GitHubServiceError`, `LinkedInServiceError`, `AIProviderError`) with user-friendly messages rather than dumping stack traces.
- **Secret Redaction:** Never print or log raw API tokens. Use `mask_secret()` for string presentation.
