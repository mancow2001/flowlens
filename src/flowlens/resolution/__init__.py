"""Resolution service - dependency graph construction."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from flowlens.resolution.aggregator import FlowAggregator
    from flowlens.resolution.asset_mapper import AssetMapper
    from flowlens.resolution.change_detector import ChangeDetector
    from flowlens.resolution.dependency_builder import DependencyBuilder
    from flowlens.resolution.worker import ResolutionWorker

__all__ = ["FlowAggregator", "AssetMapper", "DependencyBuilder", "ChangeDetector", "ResolutionWorker"]

_EXPORTS: dict[str, str] = {
    "FlowAggregator": "flowlens.resolution.aggregator",
    "AssetMapper": "flowlens.resolution.asset_mapper",
    "ChangeDetector": "flowlens.resolution.change_detector",
    "DependencyBuilder": "flowlens.resolution.dependency_builder",
    "ResolutionWorker": "flowlens.resolution.worker",
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_EXPORTS[name])
    return getattr(module, name)
