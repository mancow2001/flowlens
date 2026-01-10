"""Asset classification API endpoints.

Provides endpoints for viewing and managing asset classification.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.api.dependencies import get_db
from flowlens.classification.feature_extractor import FeatureExtractor
from flowlens.classification.scoring_engine import ScoringEngine
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset, AssetType
from flowlens.models.classification import ClassificationHistory
from flowlens.schemas.asset_classification import (
    ClassificationHistoryEntry,
    ClassificationHistoryResponse,
    ClassificationResponse,
    FeaturesUsed,
    LockClassificationRequest,
    LockClassificationResponse,
    ReclassifyRequest,
    ReclassifyResponse,
    SignalBreakdown,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/assets", tags=["classification"])


@router.get("/{asset_id}/classification", response_model=ClassificationResponse)
async def get_asset_classification(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ClassificationResponse:
    """Get classification scores and recommendation for an asset.

    Computes classification scores for all asset types based on
    behavioral features extracted from flow data.
    """
    # Get asset
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Extract features
    extractor = FeatureExtractor(db)
    features = await extractor.extract_features(
        ip_address=asset.ip_address,
        window_size="24hour",
    )

    # Compute scores
    engine = ScoringEngine()
    classification = engine.compute_scores(
        features=features,
        current_type=asset.asset_type.value if asset.asset_type else None,
    )

    # Build response
    scores_dict = {}
    for asset_type, type_score in classification.scores.items():
        scores_dict[asset_type.value] = SignalBreakdown(
            score=type_score.score,
            breakdown=type_score.signal_breakdown,
        )

    features_used = FeaturesUsed(
        window_size=features.window_size,
        total_flows=features.total_flows,
        fan_in_count=features.fan_in_count,
        fan_out_count=features.fan_out_count,
        listening_ports=features.persistent_listener_ports[:5] if features.persistent_listener_ports else [],
        has_db_ports=features.has_db_ports,
        has_web_ports=features.has_web_ports,
        has_storage_ports=features.has_storage_ports,
        active_hours=features.active_hours_count,
        business_hours_ratio=round(features.business_hours_ratio, 2) if features.business_hours_ratio else None,
    )

    return ClassificationResponse(
        ip_address=classification.ip_address,
        current_type=classification.current_type,
        recommended_type=classification.recommended_type.value,
        confidence=classification.confidence,
        should_auto_update=classification.should_auto_update,
        scores=scores_dict,
        features_used=features_used,
    )


@router.post("/{asset_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_asset(
    asset_id: uuid.UUID,
    request: ReclassifyRequest = ReclassifyRequest(),
    db: AsyncSession = Depends(get_db),
) -> ReclassifyResponse:
    """Force reclassification of an asset.

    Optionally applies the classification result to update the asset type.
    """
    # Get asset
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Check if locked
    if request.apply and asset.classification_locked:
        return ReclassifyResponse(
            success=False,
            applied=False,
            message="Asset classification is locked. Unlock it first to apply changes.",
        )

    # Extract features
    extractor = FeatureExtractor(db)
    features = await extractor.extract_features(
        ip_address=asset.ip_address,
        window_size="24hour",
    )

    # Compute scores
    engine = ScoringEngine()
    classification = engine.compute_scores(
        features=features,
        current_type=asset.asset_type.value if asset.asset_type else None,
    )

    # Build classification response
    scores_dict = {}
    for asset_type, type_score in classification.scores.items():
        scores_dict[asset_type.value] = SignalBreakdown(
            score=type_score.score,
            breakdown=type_score.signal_breakdown,
        )

    features_used = FeaturesUsed(
        window_size=features.window_size,
        total_flows=features.total_flows,
        fan_in_count=features.fan_in_count,
        fan_out_count=features.fan_out_count,
        listening_ports=features.persistent_listener_ports[:5] if features.persistent_listener_ports else [],
        has_db_ports=features.has_db_ports,
        has_web_ports=features.has_web_ports,
        has_storage_ports=features.has_storage_ports,
        active_hours=features.active_hours_count,
        business_hours_ratio=round(features.business_hours_ratio, 2) if features.business_hours_ratio else None,
    )

    classification_response = ClassificationResponse(
        ip_address=classification.ip_address,
        current_type=classification.current_type,
        recommended_type=classification.recommended_type.value,
        confidence=classification.confidence,
        should_auto_update=classification.should_auto_update,
        scores=scores_dict,
        features_used=features_used,
    )

    applied = False
    message = None

    # Apply if requested
    if request.apply:
        now = datetime.utcnow()
        previous_type = asset.asset_type.value if asset.asset_type else None
        new_type = classification.recommended_type.value

        # Map to AssetType
        asset_type_mapping = {
            "server": AssetType.SERVER,
            "workstation": AssetType.WORKSTATION,
            "database": AssetType.DATABASE,
            "load_balancer": AssetType.LOAD_BALANCER,
            "network_device": AssetType.ROUTER,
            "storage": AssetType.STORAGE,
            "container": AssetType.CONTAINER,
            "virtual_machine": AssetType.VIRTUAL_MACHINE,
            "cloud_service": AssetType.CLOUD_SERVICE,
            "unknown": AssetType.UNKNOWN,
        }

        new_asset_type = asset_type_mapping.get(new_type, AssetType.UNKNOWN)

        # Update asset
        asset.asset_type = new_asset_type
        asset.classification_confidence = classification.confidence
        asset.classification_scores = {k: v.to_dict() for k, v in classification.scores.items()}
        asset.last_classified_at = now
        asset.classification_method = "api"

        # Record history
        history = ClassificationHistory(
            id=uuid.uuid4(),
            asset_id=asset.id,
            classified_at=now,
            previous_type=previous_type,
            new_type=new_type,
            confidence=classification.confidence,
            scores={k.value: v.to_dict() for k, v in classification.scores.items()},
            features_snapshot=classification.features_summary,
            triggered_by="api",
        )
        db.add(history)

        await db.commit()

        applied = True
        message = f"Asset type changed from {previous_type or 'unknown'} to {new_type}"

        logger.info(
            "Asset reclassified via API",
            asset_id=str(asset_id),
            previous=previous_type,
            new=new_type,
            confidence=classification.confidence,
        )

    return ReclassifyResponse(
        success=True,
        classification=classification_response,
        applied=applied,
        message=message,
    )


@router.post("/{asset_id}/lock-classification", response_model=LockClassificationResponse)
async def lock_classification(
    asset_id: uuid.UUID,
    request: LockClassificationRequest,
    db: AsyncSession = Depends(get_db),
) -> LockClassificationResponse:
    """Lock or unlock auto-classification for an asset.

    Locked assets will not be automatically reclassified by the
    classification worker.
    """
    # Get asset
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Update lock status
    asset.classification_locked = request.locked
    await db.commit()

    action = "locked" if request.locked else "unlocked"
    logger.info(
        f"Classification {action}",
        asset_id=str(asset_id),
        ip=asset.ip_address,
    )

    return LockClassificationResponse(
        success=True,
        asset_id=asset_id,
        classification_locked=asset.classification_locked,
        message=f"Classification {action} for asset {asset.ip_address}",
    )


@router.get("/{asset_id}/classification/history", response_model=ClassificationHistoryResponse)
async def get_classification_history(
    asset_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> ClassificationHistoryResponse:
    """Get classification history for an asset.

    Returns a list of past classification changes with timestamps,
    confidence scores, and score breakdowns.
    """
    # Get asset
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Get history entries
    query = (
        select(ClassificationHistory)
        .where(ClassificationHistory.asset_id == asset_id)
        .order_by(ClassificationHistory.classified_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    history_entries = result.scalars().all()

    # Count total
    count_query = (
        select(ClassificationHistory)
        .where(ClassificationHistory.asset_id == asset_id)
    )
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Build response
    history = []
    for entry in history_entries:
        scores_dict = None
        if entry.scores:
            scores_dict = {}
            for type_name, score_data in entry.scores.items():
                if isinstance(score_data, dict):
                    scores_dict[type_name] = SignalBreakdown(
                        score=score_data.get("score", 0),
                        breakdown=score_data.get("breakdown", {}),
                    )

        history.append(ClassificationHistoryEntry(
            id=entry.id,
            classified_at=entry.classified_at,
            previous_type=entry.previous_type,
            new_type=entry.new_type,
            confidence=entry.confidence,
            triggered_by=entry.triggered_by,
            scores=scores_dict,
            features_snapshot=entry.features_snapshot,
        ))

    return ClassificationHistoryResponse(
        asset_id=asset_id,
        ip_address=asset.ip_address,
        history=history,
        total=total,
    )
