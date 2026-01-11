#!/usr/bin/env python
"""Build the shipped ML model using synthetic data.

This script generates a pre-trained classification model that ships with
FlowLens. The model is trained on improved synthetic data that includes:

  - 46 sub-type variants across 9 asset types
  - Realistic log-normal and beta distributions
  - 5 workload modes (idle, light, normal, heavy, burst)
  - Edge cases (minimal traffic, peak load, unusual ports, mixed roles)

Usage:
    python scripts/build_shipped_model.py [OPTIONS]

Options:
    --samples-per-class INT  Number of samples per asset type (default: 5000)
    --algorithm STR          Algorithm: random_forest, xgboost, gradient_boosting
    --seed INT               Random seed for reproducibility (default: 42)
    --output PATH            Output path for the model file
    --min-accuracy FLOAT     Minimum required accuracy (default: 0.85)
    --no-edge-cases          Disable edge case generation
    --edge-case-ratio FLOAT  Proportion of edge cases (default: 0.15)

Example:
    python scripts/build_shipped_model.py --samples-per-class 5000
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
        default=5000,
        help="Number of synthetic samples per asset type (default: 5000)",
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
    parser.add_argument(
        "--no-edge-cases",
        action="store_true",
        help="Disable edge case generation",
    )
    parser.add_argument(
        "--edge-case-ratio",
        type=float,
        default=0.15,
        help="Proportion of edge cases (default: 0.15)",
    )

    args = parser.parse_args()

    total_samples = args.samples_per_class * 9
    edge_samples = int(args.samples_per_class * args.edge_case_ratio) if not args.no_edge_cases else 0

    print("=" * 70)
    print("FlowLens Shipped Model Builder (Improved Synthetic Data)")
    print("=" * 70)
    print()
    print("Configuration:")
    print(f"  Samples per class:  {args.samples_per_class:,}")
    print(f"  Total samples:      {total_samples:,}")
    print(f"  Algorithm:          {args.algorithm}")
    print(f"  Random seed:        {args.seed}")
    print(f"  Edge cases:         {'disabled' if args.no_edge_cases else f'{args.edge_case_ratio:.0%} ({edge_samples:,} per class)'}")
    print(f"  Output path:        {args.output}")
    print(f"  Min accuracy:       {args.min_accuracy:.0%}")
    print()
    print("Data Generation Features:")
    print("  - 46 sub-type variants (e.g., MySQL, MongoDB, Redis for databases)")
    print("  - Log-normal traffic distributions (realistic heavy-tail patterns)")
    print("  - Beta distributions for temporal patterns")
    print("  - 5 workload modes: idle, light, normal, heavy, burst")
    if not args.no_edge_cases:
        print("  - Edge cases: minimal, peak, unusual_ports, mixed_role, intermittent")
    print()
    print("=" * 70)
    print()

    # Create trainer (no database needed for synthetic training)
    trainer = MLTrainer()

    # Train from synthetic data
    print("Generating synthetic training data and training model...")
    print("This may take a moment for large datasets...")
    print()

    classifier, stats, metrics = trainer.train_from_synthetic(
        samples_per_class=args.samples_per_class,
        algorithm=args.algorithm,  # type: ignore[arg-type]
        seed=args.seed,
        include_edge_cases=not args.no_edge_cases,
        edge_case_ratio=args.edge_case_ratio,
    )

    # Print results
    print()
    print("Training Results:")
    print("-" * 50)
    print(f"  Training samples:    {stats.training_samples:,}")
    print(f"  Test accuracy:       {metrics.accuracy:.2%}")
    print(f"  Test F1 (macro):     {metrics.f1_macro:.2%}")
    print(f"  Test F1 (weighted):  {metrics.f1_weighted:.2%}")
    print()

    # Print class distribution
    print("Class Distribution:")
    print("-" * 50)
    if stats.class_distribution:
        for class_name, count in sorted(stats.class_distribution.items()):
            print(f"  {class_name:20s}: {count:,}")
    print()

    # Print feature importances (top 10)
    if stats.feature_importances:
        print("Top 10 Feature Importances:")
        print("-" * 50)
        sorted_features = sorted(
            stats.feature_importances.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        for name, importance in sorted_features:
            bar = "#" * int(importance * 50)
            print(f"  {name:25s}: {importance:.4f} {bar}")
        print()

    # Print per-class accuracy from confusion matrix
    print("Per-Class Accuracy:")
    print("-" * 50)
    for i, class_name in enumerate(metrics.class_names):
        row = metrics.confusion_matrix[i]
        total = sum(row)
        correct = row[i]
        accuracy = correct / total if total > 0 else 0
        print(f"  {class_name:20s}: {accuracy:.1%} ({correct}/{total})")
    print()

    # Check accuracy threshold
    if metrics.accuracy < args.min_accuracy:
        print(f"ERROR: Model accuracy {metrics.accuracy:.2%} is below minimum threshold {args.min_accuracy:.0%}")
        print()
        print("Consider:")
        print("  - Increasing samples-per-class")
        print("  - Adjusting synthetic data profiles in synthetic.py")
        print("  - Using a different algorithm (try xgboost)")
        return 1

    # Save the model
    print("Saving model...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    classifier.model_version = "shipped"
    classifier.save(args.output)

    file_size = args.output.stat().st_size
    print()
    print("=" * 70)
    print("SUCCESS!")
    print("=" * 70)
    print(f"  Model saved to:  {args.output}")
    print(f"  File size:       {file_size / 1024:.1f} KB ({file_size / 1024 / 1024:.2f} MB)")
    print(f"  Accuracy:        {metrics.accuracy:.2%}")
    print(f"  F1 Score:        {metrics.f1_macro:.2%}")
    print(f"  Classes:         {len(metrics.class_names)}")
    print(f"  Training data:   {stats.training_samples:,} samples")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
