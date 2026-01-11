"""ML classifier for asset type prediction.

Wraps scikit-learn/XGBoost models for classification with
confidence scoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import LabelEncoder

from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


class MLClassifier:
    """Lightweight ML classifier for asset type prediction.

    Supports Random Forest, XGBoost, and Gradient Boosting algorithms.
    Provides confidence scores based on prediction probabilities.
    """

    SUPPORTED_ALGORITHMS = ("random_forest", "xgboost", "gradient_boosting")

    def __init__(
        self,
        model: RandomForestClassifier | GradientBoostingClassifier | Any | None = None,
        label_encoder: LabelEncoder | None = None,
        feature_transformer: FeatureTransformer | None = None,
        model_version: str | None = None,
        algorithm: str | None = None,
    ) -> None:
        """Initialize the ML classifier.

        Args:
            model: Trained sklearn/xgboost model.
            label_encoder: Label encoder for class names.
            feature_transformer: Feature transformer instance.
            model_version: Version string for the model.
            algorithm: Algorithm name.
        """
        self.model = model
        self.label_encoder = label_encoder
        self.feature_transformer = feature_transformer or FeatureTransformer()
        self.model_version = model_version
        self.algorithm = algorithm

    @property
    def is_ready(self) -> bool:
        """Check if model is loaded and ready for predictions."""
        return self.model is not None and self.label_encoder is not None

    @property
    def classes(self) -> list[str]:
        """Return the list of class names."""
        if self.label_encoder is None:
            return []
        return list(self.label_encoder.classes_)

    def predict(self, features: np.ndarray) -> tuple[str, float]:
        """Predict asset type with confidence score.

        Args:
            features: Feature vector from FeatureTransformer.

        Returns:
            Tuple of (predicted_type, confidence).

        Raises:
            RuntimeError: If model is not loaded.
        """
        if not self.is_ready:
            raise RuntimeError("Model not loaded")

        assert self.model is not None
        assert self.label_encoder is not None

        # Ensure 2D array for prediction
        if features.ndim == 1:
            features = features.reshape(1, -1)

        # Get prediction probabilities
        probas = self.model.predict_proba(features)[0]
        predicted_idx = np.argmax(probas)
        confidence = float(probas[predicted_idx])

        # Decode class name
        predicted_type = self.label_encoder.inverse_transform([predicted_idx])[0]

        return predicted_type, confidence

    def predict_proba(self, features: np.ndarray) -> dict[str, float]:
        """Get probability distribution over all classes.

        Args:
            features: Feature vector from FeatureTransformer.

        Returns:
            Dictionary mapping class names to probabilities.

        Raises:
            RuntimeError: If model is not loaded.
        """
        if not self.is_ready:
            raise RuntimeError("Model not loaded")

        assert self.model is not None
        assert self.label_encoder is not None

        # Ensure 2D array
        if features.ndim == 1:
            features = features.reshape(1, -1)

        probas = self.model.predict_proba(features)[0]
        return {
            class_name: float(prob)
            for class_name, prob in zip(self.label_encoder.classes_, probas, strict=True)
        }

    def predict_batch(
        self,
        features: np.ndarray,
    ) -> list[tuple[str, float]]:
        """Batch predict asset types.

        Args:
            features: 2D feature array of shape (n_samples, n_features).

        Returns:
            List of (predicted_type, confidence) tuples.
        """
        if not self.is_ready:
            raise RuntimeError("Model not loaded")

        assert self.model is not None
        assert self.label_encoder is not None

        probas = self.model.predict_proba(features)
        predicted_indices = np.argmax(probas, axis=1)
        confidences = probas[np.arange(len(probas)), predicted_indices]
        predicted_types = self.label_encoder.inverse_transform(predicted_indices)

        return list(zip(predicted_types, confidences.astype(float), strict=True))

    def save(self, path: Path) -> None:
        """Save model to disk.

        Args:
            path: Path to save the model file.
        """
        if not self.is_ready:
            raise RuntimeError("No model to save")

        path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "model": self.model,
            "label_encoder": self.label_encoder,
            "model_version": self.model_version,
            "algorithm": self.algorithm,
            "feature_names": self.feature_transformer.feature_names,
        }

        joblib.dump(model_data, path)
        logger.info(
            "Model saved",
            path=str(path),
            version=self.model_version,
            algorithm=self.algorithm,
        )

    @classmethod
    def load(cls, path: Path) -> MLClassifier:
        """Load model from disk.

        Args:
            path: Path to the model file.

        Returns:
            Loaded MLClassifier instance.

        Raises:
            FileNotFoundError: If model file doesn't exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model_data = joblib.load(path)

        classifier = cls(
            model=model_data["model"],
            label_encoder=model_data["label_encoder"],
            model_version=model_data.get("model_version"),
            algorithm=model_data.get("algorithm"),
        )

        logger.info(
            "Model loaded",
            path=str(path),
            version=classifier.model_version,
            algorithm=classifier.algorithm,
            classes=classifier.classes,
        )

        return classifier

    @classmethod
    def create_model(
        cls,
        algorithm: Literal["random_forest", "xgboost", "gradient_boosting"] = "random_forest",
        **kwargs: Any,
    ) -> RandomForestClassifier | GradientBoostingClassifier | Any:
        """Create a new untrained model instance.

        Args:
            algorithm: Algorithm to use.
            **kwargs: Additional parameters for the model.

        Returns:
            Untrained model instance.

        Raises:
            ValueError: If algorithm is not supported.
        """
        default_params: dict[str, Any]
        if algorithm == "random_forest":
            default_params = {
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 5,
                "min_samples_leaf": 2,
                "random_state": 42,
                "n_jobs": -1,
            }
            default_params.update(kwargs)
            return RandomForestClassifier(**default_params)

        elif algorithm == "xgboost":
            try:
                from xgboost import XGBClassifier
            except ImportError:
                raise ImportError("XGBoost not installed. Install with: pip install xgboost")

            default_params = {
                "n_estimators": 100,
                "max_depth": 6,
                "learning_rate": 0.1,
                "random_state": 42,
                "n_jobs": -1,
            }
            default_params.update(kwargs)
            return XGBClassifier(**default_params)

        elif algorithm == "gradient_boosting":
            default_params = {
                "n_estimators": 100,
                "max_depth": 5,
                "learning_rate": 0.1,
                "random_state": 42,
            }
            default_params.update(kwargs)
            return GradientBoostingClassifier(**default_params)

        else:
            raise ValueError(
                f"Unsupported algorithm: {algorithm}. "
                f"Supported: {cls.SUPPORTED_ALGORITHMS}"
            )
