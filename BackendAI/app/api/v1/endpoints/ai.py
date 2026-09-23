from fastapi import APIRouter, HTTPException, status
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    ExplainNodeRequest,
    ExplainNodeResponse,
    GenerateRequest,
    GenerateResponse,
)
from app.schemas.common import APIResponse
from app.services.ai_service import ai_service
from app.services.graph_service import graph_service

router = APIRouter()


@router.post("/generate", response_model=APIResponse[GenerateResponse], summary="Generate text using AI")
async def generate_text(request: GenerateRequest):
    try:
        result = await ai_service.generate_text(
            prompt=request.prompt,
            model=request.model,
            temperature=request.temperature or 0.7,
            system_instruction=request.system_instruction,
        )
        return APIResponse(data=result, message="Text successfully generated")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI generation failed: {e!s}",
        )


@router.post("/chat", response_model=APIResponse[ChatResponse], summary="Conversational AI Chat")
async def chat_conversation(request: ChatRequest):
    try:
        result = await ai_service.chat(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature or 0.7,
            system_instruction=request.system_instruction,
        )
        return APIResponse(data=result, message="Chat response received")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat failed: {e!s}",
        )


@router.post("/explain-node", response_model=APIResponse[ExplainNodeResponse], summary="Generate AI explanation for node role")
async def explain_node(request: ExplainNodeRequest):
    if not graph_service.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph dataset is not loaded.",
        )

    node = graph_service.get_node_by_gid(request.gid)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with gid={request.gid} not found in dataset.",
        )

    assigned_role = request.role or node.role
    metrics = {
        "in_deg": node.in_deg,
        "out_deg": node.out_deg,
        "in_kzt": node.in_kzt,
        "out_kzt": node.out_kzt,
        "pass_through": node.pass_through,
        "pagerank": node.pagerank,
        "depth": node.depth,
        "is_seed": node.is_seed,
    }

    explanation_text = await ai_service.generate_node_explanation(
        gid=node.gid,
        role=assigned_role,
        role_score=node.role_score,
        priority_score=node.priority_score,
        evidence=node.evidence,
        metrics=metrics,
        language=request.language,
    )

    response_data = ExplainNodeResponse(
        gid=node.gid,
        role=assigned_role,
        role_score=node.role_score,
        priority_score=node.priority_score,
        evidence=node.evidence,
        explanation=explanation_text,
        key_metrics=metrics,
    )

    return APIResponse(data=response_data, message=f"Generated explanation for GID {node.gid}")
