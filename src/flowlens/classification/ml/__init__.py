"""ML-based classification module.

Provides lightweight machine learning classification for faster device type
recognition. Ships with a pre-built model and supports user-trained custom models.
"""

from flowlens.classification.ml.classifier import MLClassifier
from flowlens.classification.ml.dataset import DatasetBuilder, DatasetSplit, TrainingDataset
from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.classification.ml.hybrid_engine import HybridClassificationEngine
from flowlens.classification.ml.model_manager import ModelManager, TrainingStats
from flowlens.classification.ml.synthetic import SyntheticDataGenerator
from flowlens.classification.ml.trainer import MLTrainer, TrainingError

__all__ = [
    "DatasetBuilder",
    "DatasetSplit",
    "FeatureTransformer",
    "HybridClassificationEngine",
    "MLClassifier",
    "MLTrainer",
    "ModelManager",
    "SyntheticDataGenerator",
    "TrainingDataset",
    "TrainingError",
    "TrainingStats",
]
