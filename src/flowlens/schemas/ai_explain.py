"""Pydantic schemas for AI-powered dependency explanations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DependencyExplanationRequest(BaseModel):
    """Request context for dependency explanation (internal use)."""

    # Source asset info
    source_name: str
    source_type: str
    source_ip: str
    source_criticality: int

    # Target asset info
    target_name: str
    target_type: str
    target_ip: str
    target_criticality: int

    # Connection details
    target_port: int
    protocol: int
    protocol_name: str

    # Traffic metrics
    bytes_total: int
    bytes_last_24h: int
    flows_total: int
    first_seen: datetime | None
    last_seen: datetime | None

    # Context
    source_outbound_count: int
    target_inbound_count: int


class DependencyExplanationResponse(BaseModel):
    """Response schema for dependency explanation."""

    dependency_id: UUID
    explanation: str
    generated_at: datetime
    cached: bool = False
