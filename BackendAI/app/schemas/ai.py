from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', 'model', or 'system'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., min_length=1, description="Conversation history")
    model: Optional[str] = Field(default=None, description="Model to use (defaults to configured Gemini model)")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    system_instruction: Optional[str] = Field(default=None, description="Optional system prompt")


class ChatResponse(BaseModel):
    response: str
    model: str
    role: str = "assistant"
    usage: Optional[Dict[str, Any]] = None


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Input prompt for LLM")
    model: Optional[str] = Field(default=None, description="Model override")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    system_instruction: Optional[str] = Field(default=None, description="System guidance")


class GenerateResponse(BaseModel):
    text: str
    model: str


class ExplainNodeRequest(BaseModel):
    gid: int = Field(..., description="Client ID (gid) to explain")
    role: Optional[str] = Field(default=None, description="Assigned role (optional, will compute if omitted)")
    language: str = Field(default="ru", description="Language of explanation: 'ru' or 'en'")


class ExplainNodeResponse(BaseModel):
    gid: int
    role: str
    role_score: float
    priority_score: float
    evidence: str
    explanation: str
    key_metrics: Dict[str, Any]
