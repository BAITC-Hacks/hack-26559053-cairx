import logging
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.schemas.ai import ChatMessage, ChatResponse, GenerateResponse

logger = logging.getLogger("backend_ai.services.ai")


class AIService:
    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initializes the Google GenAI client if an API key is available."""
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Google GenAI client successfully initialized.")
            except Exception as e:
                logger.warning(f"Failed to initialize GenAI client: {e}. Falling back to simulation.")
                self._client = None
        else:
            logger.info("GEMINI_API_KEY is not set. AIService operating in heuristic/simulation mode.")
            self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        system_instruction: Optional[str] = None,
    ) -> GenerateResponse:
        target_model = model or settings.GEMINI_MODEL

        if self._client:
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_instruction,
                )
                response = await self._client.aio.models.generate_content(
                    model=target_model,
                    contents=prompt,
                    config=config,
                )
                return GenerateResponse(
                    text=response.text or "",
                    model=target_model,
                )
            except Exception as e:
                logger.error(f"GenAI generation error: {e}")
                # Fallback on failure
                return GenerateResponse(
                    text=f"[GenAI Error: {e!s}]. Fallback heuristic response for prompt: {prompt[:100]}...",
                    model=f"{target_model}-fallback",
                )

        # Simulation mode response
        simulated_text = (
            f"AI Heuristic Response (Set GEMINI_API_KEY in .env for live Gemini output):\n\n"
            f"Analysis of input: '{prompt[:120]}...'\n"
            f"Summary: System processed your prompt with simulated model '{target_model}'. "
            f"To enable real LLM inference, configure your Google Gemini API key."
        )
        return GenerateResponse(text=simulated_text, model=f"{target_model}-mock")

    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        system_instruction: Optional[str] = None,
    ) -> ChatResponse:
        target_model = model or settings.GEMINI_MODEL

        if self._client:
            try:
                from google.genai import types
                formatted_contents = []
                for msg in messages:
                    role = "model" if msg.role in ["assistant", "model"] else "user"
                    formatted_contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg.content)]
                        )
                    )

                config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_instruction,
                )
                response = await self._client.aio.models.generate_content(
                    model=target_model,
                    contents=formatted_contents,
                    config=config,
                )
                return ChatResponse(
                    response=response.text or "",
                    model=target_model,
                    role="assistant",
                )
            except Exception as e:
                logger.error(f"GenAI chat error: {e}")
                return ChatResponse(
                    response=f"[Error during AI chat: {e!s}]. Please check API key.",
                    model=f"{target_model}-fallback",
                    role="assistant",
                )

        # Simulation response
        last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "Hello")
        reply = (
            f"Simulated AI Assistant Response:\n"
            f"Received your message: '{last_user_msg}'.\n"
            f"Add GEMINI_API_KEY to your .env to enable live Gemini {target_model} generation."
        )
        return ChatResponse(response=reply, model=f"{target_model}-mock", role="assistant")

    async def generate_node_explanation(
        self,
        gid: int,
        role: str,
        role_score: float,
        priority_score: float,
        evidence: str,
        metrics: Dict[str, Any],
        language: str = "ru",
    ) -> str:
        prompt = (
            f"You are a Senior Financial Intelligence & AML Graph Analyst.\n"
            f"Explain to the financial investigation jury why client (GID: {gid}) was classified with the role '{role}'.\n"
            f"Metrics:\n"
            f"- Role Score: {role_score:.2f}\n"
            f"- Priority Score: {priority_score:.2f}\n"
            f"- In Degree: {metrics.get('in_deg')}, Out Degree: {metrics.get('out_deg')}\n"
            f"- Inflow (KZT): {metrics.get('in_kzt', 0):,.0f}, Outflow (KZT): {metrics.get('out_kzt', 0):,.0f}\n"
            f"- Pass-Through Ratio: {metrics.get('pass_through')}\n"
            f"- PageRank: {metrics.get('pagerank', 0):.6f}\n"
            f"- Evidence string: {evidence}\n\n"
            f"Language: {language.upper()}.\n"
            f"Write a sharp, professional 2-3 paragraph explanation covering: "
            f"1) Role rationale based on exact numbers; 2) Flow dynamics (transit/drain/consolidation); 3) Recommended action for compliance."
        )

        resp = await self.generate_text(prompt=prompt, temperature=0.3)
        return resp.text


ai_service = AIService()
