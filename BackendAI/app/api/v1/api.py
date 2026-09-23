from fastapi import APIRouter
from app.api.v1.endpoints import ai, graph, health

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Inference & LLM"])
api_router.include_router(graph.router, prefix="/graph", tags=["Graph & AML Analytics"])
