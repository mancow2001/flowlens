"""Change detection for dependency resolution.

Detects new, stale, and changed dependencies and assets,
generating change events and alerts.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.config import ResolutionSettings, get_settings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import CHANGES_DETECTED
from flowlens.models.asset import Asset
from flowlens.models.change import Alert, AlertSeverity, ChangeEvent, ChangeType
from flowlens.models.dependency import Dependency
from flowlens.notifications.base import Notification, NotificationManager, NotificationPriority
from flowlens.notifications.email import EmailChannel, EmailSettings, create_alert_notification
from flowlens.notifications.webhook import WebhookChannel, WebhookSettings
from flowlens.notifications.slack import SlackChannel, SlackSettings
from flowlens.notifications.teams import TeamsChannel, TeamsSettings
from flowlens.notifications.pagerduty import PagerDutyChannel, PagerDutySettings
from flowlens.resolution.alert_rule_evaluator import AlertRuleEvaluator
from flowlens.api.websocket.manager import (
    EventType,
    broadcast_alert_event,
    broadcast_change_event,
)

logger = get_logger(__name__)


class ChangeDetector:
    """Detects changes in the dependency graph.

    Monitors for:
    - New dependencies (first-time connections)
    - Stale dependencies (no traffic for threshold period)
    - Asset state changes (online/offline)
    - Traffic anomalies (spikes/drops)
    """

    def __init__(self, settings: ResolutionSettings | None = None) -> None:
        """Initialize change detector.

        Args:
            settings: Resolution settings.
        """
        app_settings = get_settings()
        if settings is None:
            settings = app_settings.resolution

        self._stale_threshold_hours = settings.stale_threshold_hours
        self._stale_dependency_cleanup_days = settings.stale_dependency_cleanup_days
        self._stale_asset_cleanup_days = settings.stale_asset_cleanup_days
        self._traffic_spike_threshold = 2.0  # 2x baseline
        self._traffic_drop_threshold = 0.5  # 50% of baseline

        # Initialize notification manager
        self._notification_manager: NotificationManager | None = None
        self._notification_settings = app_settings.notifications

        # Initialize alert rule evaluator
        self._rule_evaluator = AlertRuleEvaluator()

    def _get_notification_manager(self) -> NotificationManager:
        """Get or create notification manager singleton."""
        if self._notification_manager is None:
            self._notification_manager = NotificationManager()
            settings = self._notification_settings

            # Register email channel if enabled
            if settings.email.enabled:
                email_settings = EmailSettings(
                    host=settings.email.host,
                    port=settings.email.port,
                    username=settings.email.username,
                    password=settings.email.password.get_secret_value() if settings.email.password else None,
                    use_tls=settings.email.use_tls,
                    start_tls=settings.email.start_tls,
                    from_address=settings.email.from_address,
                    from_name=settings.email.from_name,
                    timeout=settings.email.timeout,
                    validate_certs=settings.email.validate_certs,
                )
                self._notification_manager.register_channel(EmailChannel(email_settings))

            # Register webhook channel if enabled
            if settings.webhook.enabled and settings.webhook.url:
                webhook_settings = WebhookSettings(
                    url=settings.webhook.url,
                    secret=settings.webhook.secret.get_secret_value() if settings.webhook.secret else None,
                    timeout=settings.webhook.timeout,
                    retry_count=settings.webhook.retry_count,
                    retry_delay=settings.webhook.retry_delay,
                    headers=settings.webhook.headers,
                )
                self._notification_manager.register_channel(WebhookChannel(webhook_settings))

            # Register Slack channel if enabled
            if settings.slack.enabled and settings.slack.webhook_url:
                slack_settings = SlackSettings(
                    webhook_url=settings.slack.webhook_url,
                    default_channel=settings.slack.default_channel,
                    username=settings.slack.username,
                    icon_emoji=settings.slack.icon_emoji,
                    timeout=settings.slack.timeout,
                    retry_count=settings.slack.retry_count,
                    retry_delay=settings.slack.retry_delay,
                )
                self._notification_manager.register_channel(SlackChannel(slack_settings))

            # Register Teams channel if enabled
            if settings.teams.enabled and settings.teams.webhook_url:
                teams_settings = TeamsSettings(
                    webhook_url=settings.teams.webhook_url,
                    timeout=settings.teams.timeout,
                    retry_count=settings.teams.retry_count,
                    retry_delay=settings.teams.retry_delay,
                )
                self._notification_manager.register_channel(TeamsChannel(teams_settings))

            # Register PagerDuty channel if enabled
            if settings.pagerduty.enabled and settings.pagerduty.routing_key:
                pagerduty_settings = PagerDutySettings(
                    routing_key=settings.pagerduty.routing_key,
                    service_name=settings.pagerduty.service_name,
                    timeout=settings.pagerduty.timeout,
                    retry_count=settings.pagerduty.retry_count,
                    retry_delay=settings.pagerduty.retry_delay,
                )
                self._notification_manager.register_channel(PagerDutyChannel(pagerduty_settings))

        return self._notification_manager

    async def _dispatch_notification(
        self,
        alert: Alert,
        event: ChangeEvent,
        override_channels: list[str] | None = None,
    ) -> list[str]:
        """Dispatch notification for an alert.

        Routes to appropriate channels based on severity or rule override.

        Args:
            alert: Alert to notify about.
            event: Source change event.
            override_channels: Optional list of channels from alert rule.

        Returns:
            List of channels that received the notification.
        """
        if not self._notification_settings.enabled:
            return []

        manager = self._get_notification_manager()
        settings = self._notification_settings

        # Determine channels - use override if provided, otherwise severity-based
        severity_str = alert.severity.value if hasattr(alert.severity, 'value') else str(alert.severity)

        if override_channels:
            channels = override_channels
        else:
            channels = []
            if severity_str == "critical":
                channels = settings.critical_channels
            elif severity_str == "error":
                channels = settings.high_channels
            elif severity_str == "warning":
                channels = settings.warning_channels
            elif severity_str == "info":
                channels = settings.info_channels

        # Filter to only registered channels
        available_channels = [c for c in channels if c in manager.channels]
        if not available_channels:
            return []

        # Create notification
        notification = create_alert_notification(
            alert_title=alert.title,
            alert_message=alert.message,
            severity=severity_str,
            alert_id=str(alert.id),
        )

        # Build recipients dict
        recipients: dict[str, list[str]] = {}

        if "email" in available_channels:
            email_recipients = settings.email.alert_recipients
            if email_recipients:
                recipients["email"] = email_recipients

        if "webhook" in available_channels:
            # Webhook uses a single URL, not multiple recipients
            recipients["webhook"] = ["default"]

        if "slack" in available_channels:
            # Slack uses webhook URL configured in settings
            recipients["slack"] = ["default"]

        if "teams" in available_channels:
            # Teams uses webhook URL configured in settings
            recipients["teams"] = ["default"]

        if "pagerduty" in available_channels:
            # PagerDuty uses routing key configured in settings
            recipients["pagerduty"] = ["default"]

        if not recipients:
            return []

        # Send notifications
        try:
            results = await manager.send(notification, recipients)

            # Track successful channels
            sent_channels = []
            for channel_name, channel_results in results.items():
                if any(r.success for r in channel_results):
                    sent_channels.append(channel_name)

            logger.info(
                "Alert notification dispatched",
                alert_id=str(alert.id),
                severity=severity_str,
                channels=sent_channels,
            )

            return sent_channels

        except Exception as e:
            logger.error(
                "Failed to dispatch alert notification",
                alert_id=str(alert.id),
                error=str(e),
            )
            return []

    async def detect_stale_dependencies(
        self,
        db: AsyncSession,
        threshold_hours: int | None = None,
    ) -> list[UUID]:
        """Detect dependencies with no recent traffic.

        Args:
            db: Database session.
            threshold_hours: Hours since last activity to consider stale.

        Returns:
            List of stale dependency IDs.
        """
        if threshold_hours is None:
            threshold_hours = self._stale_threshold_hours

        cutoff = datetime.utcnow() - timedelta(hours=threshold_hours)

        result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.last_seen < cutoff,
                Dependency.valid_to.is_(None),
                Dependency.is_ignored == False,
            )
            .limit(1000)
        )

        stale_ids = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected stale dependencies",
            count=len(stale_ids),
            threshold_hours=threshold_hours,
        )

        return stale_ids

    async def detect_offline_assets(
        self,
        db: AsyncSession,
        threshold_hours: int = 24,
    ) -> list[UUID]:
        """Detect assets with no recent activity.

        Args:
            db: Database session.
            threshold_hours: Hours since last activity.

        Returns:
            List of offline asset IDs.
        """
        cutoff = datetime.utcnow() - timedelta(hours=threshold_hours)

        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.last_seen < cutoff,
                Asset.deleted_at.is_(None),
            )
            .limit(1000)
        )

        offline_ids = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected offline assets",
            count=len(offline_ids),
            threshold_hours=threshold_hours,
        )

        return offline_ids

    async def create_change_event(
        self,
        db: AsyncSession,
        change_type: ChangeType,
        summary: str,
        description: str | None = None,
        asset_id: UUID | None = None,
        dependency_id: UUID | None = None,
        source_asset_id: UUID | None = None,
        target_asset_id: UUID | None = None,
        previous_state: dict | None = None,
        new_state: dict | None = None,
        impact_score: int = 0,
        affected_assets_count: int = 0,
        occurred_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> ChangeEvent:
        """Create a change event record.

        Args:
            db: Database session.
            change_type: Type of change.
            summary: Brief summary of the change.
            description: Detailed description.
            asset_id: Related asset ID.
            dependency_id: Related dependency ID.
            source_asset_id: Source asset for dependency changes.
            target_asset_id: Target asset for dependency changes.
            previous_state: State before change.
            new_state: State after change.
            impact_score: Impact severity (0-100).
            affected_assets_count: Number of affected assets.
            occurred_at: When the change occurred.
            metadata: Additional metadata.

        Returns:
            Created change event.
        """
        event = ChangeEvent(
            change_type=change_type,
            summary=summary,
            description=description,
            asset_id=asset_id,
            dependency_id=dependency_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            previous_state=previous_state,
            new_state=new_state,
            impact_score=impact_score,
            affected_assets_count=affected_assets_count,
            occurred_at=occurred_at,
            metadata=metadata or {},
        )

        db.add(event)
        await db.flush()

        CHANGES_DETECTED.labels(change_type=change_type.value).inc()

        logger.info(
            "Created change event",
            event_id=str(event.id),
            change_type=change_type.value,
            summary=summary,
        )

        # Broadcast via WebSocket
        try:
            await broadcast_change_event(
                EventType.CHANGE_DETECTED,
                event.id,
                {
                    "change_type": change_type.value,
                    "summary": summary,
                    "impact_score": impact_score,
                    "asset_id": str(asset_id) if asset_id else None,
                    "dependency_id": str(dependency_id) if dependency_id else None,
                },
            )
        except Exception as e:
            # Don't fail the event creation if broadcast fails
            logger.warning("Failed to broadcast change event", error=str(e))

        return event

    async def create_alert_from_event(
        self,
        db: AsyncSession,
        event: ChangeEvent,
        severity: AlertSeverity | None = None,
        title: str | None = None,
        message: str | None = None,
        send_notification: bool = True,
    ) -> Alert | None:
        """Create an alert from a change event.

        Evaluates alert rules to determine if an alert should be created,
        and uses rule configuration for severity, title, and notification channels.

        Args:
            db: Database session.
            event: Source change event.
            severity: Alert severity (uses rule or auto-determined if not provided).
            title: Alert title (uses rule template or derived from event).
            message: Alert message (uses rule template or derived from event).
            send_notification: Whether to send notification (default: True).

        Returns:
            Created alert, or None if suppressed by maintenance window.
        """
        # Evaluate alert rules
        rule_result = await self._rule_evaluator.evaluate(db, event)

        # Check if suppressed by maintenance window
        if not rule_result.should_create_alert:
            logger.info(
                "Alert suppressed",
                event_id=str(event.id),
                reason=rule_result.suppression_reason,
            )
            return None

        # Use rule-provided values, or fall back to defaults
        if rule_result.matching_rule:
            # Rule matched - use rule configuration
            if severity is None:
                severity = rule_result.severity
            if title is None:
                title = rule_result.rendered_title
            if message is None:
                message = rule_result.rendered_description
            notify_channels = rule_result.notify_channels
        else:
            # No rule matched - use default behavior
            notify_channels = None

        # Fall back to auto-determined values if still None
        if severity is None:
            severity = self._determine_severity(event)

        if title is None:
            title = self._generate_alert_title(event)

        if message is None:
            message = self._generate_alert_message(event)

        alert = Alert(
            change_event_id=event.id,
            severity=severity,
            title=title,
            message=message,
            asset_id=event.asset_id,
            dependency_id=event.dependency_id,
        )

        db.add(alert)
        await db.flush()

        severity_str = severity.value if hasattr(severity, 'value') else str(severity)
        logger.info(
            "Created alert",
            alert_id=str(alert.id),
            severity=severity_str,
            title=title,
            rule=rule_result.matching_rule.name if rule_result.matching_rule else None,
        )

        # Dispatch notification
        if send_notification:
            sent_channels = await self._dispatch_notification(
                alert, event, override_channels=notify_channels
            )
            if sent_channels:
                alert.notification_sent = True
                alert.notification_channels = sent_channels
                await db.flush()

        # Broadcast via WebSocket
        try:
            change_type_str = event.change_type.value if hasattr(event.change_type, 'value') else str(event.change_type)
            await broadcast_alert_event(
                EventType.ALERT_CREATED,
                alert.id,
                {
                    "severity": severity_str,
                    "title": title,
                    "message": message[:200] if message else None,  # Truncate for broadcast
                    "change_type": change_type_str,
                    "asset_id": str(alert.asset_id) if alert.asset_id else None,
                    "dependency_id": str(alert.dependency_id) if alert.dependency_id else None,
                },
            )
        except Exception as e:
            # Don't fail the alert creation if broadcast fails
            logger.warning("Failed to broadcast alert event", error=str(e))

        return alert

    def _determine_severity(self, event: ChangeEvent) -> AlertSeverity:
        """Determine alert severity from change event.

        Args:
            event: Change event.

        Returns:
            Appropriate severity level.
        """
        # Critical events
        if event.change_type in (
            ChangeType.CRITICAL_PATH_CHANGE,
            ChangeType.ASSET_OFFLINE,
        ):
            return AlertSeverity.CRITICAL

        # Error-level events
        if event.change_type in (
            ChangeType.DEPENDENCY_REMOVED,
            ChangeType.ASSET_REMOVED,
            ChangeType.DEPENDENCY_TRAFFIC_DROP,
        ):
            return AlertSeverity.ERROR

        # Warning-level events
        if event.change_type in (
            ChangeType.DEPENDENCY_STALE,
            ChangeType.DEPENDENCY_TRAFFIC_SPIKE,
            ChangeType.NEW_EXTERNAL_CONNECTION,
        ):
            return AlertSeverity.WARNING

        # Info-level for new discoveries
        if event.change_type in (
            ChangeType.DEPENDENCY_CREATED,
            ChangeType.ASSET_DISCOVERED,
            ChangeType.SERVICE_DISCOVERED,
            ChangeType.ASSET_ONLINE,
        ):
            return AlertSeverity.INFO

        # Default based on impact score
        if event.impact_score >= 70:
            return AlertSeverity.CRITICAL
        elif event.impact_score >= 50:
            return AlertSeverity.ERROR
        elif event.impact_score >= 30:
            return AlertSeverity.WARNING
        else:
            return AlertSeverity.INFO

    def _generate_alert_title(self, event: ChangeEvent) -> str:
        """Generate alert title from change event.

        Args:
            event: Change event.

        Returns:
            Alert title.
        """
        type_titles = {
            ChangeType.DEPENDENCY_CREATED: "New Dependency Discovered",
            ChangeType.DEPENDENCY_REMOVED: "Dependency Removed",
            ChangeType.DEPENDENCY_STALE: "Stale Dependency Detected",
            ChangeType.DEPENDENCY_TRAFFIC_SPIKE: "Traffic Spike Detected",
            ChangeType.DEPENDENCY_TRAFFIC_DROP: "Traffic Drop Detected",
            ChangeType.ASSET_DISCOVERED: "New Asset Discovered",
            ChangeType.ASSET_REMOVED: "Asset Removed",
            ChangeType.ASSET_OFFLINE: "Asset Offline",
            ChangeType.ASSET_ONLINE: "Asset Back Online",
            ChangeType.SERVICE_DISCOVERED: "New Service Discovered",
            ChangeType.SERVICE_REMOVED: "Service Removed",
            ChangeType.NEW_EXTERNAL_CONNECTION: "New External Connection",
            ChangeType.CRITICAL_PATH_CHANGE: "Critical Path Changed",
        }

        return type_titles.get(event.change_type, "Topology Change Detected")

    def _generate_alert_message(self, event: ChangeEvent) -> str:
        """Generate alert message from change event.

        Args:
            event: Change event.

        Returns:
            Alert message.
        """
        message = event.summary

        if event.description:
            message += f"\n\n{event.description}"

        if event.affected_assets_count > 0:
            message += f"\n\nAffected assets: {event.affected_assets_count}"

        if event.previous_state or event.new_state:
            message += "\n\nChange details:"
            if event.previous_state:
                message += f"\n- Previous: {event.previous_state}"
            if event.new_state:
                message += f"\n- New: {event.new_state}"

        return message

    async def process_stale_dependencies(
        self,
        db: AsyncSession,
        stale_dep_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process stale dependencies - create events and optionally alerts.

        Args:
            db: Database session.
            stale_dep_ids: List of stale dependency IDs.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for dep_id in stale_dep_ids:
            # Get dependency details
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()

            if not dep:
                continue

            # Create change event
            event = await self.create_change_event(
                db,
                change_type=ChangeType.DEPENDENCY_STALE,
                summary=f"No traffic on dependency for {self._stale_threshold_hours}+ hours",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                previous_state={
                    "last_seen": dep.last_seen.isoformat(),
                    "bytes_total": dep.bytes_total,
                    "flows_total": dep.flows_total,
                },
                metadata={
                    "port": dep.target_port,
                    "protocol": dep.protocol,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)

            count += 1

        return count

    async def check_new_external_connections(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> list[UUID]:
        """Check for new connections to external assets.

        Args:
            db: Database session.
            since: Check for connections created after this time.

        Returns:
            List of dependency IDs for new external connections.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        # Find new dependencies where target is external
        result = await db.execute(
            select(Dependency.id)
            .join(Asset, Dependency.target_asset_id == Asset.id)
            .where(
                Dependency.first_seen >= since,
                Dependency.valid_to.is_(None),
                Asset.is_internal == False,
            )
        )

        new_external = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected new external connections",
            count=len(new_external),
            since=since.isoformat(),
        )

        return new_external

    async def detect_traffic_anomalies(
        self,
        db: AsyncSession,
    ) -> dict[str, list[UUID]]:
        """Detect traffic anomalies (spikes and drops).

        Compares 24h traffic to 7d average to find anomalies.

        Args:
            db: Database session.

        Returns:
            Dict with 'spikes' and 'drops' lists of dependency IDs.
        """
        # Find dependencies with traffic spikes (>2x baseline)
        spike_result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.valid_to.is_(None),
                Dependency.bytes_last_7d > 0,
                # 24h traffic * 7 > 7d traffic * spike_threshold (comparing daily average)
                (Dependency.bytes_last_24h * 7) > (Dependency.bytes_last_7d * self._traffic_spike_threshold),
            )
            .limit(100)
        )
        spikes = [row[0] for row in spike_result.fetchall()]

        # Find dependencies with traffic drops (<50% of baseline)
        drop_result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.valid_to.is_(None),
                Dependency.bytes_last_7d > 1000000,  # At least 1MB over 7d to be significant
                # 24h traffic * 7 < 7d traffic * drop_threshold (comparing daily average)
                (Dependency.bytes_last_24h * 7) < (Dependency.bytes_last_7d * self._traffic_drop_threshold),
            )
            .limit(100)
        )
        drops = [row[0] for row in drop_result.fetchall()]

        logger.info(
            "Detected traffic anomalies",
            spikes=len(spikes),
            drops=len(drops),
        )

        return {"spikes": spikes, "drops": drops}

    async def process_traffic_anomalies(
        self,
        db: AsyncSession,
        anomalies: dict[str, list[UUID]],
        create_alerts: bool = True,
    ) -> int:
        """Process traffic anomalies - create events and optionally alerts.

        Args:
            db: Database session.
            anomalies: Dict with 'spikes' and 'drops' lists.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        # Process spikes
        for dep_id in anomalies.get("spikes", []):
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()
            if not dep:
                continue

            daily_avg = dep.bytes_last_7d / 7 if dep.bytes_last_7d > 0 else 0
            spike_ratio = dep.bytes_last_24h / daily_avg if daily_avg > 0 else 0

            event = await self.create_change_event(
                db,
                change_type=ChangeType.DEPENDENCY_TRAFFIC_SPIKE,
                summary=f"Traffic spike detected: {spike_ratio:.1f}x normal",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                previous_state={
                    "bytes_7d_avg_daily": int(daily_avg),
                },
                new_state={
                    "bytes_last_24h": dep.bytes_last_24h,
                    "spike_ratio": round(spike_ratio, 2),
                },
                impact_score=min(50 + int(spike_ratio * 10), 100),
                metadata={
                    "port": dep.target_port,
                    "protocol": dep.protocol,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        # Process drops
        for dep_id in anomalies.get("drops", []):
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()
            if not dep:
                continue

            daily_avg = dep.bytes_last_7d / 7 if dep.bytes_last_7d > 0 else 0
            drop_ratio = dep.bytes_last_24h / daily_avg if daily_avg > 0 else 0

            event = await self.create_change_event(
                db,
                change_type=ChangeType.DEPENDENCY_TRAFFIC_DROP,
                summary=f"Traffic drop detected: {drop_ratio:.0%} of normal",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                previous_state={
                    "bytes_7d_avg_daily": int(daily_avg),
                },
                new_state={
                    "bytes_last_24h": dep.bytes_last_24h,
                    "drop_ratio": round(drop_ratio, 2),
                },
                impact_score=min(60 + int((1 - drop_ratio) * 40), 100),
                metadata={
                    "port": dep.target_port,
                    "protocol": dep.protocol,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        return count

    async def detect_new_assets(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> list[UUID]:
        """Detect newly discovered assets.

        Args:
            db: Database session.
            since: Check for assets created after this time.

        Returns:
            List of new asset IDs.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.first_seen >= since,
                Asset.deleted_at.is_(None),
            )
            .limit(100)
        )

        new_assets = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected new assets",
            count=len(new_assets),
            since=since.isoformat(),
        )

        return new_assets

    async def process_new_assets(
        self,
        db: AsyncSession,
        asset_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process new assets - create events and optionally alerts.

        Args:
            db: Database session.
            asset_ids: List of new asset IDs.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for asset_id in asset_ids:
            result = await db.execute(
                select(Asset).where(Asset.id == asset_id)
            )
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            event = await self.create_change_event(
                db,
                change_type=ChangeType.ASSET_DISCOVERED,
                summary=f"New asset discovered: {asset.name}",
                asset_id=asset_id,
                new_state={
                    "name": asset.name,
                    "ip_address": str(asset.ip_address),
                    "asset_type": asset.asset_type.value if hasattr(asset.asset_type, 'value') else asset.asset_type,
                    "is_internal": asset.is_internal,
                },
                metadata={
                    "hostname": asset.hostname,
                    "environment": asset.environment,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        return count

    async def detect_new_dependencies(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> list[UUID]:
        """Detect newly created dependencies.

        Args:
            db: Database session.
            since: Check for dependencies created after this time.

        Returns:
            List of new dependency IDs.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.first_seen >= since,
                Dependency.valid_to.is_(None),
            )
            .limit(100)
        )

        new_deps = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected new dependencies",
            count=len(new_deps),
            since=since.isoformat(),
        )

        return new_deps

    async def process_new_dependencies(
        self,
        db: AsyncSession,
        dep_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process new dependencies - create events and optionally alerts.

        Args:
            db: Database session.
            dep_ids: List of new dependency IDs.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for dep_id in dep_ids:
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()
            if not dep:
                continue

            # Get asset names
            source_name = "Unknown"
            target_name = "Unknown"

            source_result = await db.execute(
                select(Asset.name).where(Asset.id == dep.source_asset_id)
            )
            source_row = source_result.first()
            if source_row:
                source_name = source_row[0]

            target_result = await db.execute(
                select(Asset.name).where(Asset.id == dep.target_asset_id)
            )
            target_row = target_result.first()
            if target_row:
                target_name = target_row[0]

            event = await self.create_change_event(
                db,
                change_type=ChangeType.DEPENDENCY_CREATED,
                summary=f"New dependency: {source_name} → {target_name}:{dep.target_port}",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                new_state={
                    "target_port": dep.target_port,
                    "protocol": dep.protocol,
                },
                metadata={
                    "source_name": source_name,
                    "target_name": target_name,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        return count

    async def process_offline_assets(
        self,
        db: AsyncSession,
        asset_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process offline assets - create events and optionally alerts.

        Args:
            db: Database session.
            asset_ids: List of offline asset IDs.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for asset_id in asset_ids:
            result = await db.execute(
                select(Asset).where(Asset.id == asset_id)
            )
            asset = result.scalar_one_or_none()
            if not asset:
                continue

            # Handle both timezone-aware and naive datetimes
            now = datetime.now(timezone.utc)
            last_seen = asset.last_seen
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            hours_offline = (now - last_seen).total_seconds() / 3600

            event = await self.create_change_event(
                db,
                change_type=ChangeType.ASSET_OFFLINE,
                summary=f"Asset offline: {asset.name} (no activity for {hours_offline:.0f}h)",
                asset_id=asset_id,
                previous_state={
                    "last_seen": asset.last_seen.isoformat(),
                },
                impact_score=80 if asset.is_critical else 40,
                affected_assets_count=asset.connections_in + asset.connections_out,
                metadata={
                    "hours_offline": round(hours_offline, 1),
                    "is_critical": asset.is_critical,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        return count

    async def process_new_external_connections(
        self,
        db: AsyncSession,
        dep_ids: list[UUID],
        create_alerts: bool = True,
    ) -> int:
        """Process new external connections - create events and optionally alerts.

        Args:
            db: Database session.
            dep_ids: List of dependency IDs with external targets.
            create_alerts: Whether to create alerts.

        Returns:
            Number of events created.
        """
        count = 0

        for dep_id in dep_ids:
            result = await db.execute(
                select(Dependency).where(Dependency.id == dep_id)
            )
            dep = result.scalar_one_or_none()
            if not dep:
                continue

            # Get asset info
            source_result = await db.execute(
                select(Asset).where(Asset.id == dep.source_asset_id)
            )
            source = source_result.scalar_one_or_none()

            target_result = await db.execute(
                select(Asset).where(Asset.id == dep.target_asset_id)
            )
            target = target_result.scalar_one_or_none()

            source_name = source.name if source else "Unknown"
            target_name = target.name if target else "Unknown"
            target_ip = str(target.ip_address) if target else "Unknown"

            event = await self.create_change_event(
                db,
                change_type=ChangeType.NEW_EXTERNAL_CONNECTION,
                summary=f"New external connection: {source_name} → {target_name} ({target_ip})",
                dependency_id=dep_id,
                source_asset_id=dep.source_asset_id,
                target_asset_id=dep.target_asset_id,
                new_state={
                    "target_port": dep.target_port,
                    "protocol": dep.protocol,
                    "target_ip": target_ip,
                },
                impact_score=50,  # External connections are moderately concerning
                metadata={
                    "source_name": source_name,
                    "target_name": target_name,
                },
            )

            if create_alerts:
                await self.create_alert_from_event(db, event)
            count += 1

        return count

    async def detect_critical_path_changes(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> list[UUID]:
        """Detect changes affecting critical assets.

        Args:
            db: Database session.
            since: Check for changes after this time.

        Returns:
            List of dependency IDs affecting critical paths.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        # Find dependencies to/from critical assets that changed recently
        result = await db.execute(
            select(Dependency.id)
            .join(Asset, (Dependency.source_asset_id == Asset.id) | (Dependency.target_asset_id == Asset.id))
            .where(
                Asset.is_critical == True,
                Dependency.updated_at >= since,
                Dependency.valid_to.is_(None),
            )
            .distinct()
            .limit(50)
        )

        critical_deps = [row[0] for row in result.fetchall()]

        logger.info(
            "Detected critical path changes",
            count=len(critical_deps),
            since=since.isoformat(),
        )

        return critical_deps

    async def cleanup_stale_dependencies(
        self,
        db: AsyncSession,
        threshold_days: int | None = None,
    ) -> int:
        """Close dependencies that have been stale for too long.

        Sets valid_to to mark dependencies as closed/ended.

        Args:
            db: Database session.
            threshold_days: Days since last activity to trigger cleanup.

        Returns:
            Number of dependencies closed.
        """
        if threshold_days is None:
            threshold_days = self._stale_dependency_cleanup_days

        cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)

        # Find dependencies to close
        result = await db.execute(
            select(Dependency.id)
            .where(
                Dependency.last_seen < cutoff,
                Dependency.valid_to.is_(None),
            )
            .limit(500)
        )
        stale_ids = [row[0] for row in result.fetchall()]

        if not stale_ids:
            return 0

        # Close the dependencies by setting valid_to
        now = datetime.now(timezone.utc)
        await db.execute(
            update(Dependency)
            .where(Dependency.id.in_(stale_ids))
            .values(valid_to=now)
        )

        logger.info(
            "Cleaned up stale dependencies",
            count=len(stale_ids),
            threshold_days=threshold_days,
        )

        return len(stale_ids)

    async def cleanup_stale_assets(
        self,
        db: AsyncSession,
        threshold_days: int | None = None,
    ) -> int:
        """Soft-delete assets that have been inactive for too long.

        Sets deleted_at to mark assets as removed.

        Args:
            db: Database session.
            threshold_days: Days since last activity to trigger cleanup.

        Returns:
            Number of assets soft-deleted.
        """
        if threshold_days is None:
            threshold_days = self._stale_asset_cleanup_days

        cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_days)

        # Find assets to soft-delete
        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.last_seen < cutoff,
                Asset.deleted_at.is_(None),
            )
            .limit(500)
        )
        stale_ids = [row[0] for row in result.fetchall()]

        if not stale_ids:
            return 0

        # Soft-delete the assets
        now = datetime.now(timezone.utc)
        await db.execute(
            update(Asset)
            .where(Asset.id.in_(stale_ids))
            .values(deleted_at=now)
        )

        logger.info(
            "Cleaned up stale assets",
            count=len(stale_ids),
            threshold_days=threshold_days,
        )

        return len(stale_ids)

    async def run_detection_cycle(
        self,
        db: AsyncSession,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Run a full detection cycle.

        Checks for:
        - Stale dependencies
        - Offline assets
        - New external connections
        - Traffic anomalies (spikes/drops)
        - New assets
        - New dependencies

        Args:
            db: Database session.
            since: Check for changes since this time (default: 1 hour ago).

        Returns:
            Summary of detected changes.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(hours=1)

        results = {
            "stale_dependencies": 0,
            "offline_assets": 0,
            "new_external_connections": 0,
            "traffic_spikes": 0,
            "traffic_drops": 0,
            "new_assets": 0,
            "new_dependencies": 0,
            "events_created": 0,
            "alerts_created": 0,
            "dependencies_cleaned_up": 0,
            "assets_cleaned_up": 0,
        }

        # Detect stale dependencies
        stale_deps = await self.detect_stale_dependencies(db)
        results["stale_dependencies"] = len(stale_deps)

        if stale_deps:
            events_created = await self.process_stale_dependencies(
                db, stale_deps[:100]  # Limit batch size
            )
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect offline assets
        offline_assets = await self.detect_offline_assets(db)
        results["offline_assets"] = len(offline_assets)

        if offline_assets:
            events_created = await self.process_offline_assets(
                db, offline_assets[:50]
            )
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect new external connections
        new_external = await self.check_new_external_connections(db, since)
        results["new_external_connections"] = len(new_external)

        if new_external:
            events_created = await self.process_new_external_connections(
                db, new_external[:50]
            )
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect traffic anomalies
        anomalies = await self.detect_traffic_anomalies(db)
        results["traffic_spikes"] = len(anomalies.get("spikes", []))
        results["traffic_drops"] = len(anomalies.get("drops", []))

        if anomalies.get("spikes") or anomalies.get("drops"):
            events_created = await self.process_traffic_anomalies(db, anomalies)
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect new assets
        new_assets = await self.detect_new_assets(db, since)
        results["new_assets"] = len(new_assets)

        if new_assets:
            events_created = await self.process_new_assets(db, new_assets[:50])
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Detect new dependencies
        new_deps = await self.detect_new_dependencies(db, since)
        results["new_dependencies"] = len(new_deps)

        if new_deps:
            events_created = await self.process_new_dependencies(db, new_deps[:100])
            results["events_created"] += events_created
            results["alerts_created"] += events_created

        # Cleanup stale dependencies and assets (after configured threshold)
        results["dependencies_cleaned_up"] = await self.cleanup_stale_dependencies(db)
        results["assets_cleaned_up"] = await self.cleanup_stale_assets(db)

        await db.commit()

        logger.info(
            "Detection cycle complete",
            **results,
        )

        return results
