#!/usr/bin/env python
"""Build the shipped ML model using synthetic data.

This script generates a pre-trained classification model that ships with
FlowLens. The model is trained on synthetic data that mimics realistic
traffic patterns for each asset type.

Usage:
    python scripts/build_shipped_model.py [OPTIONS]

Options:
    --samples-per-class INT  Number of samples per asset type (default: 200)
    --algorithm STR          Algorithm to use: random_forest, xgboost, gradient_boosting (default: random_forest)
    --seed INT               Random seed for reproducibility (default: 42)
    --output PATH            Output path (default: src/flowlens/classification/ml/models/shipped_model.joblib)
    --min-accuracy FLOAT     Minimum required accuracy (default: 0.85)

Example:
    python scripts/build_shipped_model.py --samples-per-class 200 --algorithm random_forest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flowlens.classification.ml.trainer import MLTrainer


def main() -> int:
    """Build the shipped model."""
    parser = argparse.ArgumentParser(
        description="Build the shipped ML classification model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--samples-per-class",
        type=int,
        default=200,
        help="Number of synthetic samples per asset type (default: 200)",
    )
    parser.add_argument(
        "--algorithm",
        choices=["random_forest", "xgboost", "gradient_boosting"],
        default="random_forest",
        help="ML algorithm to use (default: random_forest)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/flowlens/classification/ml/models/shipped_model.joblib"),
        help="Output path for the model file",
    )
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.85,
        help="Minimum required accuracy (default: 0.85)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("FlowLens Shipped Model Builder")
    print("=" * 60)
    print(f"  Samples per class: {args.samples_per_class}")
    print(f"  Algorithm: {args.algorithm}")
    print(f"  Random seed: {args.seed}")
    print(f"  Output path: {args.output}")
    print(f"  Min accuracy: {args.min_accuracy:.0%}")
    print("=" * 60)
    print()

    # Create trainer (no database needed for synthetic training)
    trainer = MLTrainer()

    # Train from synthetic data
    print("Generating synthetic training data...")
    classifier, stats, metrics = trainer.train_from_synthetic(
        samples_per_class=args.samples_per_class,
        algorithm=args.algorithm,  # type: ignore[arg-type]
        seed=args.seed,
    )

    # Print results
    print()
    print("Training Results:")
    print("-" * 40)
    print(f"  Training samples: {stats.training_samples}")
    print(f"  Test accuracy: {metrics.accuracy:.2%}")
    print(f"  Test F1 (macro): {metrics.f1_macro:.2%}")
    print(f"  Test F1 (weighted): {metrics.f1_weighted:.2%}")
    print()

    # Print class distribution
    print("Class Distribution:")
    print("-" * 40)
    if stats.class_distribution:
        for class_name, count in sorted(stats.class_distribution.items()):
            print(f"  {class_name}: {count}")
    print()

    # Print feature importances (top 10)
    if stats.feature_importances:
        print("Top 10 Feature Importances:")
        print("-" * 40)
        sorted_features = sorted(
            stats.feature_importances.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        for name, importance in sorted_features:
            print(f"  {name}: {importance:.4f}")
        print()

    # Print confusion matrix
    print("Confusion Matrix:")
    print("-" * 40)
    print(f"  Classes: {metrics.class_names}")
    for i, row in enumerate(metrics.confusion_matrix):
        print(f"  {metrics.class_names[i]}: {row}")
    print()

    # Check accuracy threshold
    if metrics.accuracy < args.min_accuracy:
        print(f"ERROR: Model accuracy {metrics.accuracy:.2%} is below minimum threshold {args.min_accuracy:.0%}")
        print("Consider:")
        print("  - Increasing samples-per-class")
        print("  - Adjusting synthetic data profiles")
        print("  - Using a different algorithm")
        return 1

    # Save the model
    print("Saving model...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    classifier.model_version = "shipped"
    classifier.save(args.output)

    file_size = args.output.stat().st_size
    print()
    print("=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print(f"  Model saved to: {args.output}")
    print(f"  File size: {file_size / 1024:.1f} KB")
    print(f"  Accuracy: {metrics.accuracy:.2%}")
    print(f"  F1 Score: {metrics.f1_macro:.2%}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
