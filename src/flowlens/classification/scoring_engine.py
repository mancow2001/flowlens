"""Scoring engine for asset classification.

Computes scores for each asset type based on behavioral features and heuristics.
"""

from dataclasses import dataclass, field

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.heuristics import ASSET_TYPE_SIGNALS, Signal
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SignalScore:
    """Individual signal evaluation result."""

    name: str
    weight: float
    raw_score: float  # 0.0 - 1.0
    contribution: float  # weight * raw_score


@dataclass
class TypeScore:
    """Classification score for a single asset type."""

    asset_type: ClassifiableAssetType
    score: float  # 0-100 normalized score
    signal_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "score": round(self.score, 2),
            "breakdown": {k: round(v, 3) for k, v in self.signal_breakdown.items()},
        }


@dataclass
class ClassificationResult:
    """Complete classification result for an asset."""

    ip_address: str
    current_type: str | None
    recommended_type: ClassifiableAssetType
    confidence: float  # 0.0 - 1.0
    should_auto_update: bool
    scores: dict[ClassifiableAssetType, TypeScore]
    features_summary: dict

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "ip_address": self.ip_address,
            "current_type": self.current_type,
            "recommended_type": self.recommended_type.value,
            "confidence": round(self.confidence, 3),
            "should_auto_update": self.should_auto_update,
            "scores": {
                k.value: v.to_dict()
                for k, v in self.scores.items()
            },
            "features_used": self.features_summary,
        }


class ScoringEngine:
    """Computes classification scores from behavioral features."""

    def __init__(self):
        """Initialize the scoring engine."""
        self.settings = get_settings().classification

    def compute_scores(
        self,
        features: BehavioralFeatures,
        current_type: str | None = None,
    ) -> ClassificationResult:
        """Compute classification scores for all asset types.

        Args:
            features: Behavioral features extracted from flow data.
            current_type: Current asset type (for stability bias).

        Returns:
            ClassificationResult with scores and recommendation.
        """
        scores: dict[ClassifiableAssetType, TypeScore] = {}

        # Calculate raw score for each asset type
        for asset_type in ClassifiableAssetType:
            type_score = self._score_asset_type(asset_type, features)
            scores[asset_type] = type_score

        # Find best and second-best scores
        sorted_scores = sorted(
            scores.items(),
            key=lambda x: x[1].score,
            reverse=True,
        )

        best_type, best_score = sorted_scores[0]
        second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else TypeScore(
            asset_type=ClassifiableAssetType.UNKNOWN,
            score=0,
        )

        # Calculate confidence based on margin
        confidence = self._calculate_confidence(best_score.score, second_score.score)

        # Apply stability bias (prefer current type if close)
        recommended_type = self._apply_stability_bias(
            current_type=current_type,
            best_type=best_type,
            best_score=best_score.score,
            scores=scores,
        )

        # Determine if we should auto-update
        should_auto_update = (
            confidence >= self.settings.auto_update_confidence_threshold
            and recommended_type != ClassifiableAssetType.UNKNOWN
            and features.total_flows >= self.settings.min_flows_required
        )

        # Create features summary for response
        features_summary = {
            "window_size": features.window_size,
            "total_flows": features.total_flows,
            "fan_in_count": features.fan_in_count,
            "fan_out_count": features.fan_out_count,
            "listening_ports": features.persistent_listener_ports[:5] if features.persistent_listener_ports else [],
            "has_db_ports": features.has_db_ports,
            "has_web_ports": features.has_web_ports,
            "has_storage_ports": features.has_storage_ports,
            "active_hours": features.active_hours_count,
            "business_hours_ratio": round(features.business_hours_ratio, 2) if features.business_hours_ratio else None,
        }

        result = ClassificationResult(
            ip_address=features.ip_address,
            current_type=current_type,
            recommended_type=recommended_type,
            confidence=confidence,
            should_auto_update=should_auto_update,
            scores=scores,
            features_summary=features_summary,
        )

        logger.debug(
            "Classification computed",
            ip=features.ip_address,
            recommended=recommended_type.value,
            confidence=confidence,
            should_update=should_auto_update,
        )

        return result

    def _score_asset_type(
        self,
        asset_type: ClassifiableAssetType,
        features: BehavioralFeatures,
    ) -> TypeScore:
        """Calculate score for a single asset type.

        Args:
            asset_type: The asset type to score.
            features: Behavioral features.

        Returns:
            TypeScore with breakdown.
        """
        signals = ASSET_TYPE_SIGNALS.get(asset_type, [])

        if not signals:
            return TypeScore(asset_type=asset_type, score=0)

        breakdown: dict[str, float] = {}
        total_weight = sum(s.weight for s in signals)
        total_score = 0.0

        for signal in signals:
            contribution = signal.evaluate(features)
            breakdown[signal.name] = contribution
            total_score += contribution

        # Normalize to 0-100 scale
        normalized_score = (total_score / total_weight * 100) if total_weight > 0 else 0

        return TypeScore(
            asset_type=asset_type,
            score=max(0, min(100, normalized_score)),
            signal_breakdown=breakdown,
        )

    def _calculate_confidence(self, best_score: float, second_score: float) -> float:
        """Calculate confidence based on score margin.

        Confidence is higher when there's a clear winner.

        Args:
            best_score: Highest score (0-100).
            second_score: Second highest score (0-100).

        Returns:
            Confidence value (0.0-1.0).
        """
        if best_score <= 0:
            return 0.0

        # Normalize to 0-1 scale
        best_normalized = best_score / 100

        # Margin between best and second best
        margin = (best_score - second_score) / 100

        # Confidence = base score * (0.5 + margin contribution)
        # This means even with 0 margin, a high score gives 0.5 * score confidence
        # With max margin (1.0), confidence approaches the score itself
        confidence = best_normalized * (0.5 + min(margin, 0.5))

        return min(1.0, confidence)

    def _apply_stability_bias(
        self,
        current_type: str | None,
        best_type: ClassifiableAssetType,
        best_score: float,
        scores: dict[ClassifiableAssetType, TypeScore],
    ) -> ClassifiableAssetType:
        """Apply stability bias to prefer current type if close.

        If the current type's score is within 10% of the best score,
        prefer keeping the current type.

        Args:
            current_type: Current asset type string.
            best_type: Type with highest score.
            best_score: Score of best type.
            scores: All type scores.

        Returns:
            Recommended type (may differ from best if stability applies).
        """
        if current_type is None or current_type == "unknown":
            return best_type

        # Try to match current type to ClassifiableAssetType
        try:
            current_classifiable = ClassifiableAssetType(current_type)
        except ValueError:
            # Current type not in our classifiable types
            return best_type

        # Check if current type's score is within 10% of best
        current_score = scores.get(current_classifiable)
        if current_score and current_score.score >= best_score * 0.9:
            logger.debug(
                "Stability bias applied",
                current=current_type,
                best=best_type.value,
                current_score=current_score.score,
                best_score=best_score,
            )
            return current_classifiable

        return best_type


def classify_asset(
    features: BehavioralFeatures,
    current_type: str | None = None,
) -> ClassificationResult:
    """Convenience function to classify an asset.

    Args:
        features: Behavioral features.
        current_type: Current type if known.

    Returns:
        Classification result.
    """
    engine = ScoringEngine()
    return engine.compute_scores(features, current_type)
