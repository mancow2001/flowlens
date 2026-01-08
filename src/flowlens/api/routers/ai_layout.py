"""AI-powered layout arrangement endpoint."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from flowlens.api.dependencies import DbSession, AnalystUser
from flowlens.common.config import get_settings
from flowlens.schemas.ai_layout import AIArrangeRequest, AIArrangeResponse, LLMProvider
from flowlens.services.llm_layout import suggest_layout

router = APIRouter(prefix="/applications/{application_id}/layouts", tags=["ai-layout"])


@router.post("/{hop_depth}/ai-arrange", response_model=AIArrangeResponse)
async def ai_arrange_layout(
    application_id: UUID,
    request: AIArrangeRequest,
    hop_depth: int = Path(..., ge=1, le=5),
    db: DbSession = None,
    user: AnalystUser = None,
) -> AIArrangeResponse:
    """Use LLM to suggest optimal node arrangement for the topology.

    This endpoint sends the current topology structure to a configured LLM
    (Anthropic Claude, OpenAI GPT, or OpenAI-compatible local models like Ollama/LM Studio)
    and returns suggested X,Y positions for each node that optimize for:
    - Minimal edge crossings
    - Clear hierarchical left-to-right flow
    - Logical grouping of related nodes
    - Even distribution across the canvas

    The LLM provider and API key must be configured in System Settings.
    """
    settings = get_settings()

    # Get LLM settings
    provider_str = settings.llm.provider
    api_key = settings.llm.api_key
    model = settings.llm.model
    base_url = settings.llm.base_url

    # API key is required for cloud providers, optional for local ones
    if provider_str != "openai_compatible" and not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM API key not configured. Set it in System Settings → AI/LLM Configuration.",
        )

    # Base URL is required for openai_compatible provider
    if provider_str == "openai_compatible" and not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Base URL is required for OpenAI-compatible provider. Set it in System Settings → AI/LLM Configuration.",
        )

    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid LLM provider: {provider_str}. Must be 'anthropic', 'openai', or 'openai_compatible'.",
        )

    try:
        return await suggest_layout(request, provider, api_key, model, base_url)
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse LLM response: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM request failed: {str(e)}",
        )
