"""Main entry point for GitHub LinkedIn AI Publisher application."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.publisher.api.drafts import router as drafts_router
from src.publisher.api.health import router as health_router
from src.publisher.api.history import router as history_router
from src.publisher.api.integrations import router as integrations_router
from src.publisher.api.projects import router as projects_router
from src.publisher.api.settings import router as settings_router
from src.publisher.core.config import settings
from src.publisher.core.logging_config import logger, setup_logging
from src.publisher.db.connection import init_db

# Setup directories
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class LocalhostHostValidationMiddleware(BaseHTTPMiddleware):
    """Enforce that all requests come strictly from localhost or 127.0.0.1."""

    async def dispatch(self, request: Request, call_next):
        host_header = request.headers.get("host", "").split(":")[0].lower()
        allowed_hosts = {"127.0.0.1", "localhost", "testserver"}
        if host_header not in allowed_hosts and not host_header.startswith("127.0.0."):
            logger.warning("Rejected non-localhost Host header: %s", host_header)
            return JSONResponse(
                status_code=403,
                content={"error": "Access forbidden: Application strictly binds to localhost."},
            )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown."""
    setup_logging()
    settings.ensure_directories()
    init_db()
    logger.info("Starting %s v%s on http://%s:%s", settings.APP_NAME, settings.APP_VERSION, settings.HOST, settings.PORT)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    """Application factory for FastAPI app."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(LocalhostHostValidationMiddleware)

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Static media & screenshots storage
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (settings.DATA_DIR / "media").mkdir(parents=True, exist_ok=True)
    (settings.DATA_DIR / "screenshots").mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(settings.DATA_DIR)), name="data")

    # API Routers
    app.include_router(health_router)
    app.include_router(settings_router)
    app.include_router(projects_router)
    app.include_router(drafts_router)
    app.include_router(integrations_router)
    app.include_router(history_router)

    # Web Dashboard Route
    @app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
    async def get_dashboard(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "title": f"{settings.APP_NAME} - Dashboard",
            },
        )

    return app


app = create_app()
