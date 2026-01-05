"""Discovery status API endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from flowlens.api.dependencies import DbSession, ViewerUser
from flowlens.models.discovery import DiscoveryStatus
from flowlens.schemas.discovery import DiscoveryLastScanResponse, DiscoveryStatusResponse

router = APIRouter(prefix="/discovery", tags=["discovery"])

KUBERNETES_PROVIDER = "kubernetes"


async def _get_or_create_status(db: DbSession, provider: str) -> DiscoveryStatus:
    result = await db.execute(
        select(DiscoveryStatus).where(DiscoveryStatus.provider == provider)
    )
    status = result.scalar_one_or_none()
    if status:
        return status
    status = DiscoveryStatus(provider=provider, status="idle")
    db.add(status)
    await db.flush()
    return status


@router.get("/kubernetes/status", response_model=DiscoveryStatusResponse)
async def get_kubernetes_discovery_status(
    db: DbSession,
    _user: ViewerUser,
) -> DiscoveryStatusResponse:
    """Get Kubernetes discovery sync status."""
    status = await _get_or_create_status(db, KUBERNETES_PROVIDER)
    return DiscoveryStatusResponse(
        provider=status.provider,
        status=status.status,
        last_started_at=status.last_started_at,
        last_completed_at=status.last_completed_at,
        last_success_at=status.last_success_at,
        last_error=status.last_error,
    )


@router.get("/kubernetes/last-scan", response_model=DiscoveryLastScanResponse)
async def get_kubernetes_last_scan(
    db: DbSession,
    _user: ViewerUser,
) -> DiscoveryLastScanResponse:
    """Get Kubernetes discovery last scan timestamps."""
    status = await _get_or_create_status(db, KUBERNETES_PROVIDER)
    return DiscoveryLastScanResponse(
        provider=status.provider,
        last_scan_at=status.last_completed_at,
        last_success_at=status.last_success_at,
        status=status.status,
    )
