"""Startup tasks for the API service.

Contains initialization tasks that run when the API server starts.
"""

from datetime import datetime, timezone

from sqlalchemy import update

from flowlens.common.database import get_session
from flowlens.common.logging import get_logger
from flowlens.models.auth import AuthSession

logger = get_logger(__name__)


async def invalidate_all_sessions() -> int:
    """Invalidate all active sessions on startup.

    This ensures that users must re-authenticate after a server restart,
    which is important for security (e.g., after secret key rotation or
    security patches).

    Returns:
        Number of sessions that were revoked.
    """
    async with get_session() as db:
        # Revoke all active (non-revoked) sessions
        result = await db.execute(
            update(AuthSession)
            .where(AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()

        revoked_count = result.rowcount
        if revoked_count > 0:
            logger.debug(
                "Revoked all active sessions on startup",
                revoked_count=revoked_count,
            )

        return revoked_count
