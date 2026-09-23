import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.services.graph_service import graph_service

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load datasets and initialize models/services
    logger.info("Initializing HackAlem AI backend...")
    data_loaded = graph_service.load_data()
    if data_loaded:
        logger.info("Graph analysis service initialized with HackAlem parquet datasets.")
    else:
        logger.warning("Graph data not found or failed to load. AI endpoints remain operational.")

    yield
    # Shutdown
    logger.info("HackAlem AI backend shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
origins = settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An internal server error occurred.",
        },
    )


# Root Endpoint
@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to HackAlem AI API Backend",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health",
        "status": "ready",
    }


# Include API Routers
app.include_router(api_router, prefix=settings.API_V1_STR)
