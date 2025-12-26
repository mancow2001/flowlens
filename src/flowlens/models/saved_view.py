"""Saved view model for topology visualization.

Allows users to save and share topology view configurations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flowlens.models.base import BaseModel


class SavedView(BaseModel):
    """Saved topology view configuration.

    Stores filter settings, grouping mode, zoom level, and selected nodes
    so users can quickly return to a specific view of the topology.
    """

    __tablename__ = "saved_views"

    # View metadata
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Owner (for RBAC when implemented)
    created_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Sharing settings
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # View configuration stored as JSON
    config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    """
    Config structure:
    {
        "filters": {
            "asset_types": ["server", "database"],
            "environments": ["production"],
            "datacenters": ["us-east-1"],
            "include_external": true,
            "min_bytes_24h": 0,
            "as_of": null  # ISO timestamp for historical view
        },
        "grouping": "environment",  # none, location, environment, datacenter, type
        "zoom": {
            "scale": 1.0,
            "x": 0,
            "y": 0
        },
        "selected_asset_ids": [],
        "layout_positions": {}  # Optional: saved node positions {asset_id: {x, y}}
    }
    """

    # Usage tracking
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    access_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
