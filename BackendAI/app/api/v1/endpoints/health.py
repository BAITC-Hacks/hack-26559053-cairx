import time
from fastapi import APIRouter
from app.core.config import settings
from app.services.ai_service import ai_service
from app.services.graph_service import graph_service

router = APIRouter()
START_TIME = time.time()


@router.get("", summary="System Health Check")
async def health_check():
    uptime_seconds = round(time.time() - START_TIME, 2)
    return {
        "status": "online",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "uptime_seconds": uptime_seconds,
        "services": {
            "ai_service": {
                "available": ai_service.is_available,
                "model": settings.GEMINI_MODEL,
                "mode": "live" if ai_service.is_available else "simulation",
            },
            "graph_service": {
                "loaded": graph_service.is_loaded,
                "total_nodes": len(graph_service.processed_nodes_df) if graph_service.is_loaded else 0,
                "total_edges": len(graph_service.edges_df) if graph_service.is_loaded else 0,
            },
        },
    }
