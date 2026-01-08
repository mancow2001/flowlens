"""LLM-based layout suggestion service."""

import json
import re
from typing import TYPE_CHECKING

from flowlens.schemas.ai_layout import (
    AIArrangeRequest,
    AIArrangeResponse,
    AINodePosition,
    LLMProvider,
)

if TYPE_CHECKING:
    pass

LAYOUT_PROMPT = """You are a graph layout calculator. Output JSON coordinates for network nodes.

NODES:
{nodes_list}

EDGES:
{edges_list}

CANVAS: {width}x{height} pixels

RULES:
- X position by hop_distance: -1→75, 0→200, 1→400, 2→600, 3→800
- Y positions: spread nodes at same hop level vertically, 80px minimum gap
- Y range: 50 to {max_y}
- Center nodes vertically within their hop column

EXAMPLE:
Nodes: A(hop=0), B(hop=1), C(hop=1)
Edges: A→B, A→C
Output: {{"A":{{"x":200,"y":250}},"B":{{"x":400,"y":150}},"C":{{"x":400,"y":350}}}}

OUTPUT: Return ONLY valid JSON mapping node IDs to {{"x":number,"y":number}}. No text, no markdown.

JSON:"""


async def suggest_layout(
    request: AIArrangeRequest,
    provider: LLMProvider,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.3,
) -> AIArrangeResponse:
    """Call LLM to suggest optimal layout positions.

    Args:
        request: The layout arrangement request with nodes, edges, and canvas size
        provider: The LLM provider to use (anthropic, openai, or openai_compatible)
        api_key: API key for the provider
        model: Optional model override (defaults to provider's best model)
        base_url: Custom base URL for OpenAI-compatible APIs (Ollama, LM Studio, etc.)
        temperature: Sampling temperature (0.0-1.0, lower = more deterministic)

    Returns:
        AIArrangeResponse with suggested positions for each node
    """
    # Format nodes as a simple list for the prompt
    nodes_list = "\n".join(
        f"- {n.id}: name={n.name}, type={n.node_type}, hop={n.hop_distance}"
        for n in request.nodes
    )

    # Format edges as a simple list
    edges_list = "\n".join(
        f"- {e.source_id} → {e.target_id}" + (f" ({e.dependency_type})" if e.dependency_type else "")
        for e in request.edges
    )

    prompt = LAYOUT_PROMPT.format(
        nodes_list=nodes_list,
        edges_list=edges_list,
        width=int(request.canvas_width),
        height=int(request.canvas_height),
        max_y=int(request.canvas_height - 50),
    )

    if provider == LLMProvider.ANTHROPIC:
        response_text = await _call_anthropic(prompt, api_key, model, temperature)
    elif provider == LLMProvider.OPENAI_COMPATIBLE:
        response_text = await _call_openai_compatible(prompt, api_key, model, base_url, temperature)
    else:
        response_text = await _call_openai(prompt, api_key, model, temperature)

    # Parse JSON from response (handle potential markdown code blocks)
    positions = _parse_json_response(response_text)

    # Convert to AINodePosition objects
    result_positions = {}
    for node_id, pos in positions.items():
        if isinstance(pos, dict) and "x" in pos and "y" in pos:
            result_positions[node_id] = AINodePosition(x=float(pos["x"]), y=float(pos["y"]))

    return AIArrangeResponse(positions=result_positions)


def _parse_json_response(response_text: str) -> dict:
    """Parse JSON from LLM response, handling potential markdown code blocks."""
    # Try direct JSON parse first
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code block
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response_text)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find JSON object in the response
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {response_text[:500]}")


async def _call_anthropic(
    prompt: str, api_key: str, model: str | None = None, temperature: float = 0.3
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
        max_tokens=4096,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def _call_openai(
    prompt: str, api_key: str, model: str | None = None, temperature: float = 0.3
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
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content or "{}"


async def _call_openai_compatible(
    prompt: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float = 0.3,
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
        raise ValueError(
            "base_url is required for OpenAI-compatible provider. "
            "Set it in System Settings (e.g., http://localhost:11434/v1 for Ollama)."
        )

    # For local providers, api_key might be optional or a placeholder
    client = OpenAI(
        api_key=api_key or "not-needed",
        base_url=base_url,
    )

    # Note: Some local models may not support response_format, so we don't use it here
    # The prompt already instructs the model to return JSON only
    response = client.chat.completions.create(
        model=model or "llama3.2",  # Default to a common Ollama model
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content or "{}"
