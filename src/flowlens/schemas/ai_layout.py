"""Pydantic schemas for AI-powered layout arrangement."""

from enum import Enum

from pydantic import BaseModel


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class NodeInfo(BaseModel):
    """Node information for layout optimization."""

    id: str
    name: str
    node_type: str  # entry_point, member, external, client_summary
    hop_distance: int
    is_critical: bool = False


class EdgeInfo(BaseModel):
    """Edge information for layout optimization."""

    source_id: str
    target_id: str
    dependency_type: str | None = None


class AIArrangeRequest(BaseModel):
    """Request schema for AI layout arrangement."""

    nodes: list[NodeInfo]
    edges: list[EdgeInfo]
    canvas_width: float
    canvas_height: float


class AINodePosition(BaseModel):
    """Position for a single node."""

    x: float
    y: float


class AIArrangeResponse(BaseModel):
    """Response schema for AI layout arrangement."""

    positions: dict[str, AINodePosition]  # node_id -> {x, y}
