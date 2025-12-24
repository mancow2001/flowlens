"""Resolution service - dependency graph construction.

This service processes enriched flow data to:
- Aggregate flows into time windows
- Map IP addresses to assets
- Build dependency edges
- Detect changes in topology
"""

from flowlens.resolution.aggregator import FlowAggregator
from flowlens.resolution.asset_mapper import AssetMapper
from flowlens.resolution.change_detector import ChangeDetector
from flowlens.resolution.dependency_builder import DependencyBuilder
from flowlens.resolution.worker import ResolutionWorker

__all__ = [
    "FlowAggregator",
    "AssetMapper",
    "DependencyBuilder",
    "ChangeDetector",
    "ResolutionWorker",
]
