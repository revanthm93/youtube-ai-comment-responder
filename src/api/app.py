"""
FastAPI application entry point.

Configures the main application with middleware, routes, and lifecycle events.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import __version__
from src.config import get_settings, get_api_settings
from src.config.logging import setup_logging, bind_context, clear_context, get_logger
from src.models import HealthCheckResponse

import uuid

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    # Startup
    settings = get_settings()
    setup_logging(log_level=settings.log_level)
    logger.info(
        "application_starting",
        app_name=settings.app_name,
        environment=settings.app_env,
        version=__version__,
    )

    # Initialize services here (database, redis, etc.)
    # These will be added as we build out the system

    yield

    # Shutdown
    logger.info("application_shutting_down")
    # Cleanup resources here


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    api_settings = get_api_settings()

    app = FastAPI(
        title=settings.app_name,
        description="AI-powered YouTube comment response system with RAG",
        version=__version__,
        docs_url=f"{api_settings.prefix}/docs",
        redoc_url=f"{api_settings.prefix}/redoc",
        openapi_url=f"{api_settings.prefix}/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def add_request_context(request: Request, call_next):
        """Add request ID and timing to all requests."""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = datetime.utcnow()

        # Bind context for logging
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            return response

        except Exception as e:
            logger.exception("request_failed", error=str(e))
            raise

        finally:
            clear_context()

    # Health check endpoint
    @app.get("/health", response_model=HealthCheckResponse, tags=["Health"])
    async def health_check() -> HealthCheckResponse:
        """Check application health status."""
        return HealthCheckResponse(
            status="healthy",
            version=__version__,
            timestamp=datetime.utcnow(),
            components={
                "api": "healthy",
                # Add more component checks as they're implemented
            },
        )

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API info."""
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": f"{api_settings.prefix}/docs",
            "health": "/health",
        }

    # Include routers (will be added as we build endpoints)
    # app.include_router(comments_router, prefix=api_settings.prefix)
    # app.include_router(videos_router, prefix=api_settings.prefix)
    # app.include_router(tasks_router, prefix=api_settings.prefix)

    # Exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Handle unhandled exceptions."""
        logger.exception(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
                "message": str(exc) if settings.debug else "An unexpected error occurred",
            },
        )

    return app


# Create app instance
app = create_app()