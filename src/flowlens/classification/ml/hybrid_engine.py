"""Hybrid classification engine combining ML and heuristic approaches.

Uses ML classification for faster results when confidence is high,
falls back to heuristic scoring when ML is uncertain or unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.ml.classifier import MLClassifier
from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.classification.ml.model_manager import ModelManager
from flowlens.classification.scoring_engine import (
    ClassificationResult,
    ScoringEngine,
    TypeScore,
)
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass
class HybridClassificationResult(ClassificationResult):
    """Extended classification result with ML metadata."""

    classification_method: Literal["ml", "heuristic", "hybrid"]
    ml_confidence: float | None = None
    ml_prediction: str | None = None
    model_version: str | None = None


class HybridClassificationEngine:
    """Classification engine that combines ML and heuristic approaches.

    Strategy:
    1. If ML is enabled and model is loaded:
       - Extract ML features and get prediction
       - If ML confidence >= threshold AND enough flows: use ML result
       - Otherwise: fall back to heuristic scoring
    2. If ML is disabled or no model: use heuristic scoring only

    The hybrid approach provides:
    - Faster classification with fewer flows (ML needs ~10 vs ~100 for heuristics)
    - Higher accuracy when ML confidence is high
    - Reliable fallback when ML is uncertain
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        classifier: MLClassifier | None = None,
    ) -> None:
        """Initialize the hybrid classification engine.

        Args:
            db: Database session for model management.
            classifier: Pre-loaded ML classifier (optional).
        """
        self.db = db
        self.settings = get_settings().ml_classification
        self.heuristic_settings = get_settings().classification

        self._classifier = classifier
        self._feature_transformer = FeatureTransformer()
        self._scoring_engine = ScoringEngine()
        self._model_manager: ModelManager | None = None

        self._ml_enabled = self.settings.enabled
        self._initialized = False

    @property
    def ml_enabled(self) -> bool:
        """Check if ML classification is enabled."""
        return self._ml_enabled and self._classifier is not None

    @property
    def model_version(self) -> str | None:
        """Get the current model version."""
        if self._classifier:
            return self._classifier.model_version
        return None

    async def initialize(self) -> None:
        """Initialize the engine and load the ML model.

        Should be called once at startup or lazily on first classification.
        """
        if self._initialized:
            return

        if not self._ml_enabled:
            logger.info("ML classification disabled via config")
            self._initialized = True
            return

        try:
            self._model_manager = ModelManager(db=self.db)

            # Try to load the active model
            if self.db:
                self._classifier = await self._model_manager.load_active_model()
            elif self._model_manager.shipped_model_exists():
                self._classifier = self._model_manager.load_shipped_model()
            else:
                logger.warning(
                    "No ML model available, falling back to heuristics only"
                )
                self._classifier = None

            if self._classifier:
                logger.info(
                    "ML classification initialized",
                    model_version=self._classifier.model_version,
                    classes=self._classifier.classes,
                )

        except FileNotFoundError:
            logger.warning(
                "ML model not found, falling back to heuristics only. "
                "This is expected if no model has been trained yet."
            )
            self._classifier = None
        except Exception as e:
            logger.error(
                "Failed to initialize ML classification",
                error=str(e),
            )
            self._classifier = None

        self._initialized = True

    async def classify(
        self,
        features: BehavioralFeatures,
        current_type: str | None = None,
    ) -> HybridClassificationResult:
        """Classify an asset using the hybrid ML/heuristic approach.

        Args:
            features: Behavioral features extracted from flow data.
            current_type: Current asset type (for stability bias).

        Returns:
            HybridClassificationResult with classification and metadata.
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        # Try ML classification first if available
        ml_result = await self._try_ml_classification(features)

        if ml_result is not None:
            ml_type, ml_confidence = ml_result

            # Check if ML confidence is high enough
            if (
                ml_confidence >= self.settings.ml_confidence_threshold
                and features.total_flows >= self.settings.ml_min_flows
            ):
                return self._create_ml_result(
                    features=features,
                    ml_type=ml_type,
                    ml_confidence=ml_confidence,
                    current_type=current_type,
                )

            # ML confidence too low, fall back to heuristics but include ML info
            logger.debug(
                "ML confidence below threshold, using heuristics",
                ml_type=ml_type,
                ml_confidence=ml_confidence,
                threshold=self.settings.ml_confidence_threshold,
            )

        # Use heuristic classification
        heuristic_result = self._scoring_engine.compute_scores(features, current_type)

        # Create hybrid result with heuristic classification
        return HybridClassificationResult(
            ip_address=heuristic_result.ip_address,
            current_type=heuristic_result.current_type,
            recommended_type=heuristic_result.recommended_type,
            confidence=heuristic_result.confidence,
            should_auto_update=heuristic_result.should_auto_update,
            scores=heuristic_result.scores,
            features_summary=heuristic_result.features_summary,
            classification_method="heuristic",
            ml_confidence=ml_result[1] if ml_result else None,
            ml_prediction=ml_result[0] if ml_result else None,
            model_version=self.model_version,
        )

    async def _try_ml_classification(
        self,
        features: BehavioralFeatures,
    ) -> tuple[str, float] | None:
        """Attempt ML classification if available.

        Args:
            features: Behavioral features.

        Returns:
            Tuple of (predicted_type, confidence) or None if ML unavailable.
        """
        if not self.ml_enabled or self._classifier is None:
            return None

        try:
            # Transform features to ML format
            ml_features = self._feature_transformer.transform(features)

            # Get prediction
            predicted_type, confidence = self._classifier.predict(ml_features)

            logger.debug(
                "ML classification result",
                ip=features.ip_address,
                predicted_type=predicted_type,
                confidence=confidence,
            )

            return predicted_type, confidence

        except Exception as e:
            logger.warning(
                "ML classification failed, falling back to heuristics",
                error=str(e),
            )
            return None

    def _create_ml_result(
        self,
        features: BehavioralFeatures,
        ml_type: str,
        ml_confidence: float,
        current_type: str | None,
    ) -> HybridClassificationResult:
        """Create a classification result from ML prediction.

        Args:
            features: Behavioral features.
            ml_type: ML-predicted type.
            ml_confidence: ML confidence score.
            current_type: Current asset type.

        Returns:
            HybridClassificationResult based on ML prediction.
        """
        # Convert ML type to ClassifiableAssetType
        try:
            recommended_type = ClassifiableAssetType(ml_type)
        except ValueError:
            # Unknown type from ML, fall back to UNKNOWN
            recommended_type = ClassifiableAssetType.UNKNOWN

        # Apply stability bias if current type is close
        if current_type:
            try:
                current_classifiable = ClassifiableAssetType(current_type)
                # If current type matches ML prediction, keep it
                if current_classifiable == recommended_type:
                    pass  # Already correct
                # If current type is within a small confidence margin, prefer stability
                elif ml_confidence < 0.85:  # Only apply if not very confident
                    # Get ML probability for current type
                    ml_features = self._feature_transformer.transform(features)
                    assert self._classifier is not None  # Already checked above
                    probas = self._classifier.predict_proba(ml_features)
                    current_proba = probas.get(current_type, 0.0)

                    # If current type has reasonable probability, keep it
                    if current_proba >= ml_confidence * 0.8:
                        logger.debug(
                            "ML stability bias applied",
                            current=current_type,
                            ml_predicted=ml_type,
                            current_proba=current_proba,
                            best_proba=ml_confidence,
                        )
                        recommended_type = current_classifiable
            except ValueError:
                pass  # Current type not classifiable

        # Determine if we should auto-update
        should_auto_update = (
            ml_confidence >= self.heuristic_settings.auto_update_confidence_threshold
            and recommended_type != ClassifiableAssetType.UNKNOWN
            and features.total_flows >= self.settings.ml_min_flows
        )

        # Create scores dict with ML probabilities
        scores: dict[ClassifiableAssetType, TypeScore] = {}
        if self._classifier:
            ml_features = self._feature_transformer.transform(features)
            probas = self._classifier.predict_proba(ml_features)

            for type_str, proba in probas.items():
                try:
                    asset_type = ClassifiableAssetType(type_str)
                    scores[asset_type] = TypeScore(
                        asset_type=asset_type,
                        score=proba * 100,  # Convert to 0-100 scale
                        signal_breakdown={"ml_probability": proba},
                    )
                except ValueError:
                    continue  # Skip unknown types

        # Features summary
        features_summary = {
            "window_size": features.window_size,
            "total_flows": features.total_flows,
            "fan_in_count": features.fan_in_count,
            "fan_out_count": features.fan_out_count,
            "listening_ports": (
                features.persistent_listener_ports[:5]
                if features.persistent_listener_ports
                else []
            ),
            "has_db_ports": features.has_db_ports,
            "has_web_ports": features.has_web_ports,
            "has_storage_ports": features.has_storage_ports,
            "active_hours": features.active_hours_count,
            "business_hours_ratio": (
                round(features.business_hours_ratio, 2)
                if features.business_hours_ratio
                else None
            ),
        }

        return HybridClassificationResult(
            ip_address=features.ip_address,
            current_type=current_type,
            recommended_type=recommended_type,
            confidence=ml_confidence,
            should_auto_update=should_auto_update,
            scores=scores,
            features_summary=features_summary,
            classification_method="ml",
            ml_confidence=ml_confidence,
            ml_prediction=ml_type,
            model_version=self.model_version,
        )

    async def reload_model(self) -> bool:
        """Reload the ML model (e.g., after training a new one).

        Returns:
            True if model was reloaded successfully.
        """
        if not self._ml_enabled:
            return False

        try:
            if self._model_manager is None:
                self._model_manager = ModelManager(db=self.db)

            if self.db:
                self._classifier = await self._model_manager.load_active_model()
            elif self._model_manager.shipped_model_exists():
                self._classifier = self._model_manager.load_shipped_model()
            else:
                self._classifier = None
                return False

            logger.info(
                "ML model reloaded",
                model_version=self._classifier.model_version if self._classifier else None,
            )
            return self._classifier is not None

        except Exception as e:
            logger.error("Failed to reload ML model", error=str(e))
            return False

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the hybrid engine.

        Returns:
            Dictionary with engine status information.
        """
        return {
            "ml_enabled": self._ml_enabled,
            "ml_available": self._classifier is not None,
            "model_version": self.model_version,
            "model_classes": self._classifier.classes if self._classifier else [],
            "ml_confidence_threshold": self.settings.ml_confidence_threshold,
            "ml_min_flows": self.settings.ml_min_flows,
            "heuristic_min_flows": self.heuristic_settings.min_flows_required,
            "initialized": self._initialized,
        }
