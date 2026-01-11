"""ML model trainer for classification.

Orchestrates training from confirmed classifications or synthetic data,
with progress reporting through the background task system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.preprocessing import LabelEncoder

from flowlens.classification.ml.classifier import MLClassifier
from flowlens.classification.ml.dataset import DatasetBuilder, TrainingDataset
from flowlens.classification.ml.model_manager import ModelManager, TrainingStats
from flowlens.classification.ml.synthetic import SyntheticDataGenerator
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from flowlens.tasks.executor import TaskExecutor

logger = get_logger(__name__)


class TrainingError(Exception):
    """Error during model training."""

    pass


@dataclass
class EvaluationMetrics:
    """Metrics from model evaluation on test set."""

    accuracy: float
    f1_macro: float
    f1_weighted: float
    confusion_matrix: list[list[int]]
    class_names: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "accuracy": self.accuracy,
            "f1_macro": self.f1_macro,
            "f1_weighted": self.f1_weighted,
            "confusion_matrix": self.confusion_matrix,
            "class_names": self.class_names,
        }


class MLTrainer:
    """Orchestrates ML model training with progress reporting.

    Supports training from:
    - Confirmed asset classifications in the database
    - Synthetic data (for building the shipped model)

    Training phases:
    1. Collect training data
    2. Validate dataset
    3. Train model
    4. Evaluate on test set
    5. Save model if accuracy meets threshold
    """

    MIN_ACCURACY_THRESHOLD = 0.85
    TRAINING_PHASES = 5

    def __init__(
        self,
        db: AsyncSession | None = None,
        task_executor: TaskExecutor | None = None,
    ) -> None:
        """Initialize the trainer.

        Args:
            db: Database session for collecting training data.
            task_executor: Task executor for progress reporting.
        """
        self.db = db
        self.executor = task_executor
        self.settings = get_settings().ml_classification

    async def train_from_confirmed(
        self,
        task_id: UUID,
        algorithm: Literal["random_forest", "xgboost", "gradient_boosting"] = "random_forest",
        notes: str | None = None,
    ) -> str:
        """Train a model from confirmed asset classifications.

        Args:
            task_id: Background task ID for progress reporting.
            algorithm: ML algorithm to use.
            notes: Optional notes about the training run.

        Returns:
            Version string of the saved model.

        Raises:
            TrainingError: If training fails or accuracy is too low.
            ValueError: If database session is not provided.
        """
        if self.db is None:
            raise ValueError("Database session required for training from confirmed assets")

        if self.executor is None:
            raise ValueError("Task executor required for progress reporting")

        # Phase 1: Start task
        await self.executor.start_task(task_id, total_items=self.TRAINING_PHASES)

        try:
            # Phase 2: Collect training data
            logger.info("Collecting training data from confirmed assets")
            builder = DatasetBuilder()
            dataset = await builder.from_confirmed_assets(self.db)
            await self._update_progress(task_id, 1, "Collected training data")

            # Phase 3: Validate dataset
            self._validate_dataset(dataset)
            await self._update_progress(task_id, 1, "Validated dataset")

            # Phase 4: Train model
            logger.info(
                "Training model",
                algorithm=algorithm,
                samples=dataset.n_samples,
                classes=dataset.n_classes,
            )
            split = DatasetBuilder.train_test_split(dataset)
            classifier, stats = self._train_model(split.train, algorithm)
            await self._update_progress(task_id, 1, "Trained model")

            # Phase 5: Evaluate
            metrics = self._evaluate(classifier, split.test)
            logger.info(
                "Model evaluation",
                accuracy=f"{metrics.accuracy:.2%}",
                f1_macro=f"{metrics.f1_macro:.2%}",
            )

            if metrics.accuracy < self.MIN_ACCURACY_THRESHOLD:
                raise TrainingError(
                    f"Model accuracy {metrics.accuracy:.2%} is below minimum threshold "
                    f"of {self.MIN_ACCURACY_THRESHOLD:.0%}. "
                    f"Consider adding more confirmed classifications."
                )
            await self._update_progress(task_id, 1, "Evaluated model")

            # Phase 6: Save model
            stats.f1_score = metrics.f1_macro
            stats.confusion_matrix = metrics.confusion_matrix

            model_manager = ModelManager(db=self.db)
            version = await model_manager.save_model(classifier, stats, notes)
            await self._update_progress(task_id, 1, "Saved model")

            logger.info(
                "Training completed successfully",
                version=version,
                accuracy=f"{metrics.accuracy:.2%}",
            )

            return version

        except TrainingError:
            raise
        except Exception as e:
            logger.exception("Training failed", error=str(e))
            raise TrainingError(f"Training failed: {e}") from e

    def train_from_synthetic(
        self,
        samples_per_class: int = 5000,
        algorithm: Literal["random_forest", "xgboost", "gradient_boosting"] = "random_forest",
        seed: int = 42,
        include_edge_cases: bool = True,
        edge_case_ratio: float = 0.15,
    ) -> tuple[MLClassifier, TrainingStats, EvaluationMetrics]:
        """Train a model from synthetic data.

        Used for building the shipped model without real customer data.
        Uses improved sub-type based generation with realistic distributions.

        Args:
            samples_per_class: Number of synthetic samples per asset type.
            algorithm: ML algorithm to use.
            seed: Random seed for reproducibility.
            include_edge_cases: Whether to include edge case samples.
            edge_case_ratio: Proportion of samples that are edge cases.

        Returns:
            Tuple of (trained classifier, training stats, evaluation metrics).
        """
        logger.info(
            "Generating synthetic training data",
            samples_per_class=samples_per_class,
            seed=seed,
            include_edge_cases=include_edge_cases,
            edge_case_ratio=edge_case_ratio,
        )

        # Generate diverse synthetic dataset with sub-type variants and edge cases
        generator = SyntheticDataGenerator(seed=seed)
        dataset = generator.generate_diverse_dataset(
            samples_per_class=samples_per_class,
            include_edge_cases=include_edge_cases,
            edge_case_ratio=edge_case_ratio,
        )

        # Validate
        self._validate_dataset(dataset)

        # Split and train
        split = DatasetBuilder.train_test_split(dataset, random_state=seed)
        classifier, stats = self._train_model(split.train, algorithm)

        # Evaluate
        metrics = self._evaluate(classifier, split.test)
        stats.f1_score = metrics.f1_macro
        stats.confusion_matrix = metrics.confusion_matrix

        logger.info(
            "Synthetic model training completed",
            accuracy=f"{metrics.accuracy:.2%}",
            f1_macro=f"{metrics.f1_macro:.2%}",
            samples=dataset.n_samples,
        )

        return classifier, stats, metrics

    def _validate_dataset(self, dataset: TrainingDataset) -> None:
        """Validate that a dataset meets training requirements.

        Args:
            dataset: Dataset to validate.

        Raises:
            TrainingError: If dataset doesn't meet requirements.
        """
        min_samples = self.settings.min_training_samples
        min_per_class = self.settings.min_samples_per_class

        if dataset.n_samples < min_samples:
            raise TrainingError(
                f"Insufficient training data: {dataset.n_samples} samples, "
                f"minimum required is {min_samples}. "
                f"Confirm more asset classifications first."
            )

        distribution = dataset.class_distribution()
        small_classes = [
            (name, count)
            for name, count in distribution.items()
            if count < min_per_class
        ]

        if small_classes:
            details = ", ".join(f"{name}: {count}" for name, count in small_classes)
            raise TrainingError(
                f"Some classes have too few samples (minimum {min_per_class}): {details}. "
                f"Confirm more assets of these types."
            )

        logger.info(
            "Dataset validated",
            samples=dataset.n_samples,
            classes=dataset.n_classes,
            distribution=distribution,
        )

    def _train_model(
        self,
        train_data: TrainingDataset,
        algorithm: str,
    ) -> tuple[MLClassifier, TrainingStats]:
        """Train a model on the provided dataset.

        Args:
            train_data: Training dataset.
            algorithm: Algorithm to use.

        Returns:
            Tuple of (trained classifier, training stats).
        """
        # Create untrained model
        model = MLClassifier.create_model(algorithm)  # type: ignore[arg-type]

        # Fit the model
        model.fit(train_data.features, train_data.labels)

        # Create label encoder with class names
        label_encoder = LabelEncoder()
        label_encoder.classes_ = np.array(train_data.class_names)

        # Get feature importances if available
        feature_importances = None
        if hasattr(model, "feature_importances_"):
            from flowlens.classification.ml.feature_transformer import FeatureTransformer

            transformer = FeatureTransformer()
            importances = model.feature_importances_
            feature_importances = {
                name: float(imp)
                for name, imp in zip(transformer.feature_names, importances, strict=True)
            }

        # Create classifier wrapper
        classifier = MLClassifier(
            model=model,
            label_encoder=label_encoder,
            algorithm=algorithm,
        )

        # Create training stats
        stats = TrainingStats(
            training_samples=train_data.n_samples,
            accuracy=0.0,  # Will be updated after evaluation
            class_distribution=train_data.class_distribution(),
            feature_importances=feature_importances,
        )

        return classifier, stats

    def _evaluate(
        self,
        classifier: MLClassifier,
        test_data: TrainingDataset,
    ) -> EvaluationMetrics:
        """Evaluate a classifier on test data.

        Args:
            classifier: Trained classifier.
            test_data: Test dataset.

        Returns:
            Evaluation metrics.
        """
        # Get predictions
        predictions = []
        for i in range(len(test_data.labels)):
            features = test_data.features[i]
            pred_type, _ = classifier.predict(features)
            # Convert type name back to label index
            pred_idx = test_data.class_names.index(pred_type)
            predictions.append(pred_idx)

        predictions = np.array(predictions)

        # Compute metrics
        accuracy = accuracy_score(test_data.labels, predictions)
        f1_macro = f1_score(test_data.labels, predictions, average="macro")
        f1_weighted = f1_score(test_data.labels, predictions, average="weighted")
        conf_matrix = confusion_matrix(test_data.labels, predictions)

        return EvaluationMetrics(
            accuracy=float(accuracy),
            f1_macro=float(f1_macro),
            f1_weighted=float(f1_weighted),
            confusion_matrix=conf_matrix.tolist(),
            class_names=test_data.class_names,
        )

    async def _update_progress(
        self,
        task_id: UUID,
        processed: int,
        message: str,
    ) -> None:
        """Update task progress.

        Args:
            task_id: Task ID.
            processed: Number of phases completed.
            message: Progress message.
        """
        if self.executor is None:
            return

        await self.executor.update_task_progress(
            task_id,
            processed=processed,
            successful=processed,
        )
        logger.debug("Training progress", phase=processed, message=message)
