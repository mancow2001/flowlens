"""Training dataset utilities for ML classification.

Provides data structures and builders for creating training datasets
from confirmed asset classifications or synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from sklearn.model_selection import train_test_split as sklearn_split
from sqlalchemy import select

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import (
    BehavioralFeatures,
    FeatureExtractor,
)
from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


@dataclass
class TrainingDataset:
    """A dataset for ML model training.

    Attributes:
        features: Feature matrix of shape (n_samples, n_features).
        labels: Label array of shape (n_samples,).
        asset_ids: List of asset UUIDs for traceability.
        class_names: List of unique class label names.
    """

    features: np.ndarray
    labels: np.ndarray
    asset_ids: list[UUID] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)

    @property
    def n_samples(self) -> int:
        """Number of samples in the dataset."""
        return len(self.labels)

    @property
    def n_features(self) -> int:
        """Number of features per sample."""
        return self.features.shape[1] if len(self.features.shape) > 1 else 0

    @property
    def n_classes(self) -> int:
        """Number of unique classes."""
        return len(self.class_names)

    def class_distribution(self) -> dict[str, int]:
        """Get the count of samples per class.

        Returns:
            Dictionary mapping class names to sample counts.
        """
        unique, counts = np.unique(self.labels, return_counts=True)
        return {
            self.class_names[int(label)]: int(count)
            for label, count in zip(unique, counts, strict=True)
        }


@dataclass
class DatasetSplit:
    """A train/test split of a dataset.

    Attributes:
        train: Training dataset.
        test: Test dataset.
    """

    train: TrainingDataset
    test: TrainingDataset


class DatasetBuilder:
    """Builds training datasets from various sources.

    Supports building datasets from:
    - Confirmed asset classifications in the database
    - Synthetic data generators
    - Raw feature lists
    """

    def __init__(self) -> None:
        """Initialize the dataset builder."""
        self.settings = get_settings().ml_classification
        self.transformer = FeatureTransformer()

    async def from_confirmed_assets(
        self,
        db: AsyncSession,
        min_flows: int | None = None,
    ) -> TrainingDataset:
        """Build a dataset from confirmed asset classifications.

        Collects assets where classification is locked (user-confirmed)
        or classification_method is 'manual'.

        Args:
            db: Database session.
            min_flows: Minimum flows required for an asset to be included.
                       Defaults to ml_min_flows from config.

        Returns:
            TrainingDataset with features from confirmed assets.

        Raises:
            ValueError: If no confirmed assets found.
        """
        if min_flows is None:
            min_flows = self.settings.ml_min_flows

        # Query confirmed assets
        query = select(Asset).where(
            Asset.deleted_at.is_(None),
            Asset.is_internal == True,  # noqa: E712
            Asset.asset_type != "unknown",
            (Asset.classification_locked == True)  # noqa: E712
            | (Asset.classification_method == "manual"),
        )

        result = await db.execute(query)
        assets = result.scalars().all()

        if not assets:
            raise ValueError(
                "No confirmed assets found. "
                "Lock asset classifications or set classification_method='manual' first."
            )

        logger.info(
            "Found confirmed assets for training",
            count=len(assets),
        )

        # Extract features for each asset
        extractor = FeatureExtractor(db)
        features_list: list[BehavioralFeatures] = []
        labels: list[str] = []
        asset_ids: list[UUID] = []
        skipped = 0

        for asset in assets:
            try:
                # Extract behavioral features from flow data
                features = await extractor.extract_features(
                    str(asset.ip_address),
                    window_size="5min",
                )

                # Skip if insufficient flows
                if features.total_flows < min_flows:
                    skipped += 1
                    continue

                # Map to classifiable type
                asset_type = self._map_to_classifiable_type(str(asset.asset_type))
                if asset_type is None:
                    skipped += 1
                    continue

                features_list.append(features)
                labels.append(asset_type)
                asset_ids.append(asset.id)

            except Exception as e:
                logger.warning(
                    "Failed to extract features for asset",
                    asset_id=str(asset.id),
                    error=str(e),
                )
                skipped += 1

        if skipped > 0:
            logger.info(
                "Skipped assets during feature extraction",
                skipped=skipped,
                reason="insufficient_flows_or_unknown_type",
            )

        if not features_list:
            raise ValueError(
                f"No assets with sufficient flow data (min_flows={min_flows}). "
                "Ensure assets have been observed long enough."
            )

        return self.from_behavioral_features(features_list, labels, asset_ids)

    def from_behavioral_features(
        self,
        features_list: list[BehavioralFeatures],
        labels: list[str],
        asset_ids: list[UUID] | None = None,
    ) -> TrainingDataset:
        """Build a dataset from BehavioralFeatures instances.

        Args:
            features_list: List of BehavioralFeatures.
            labels: Corresponding class labels.
            asset_ids: Optional list of asset UUIDs for traceability.

        Returns:
            TrainingDataset with transformed features.
        """
        if len(features_list) != len(labels):
            raise ValueError(
                f"Mismatched lengths: {len(features_list)} features, {len(labels)} labels"
            )

        # Transform to ML feature vectors
        feature_matrix = self.transformer.transform_batch(features_list)

        # Encode labels
        unique_labels = sorted(set(labels))
        label_to_idx = {label: idx for idx, label in enumerate(unique_labels)}
        encoded_labels = np.array([label_to_idx[label] for label in labels])

        return TrainingDataset(
            features=feature_matrix,
            labels=encoded_labels,
            asset_ids=asset_ids or [],
            class_names=unique_labels,
        )

    def from_feature_vectors(
        self,
        features: np.ndarray,
        labels: list[str],
        asset_ids: list[UUID] | None = None,
    ) -> TrainingDataset:
        """Build a dataset from raw feature vectors.

        Args:
            features: Feature matrix of shape (n_samples, n_features).
            labels: Corresponding class labels.
            asset_ids: Optional list of asset UUIDs.

        Returns:
            TrainingDataset with the provided features.
        """
        if features.shape[0] != len(labels):
            raise ValueError(
                f"Mismatched lengths: {features.shape[0]} features, {len(labels)} labels"
            )

        unique_labels = sorted(set(labels))
        label_to_idx = {label: idx for idx, label in enumerate(unique_labels)}
        encoded_labels = np.array([label_to_idx[label] for label in labels])

        return TrainingDataset(
            features=features,
            labels=encoded_labels,
            asset_ids=asset_ids or [],
            class_names=unique_labels,
        )

    @staticmethod
    def train_test_split(
        dataset: TrainingDataset,
        test_ratio: float = 0.2,
        random_state: int = 42,
        stratify: bool = True,
    ) -> DatasetSplit:
        """Split a dataset into training and test sets.

        Args:
            dataset: Dataset to split.
            test_ratio: Fraction of data to use for testing.
            random_state: Random seed for reproducibility.
            stratify: Whether to stratify by label (maintain class proportions).

        Returns:
            DatasetSplit with train and test datasets.
        """
        stratify_labels = dataset.labels if stratify else None

        # Split features and labels
        X_train, X_test, y_train, y_test, idx_train, idx_test = sklearn_split(
            dataset.features,
            dataset.labels,
            np.arange(len(dataset.labels)),
            test_size=test_ratio,
            random_state=random_state,
            stratify=stratify_labels,
        )

        # Split asset IDs if present
        train_ids = (
            [dataset.asset_ids[i] for i in idx_train] if dataset.asset_ids else []
        )
        test_ids = [dataset.asset_ids[i] for i in idx_test] if dataset.asset_ids else []

        return DatasetSplit(
            train=TrainingDataset(
                features=X_train,
                labels=y_train,
                asset_ids=train_ids,
                class_names=dataset.class_names,
            ),
            test=TrainingDataset(
                features=X_test,
                labels=y_test,
                asset_ids=test_ids,
                class_names=dataset.class_names,
            ),
        )

    @staticmethod
    def _map_to_classifiable_type(asset_type: str) -> str | None:
        """Map an asset type string to a ClassifiableAssetType value.

        Args:
            asset_type: Asset type string from database.

        Returns:
            Classifiable type string or None if not mappable.
        """
        # Direct mapping for types that exist in ClassifiableAssetType
        try:
            classifiable = ClassifiableAssetType(asset_type)
            if classifiable == ClassifiableAssetType.UNKNOWN:
                return None
            return classifiable.value
        except ValueError:
            pass

        # Map similar types
        type_mapping = {
            "router": "network_device",
            "switch": "network_device",
            "firewall": "network_device",
        }

        mapped = type_mapping.get(asset_type.lower())
        if mapped:
            return mapped

        return None
