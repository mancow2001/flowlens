"""Asset Classification Engine.

Behavioral classification of assets based on NetFlow/IPFIX/sFlow data.
"""

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import BehavioralFeatures, FeatureExtractor
from flowlens.classification.scoring_engine import ClassificationResult, ScoringEngine, classify_asset
from flowlens.classification.worker import ClassificationWorker

__all__ = [
    "ClassifiableAssetType",
    "BehavioralFeatures",
    "FeatureExtractor",
    "ClassificationResult",
    "ScoringEngine",
    "ClassificationWorker",
    "classify_asset",
]
