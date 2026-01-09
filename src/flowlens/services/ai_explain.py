"""AI-powered dependency explanation service."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import get_settings
from flowlens.enrichment.resolvers.protocol import ProtocolResolver
from flowlens.models.asset import Asset
from flowlens.models.dependency import Dependency
from flowlens.schemas.ai_explain import DependencyExplanationResponse
from flowlens.schemas.ai_layout import LLMProvider


EXPLANATION_PROMPT = """You are a network infrastructure analyst. Explain this dependency in 2-3 concise sentences.

CONNECTION:
- Source: {source_name} ({source_type}, {source_ip})
- Target: {target_name} ({target_type}, {target_ip})
- Port/Protocol: {port}/{protocol_name} ({service_name})
- Traffic: {bytes_display}, {flows_total:,} total flows
- Active: First seen {first_seen}, last seen {last_seen}
- Criticality: Source={source_criticality}/10, Target={target_criticality}/10

CONTEXT:
- Source has {source_outbound_count} outbound connections
- Target has {target_inbound_count} inbound connections
- Service category: {service_category}

Explain what this connection likely represents, its business purpose, and any notable characteristics. Be technical and concise."""


def _get_protocol_name(protocol: int) -> str:
    """Get protocol name from number."""
    protocols = {1: "ICMP", 6: "TCP", 17: "UDP", 47: "GRE", 50: "ESP", 58: "ICMPv6"}
    return protocols.get(protocol, f"Protocol-{protocol}")


def _format_bytes(bytes_val: int) -> str:
    """Format bytes into human-readable string."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"


async def explain_dependency(
    db: AsyncSession,
    dependency_id: UUID,
) -> DependencyExplanationResponse:
    """Generate an AI-powered explanation for a dependency.

    Args:
        db: Database session
        dependency_id: ID of the dependency to explain

    Returns:
        DependencyExplanationResponse with the explanation

    Raises:
        ValueError: If dependency not found or LLM not configured
    """
    # Get the dependency with its assets
    result = await db.execute(
        select(Dependency)
        .where(Dependency.id == dependency_id)
    )
    dependency = result.scalar_one_or_none()

    if not dependency:
        raise ValueError(f"Dependency {dependency_id} not found")

    # Get source and target assets
    source_result = await db.execute(
        select(Asset).where(Asset.id == dependency.source_asset_id)
    )
    source_asset = source_result.scalar_one_or_none()

    target_result = await db.execute(
        select(Asset).where(Asset.id == dependency.target_asset_id)
    )
    target_asset = target_result.scalar_one_or_none()

    if not source_asset or not target_asset:
        raise ValueError("Source or target asset not found")

    # Get context: count of connections
    source_outbound = await db.execute(
        select(func.count())
        .select_from(Dependency)
        .where(Dependency.source_asset_id == source_asset.id)
        .where(Dependency.valid_to.is_(None))
    )
    source_outbound_count = source_outbound.scalar() or 0

    target_inbound = await db.execute(
        select(func.count())
        .select_from(Dependency)
        .where(Dependency.target_asset_id == target_asset.id)
        .where(Dependency.valid_to.is_(None))
    )
    target_inbound_count = target_inbound.scalar() or 0

    # Resolve service info
    resolver = ProtocolResolver()
    service_info = resolver.resolve(dependency.target_port, dependency.protocol)
    service_name = service_info.name if service_info else "unknown"
    service_category = service_info.category if service_info else "unknown"

    # Helper to get asset type as string (handles both enum and string)
    def get_asset_type_str(asset_type) -> str:
        if asset_type is None:
            return "unknown"
        return asset_type.value if hasattr(asset_type, 'value') else str(asset_type)

    # Format the prompt
    prompt = EXPLANATION_PROMPT.format(
        source_name=source_asset.display_name or source_asset.name,
        source_type=get_asset_type_str(source_asset.asset_type),
        source_ip=str(source_asset.ip_address),
        source_criticality=source_asset.criticality_score or 0,
        target_name=target_asset.display_name or target_asset.name,
        target_type=get_asset_type_str(target_asset.asset_type),
        target_ip=str(target_asset.ip_address),
        target_criticality=target_asset.criticality_score or 0,
        port=dependency.target_port,
        protocol_name=_get_protocol_name(dependency.protocol),
        service_name=service_name,
        bytes_display=_format_bytes(dependency.bytes_total),
        flows_total=dependency.flows_total,
        first_seen=dependency.valid_from.strftime("%Y-%m-%d") if dependency.valid_from else "unknown",
        last_seen=dependency.last_seen.strftime("%Y-%m-%d %H:%M") if dependency.last_seen else "unknown",
        source_outbound_count=source_outbound_count,
        target_inbound_count=target_inbound_count,
        service_category=service_category,
    )

    # Call the LLM
    settings = get_settings()
    provider_str = settings.llm.provider
    api_key = settings.llm.api_key
    model = settings.llm.model
    base_url = settings.llm.base_url
    temperature = settings.llm.temperature

    # Validate configuration
    if provider_str != "openai_compatible" and not api_key:
        raise ValueError(
            "LLM API key not configured. Set it in System Settings → AI/LLM Configuration."
        )

    if provider_str == "openai_compatible" and not base_url:
        raise ValueError(
            "Base URL is required for OpenAI-compatible provider. "
            "Set it in System Settings → AI/LLM Configuration."
        )

    try:
        provider = LLMProvider(provider_str)
    except ValueError:
        raise ValueError(
            f"Invalid LLM provider: {provider_str}. "
            "Must be 'anthropic', 'openai', or 'openai_compatible'."
        )

    # Call the appropriate provider
    if provider == LLMProvider.ANTHROPIC:
        explanation = await _call_anthropic(prompt, api_key, model, temperature)
    elif provider == LLMProvider.OPENAI_COMPATIBLE:
        explanation = await _call_openai_compatible(prompt, api_key, model, base_url, temperature)
    else:
        explanation = await _call_openai(prompt, api_key, model, temperature)

    return DependencyExplanationResponse(
        dependency_id=dependency_id,
        explanation=explanation.strip(),
        generated_at=datetime.now(timezone.utc),
        cached=False,
    )


async def _call_anthropic(
    prompt: str, api_key: str, model: str | None = None, temperature: float = 0.7
) -> str:
    """Call Anthropic Claude API."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError(
            "anthropic package is required for Anthropic provider. "
            "Install with: pip install anthropic"
        )

    client = Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model or "claude-sonnet-4-20250514",
        max_tokens=500,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _call_openai(
    prompt: str, api_key: str, model: str | None = None, temperature: float = 0.7
) -> str:
    """Call OpenAI API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package is required for OpenAI provider. "
            "Install with: pip install openai"
        )

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model or "gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=500,
    )
    return response.choices[0].message.content or ""


async def _call_openai_compatible(
    prompt: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Call OpenAI-compatible API (Ollama, LM Studio, etc.)."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package is required for OpenAI-compatible provider. "
            "Install with: pip install openai"
        )

    if not base_url:
        raise ValueError("base_url is required for OpenAI-compatible provider.")

    client = OpenAI(
        api_key=api_key or "not-needed",
        base_url=base_url,
    )

    response = client.chat.completions.create(
        model=model or "llama3.2",
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=500,
    )
    return response.choices[0].message.content or ""
