"""Classification rule application task.

Applies CIDR classification rules to assets in batches with progress tracking.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.task import BackgroundTask, TaskStatus, TaskType
from flowlens.tasks.executor import TaskExecutor

logger = get_logger(__name__)

# Default batch size for processing
DEFAULT_BATCH_SIZE = 100


class ClassificationRuleTask:
    """Task for applying classification rules to assets.

    Processes assets in batches to avoid long-running transactions
    and provides progress updates.
    """

    def __init__(
        self,
        db: AsyncSession,
        executor: TaskExecutor,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        """Initialize task.

        Args:
            db: Database session.
            executor: Task executor for progress tracking.
            batch_size: Number of assets to process per batch.
        """
        self._db = db
        self._executor = executor
        self._batch_size = batch_size

    async def run(
        self,
        task_id: UUID,
        force: bool = False,
        rule_id: UUID | None = None,
    ) -> dict:
        """Run the classification rule application task.

        Args:
            task_id: Background task ID for progress tracking.
            force: If True, overwrite existing values.
            rule_id: If specified, only apply this rule (for targeted updates).

        Returns:
            Result summary.
        """
        try:
            # Count total assets to process
            count_result = await self._db.execute(
                select(Asset.id).where(Asset.deleted_at.is_(None))
            )
            total_assets = len(count_result.fetchall())

            # Start the task
            await self._executor.start_task(task_id, total_assets)
            await self._db.commit()

            # Process in batches
            offset = 0
            total_matched = 0
            total_updated = 0
            total_skipped = 0
            total_failed = 0
            sample_updates = []

            while True:
                # Check if task was cancelled
                task = await self._executor.get_task(task_id)
                if task and task.status == TaskStatus.CANCELLED.value:
                    logger.info("Task cancelled, stopping", task_id=str(task_id))
                    break

                # Fetch batch of assets
                result = await self._db.execute(
                    select(Asset)
                    .where(Asset.deleted_at.is_(None))
                    .order_by(Asset.id)
                    .offset(offset)
                    .limit(self._batch_size)
                )
                assets = result.scalars().all()

                if not assets:
                    break

                # Process batch
                batch_matched = 0
                batch_updated = 0
                batch_skipped = 0
                batch_failed = 0

                for asset in assets:
                    try:
                        matched, updated, changes = await self._process_asset(
                            asset, force, rule_id
                        )

                        if matched:
                            batch_matched += 1
                            if updated:
                                batch_updated += 1
                                # Track sample updates (first 50)
                                if len(sample_updates) < 50:
                                    sample_updates.append({
                                        "asset_id": str(asset.id),
                                        "asset_name": asset.name,
                                        "ip_address": str(asset.ip_address),
                                        "changes": changes,
                                    })
                            else:
                                batch_skipped += 1
                    except Exception as e:
                        batch_failed += 1
                        logger.warning(
                            "Failed to process asset",
                            asset_id=str(asset.id),
                            error=str(e),
                        )

                # Commit batch
                await self._db.commit()

                # Update progress
                await self._executor.update_task_progress(
                    task_id,
                    processed=len(assets),
                    successful=batch_updated,
                    failed=batch_failed,
                    skipped=batch_skipped + (len(assets) - batch_matched),
                )
                await self._db.commit()

                total_matched += batch_matched
                total_updated += batch_updated
                total_skipped += batch_skipped
                total_failed += batch_failed

                offset += self._batch_size

                logger.debug(
                    "Processed batch",
                    task_id=str(task_id),
                    offset=offset,
                    batch_updated=batch_updated,
                )

            # Complete the task
            result = {
                "total_assets": total_assets,
                "matched": total_matched,
                "updated": total_updated,
                "skipped": total_skipped,
                "failed": total_failed,
                "sample_updates": sample_updates,
            }

            await self._executor.complete_task(task_id, result)
            await self._db.commit()

            logger.info(
                "Classification task completed",
                task_id=str(task_id),
                total_assets=total_assets,
                matched=total_matched,
                updated=total_updated,
            )

            return result

        except Exception as e:
            logger.exception("Classification task failed", task_id=str(task_id))
            await self._executor.fail_task(
                task_id,
                str(e),
                {"exception_type": type(e).__name__},
            )
            await self._db.commit()
            raise

    async def _process_asset(
        self,
        asset: Asset,
        force: bool,
        rule_id: UUID | None,
    ) -> tuple[bool, bool, dict]:
        """Process a single asset.

        Args:
            asset: Asset to process.
            force: If True, overwrite existing values.
            rule_id: If specified, only apply this rule.

        Returns:
            Tuple of (matched, updated, changes).
        """
        ip_address = str(asset.ip_address)

        # Get classification for this IP
        class_result = await self._db.execute(
            text("SELECT * FROM get_ip_classification(CAST(:ip_addr AS inet))"),
            {"ip_addr": ip_address},
        )
        row = class_result.fetchone()

        if not row or row.rule_id is None:
            return False, False, {}

        # If rule_id specified, only process if this rule matches
        if rule_id and row.rule_id != rule_id:
            return False, False, {}

        # Determine what needs to be updated
        changes = {}

        # is_internal - apply from rules if specified
        if row.is_internal is not None:
            if force or asset.is_internal != row.is_internal:
                changes["is_internal"] = {"old": asset.is_internal, "new": row.is_internal}

        # environment - only update if force or currently empty
        if row.environment and (force or not asset.environment):
            if asset.environment != row.environment:
                changes["environment"] = {"old": asset.environment, "new": row.environment}

        # datacenter - only update if force or currently empty
        if row.datacenter and (force or not asset.datacenter):
            if asset.datacenter != row.datacenter:
                changes["datacenter"] = {"old": asset.datacenter, "new": row.datacenter}

        # location (maps to city field on asset)
        if row.location and (force or not asset.city):
            if asset.city != row.location:
                changes["city"] = {"old": asset.city, "new": row.location}

        # owner - only update if force or currently empty
        if row.default_owner and (force or not asset.owner):
            if asset.owner != row.default_owner:
                changes["owner"] = {"old": asset.owner, "new": row.default_owner}

        # team - only update if force or currently empty
        if row.default_team and (force or not asset.team):
            if asset.team != row.default_team:
                changes["team"] = {"old": asset.team, "new": row.default_team}

        if not changes:
            return True, False, {}

        # Apply changes
        if "is_internal" in changes:
            asset.is_internal = changes["is_internal"]["new"]
        if "environment" in changes:
            asset.environment = changes["environment"]["new"]
        if "datacenter" in changes:
            asset.datacenter = changes["datacenter"]["new"]
        if "city" in changes:
            asset.city = changes["city"]["new"]
        if "owner" in changes:
            asset.owner = changes["owner"]["new"]
        if "team" in changes:
            asset.team = changes["team"]["new"]

        return True, True, changes
