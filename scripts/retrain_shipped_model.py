#!/usr/bin/env python3
"""Retrain the shipped ML classification model.

This script regenerates the shipped model with all asset types,
including the 15 new types added for comprehensive classification coverage.

Usage:
    python scripts/retrain_shipped_model.py [--samples-per-class 5000] [--seed 42]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flowlens.classification.ml.trainer import MLTrainer
from flowlens.classification.ml.model_manager import SHIPPED_MODEL_PATH
from flowlens.classification.constants import ClassifiableAssetType


def main() -> int:
    """Retrain the shipped model with synthetic data."""
    parser = argparse.ArgumentParser(
        description="Retrain the shipped ML classification model"
    )
    parser.add_argument(
        "--samples-per-class",
        type=int,
        default=5000,
        help="Number of synthetic samples per asset type (default: 5000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--algorithm",
        choices=["random_forest", "xgboost", "gradient_boosting"],
        default="random_forest",
        help="ML algorithm to use (default: random_forest)",
    )
    parser.add_argument(
        "--edge-case-ratio",
        type=float,
        default=0.15,
        help="Proportion of samples that are edge cases (default: 0.15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Train but don't save the model",
    )

    args = parser.parse_args()

    # Show what we're training
    asset_types = [t.value for t in ClassifiableAssetType]
    print(f"\n{'='*60}")
    print("FlowLens ML Model Retraining")
    print(f"{'='*60}")
    print(f"\nAsset types to train ({len(asset_types)}):")
    for i, t in enumerate(sorted(asset_types), 1):
        print(f"  {i:2}. {t}")

    print(f"\nConfiguration:")
    print(f"  - Samples per class: {args.samples_per_class:,}")
    print(f"  - Total samples: ~{args.samples_per_class * len(asset_types):,}")
    print(f"  - Algorithm: {args.algorithm}")
    print(f"  - Edge case ratio: {args.edge_case_ratio:.0%}")
    print(f"  - Random seed: {args.seed}")
    print(f"  - Model output: {SHIPPED_MODEL_PATH}")
    print(f"  - Dry run: {args.dry_run}")
    print()

    # Train
    print("Training model...")
    trainer = MLTrainer()

    classifier, stats, metrics = trainer.train_from_synthetic(
        samples_per_class=args.samples_per_class,
        algorithm=args.algorithm,
        seed=args.seed,
        include_edge_cases=True,
        edge_case_ratio=args.edge_case_ratio,
    )

    # Show results
    print(f"\n{'='*60}")
    print("Training Results")
    print(f"{'='*60}")
    print(f"\nMetrics:")
    print(f"  - Accuracy: {metrics.accuracy:.2%}")
    print(f"  - F1 (macro): {metrics.f1_macro:.2%}")
    print(f"  - F1 (weighted): {metrics.f1_weighted:.2%}")
    print(f"  - Training samples: {stats.training_samples:,}")

    print(f"\nClasses trained: {len(metrics.class_names)}")
    for name in sorted(metrics.class_names):
        print(f"  - {name}")

    # Save if not dry run
    if args.dry_run:
        print("\n[DRY RUN] Model not saved.")
    else:
        print(f"\nSaving model to {SHIPPED_MODEL_PATH}...")
        SHIPPED_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        classifier.save(SHIPPED_MODEL_PATH)
        print(f"Model saved ({SHIPPED_MODEL_PATH.stat().st_size / 1024:.1f} KB)")

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
