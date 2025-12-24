"""Graph algorithms - traversal, impact analysis, blast radius, SPOF detection.

This module provides graph analysis capabilities using PostgreSQL
recursive CTEs for efficient traversal without a graph database.
"""

from flowlens.graph.blast_radius import BlastRadius, BlastRadiusCalculator, BlastRadiusNode
from flowlens.graph.impact import ImpactAnalysis, ImpactAnalyzer, ImpactedAsset
from flowlens.graph.spof import SPOFAnalysis, SPOFDetector, SPOFResult
from flowlens.graph.traversal import GraphTraversal, TraversalNode, TraversalResult

__all__ = [
    # Traversal
    "GraphTraversal",
    "TraversalNode",
    "TraversalResult",
    # Impact
    "ImpactAnalyzer",
    "ImpactAnalysis",
    "ImpactedAsset",
    # Blast Radius
    "BlastRadiusCalculator",
    "BlastRadius",
    "BlastRadiusNode",
    # SPOF
    "SPOFDetector",
    "SPOFAnalysis",
    "SPOFResult",
]
