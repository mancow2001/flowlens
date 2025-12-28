"""Unit tests for alert rule evaluation service."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from flowlens.models.alert_rule import AlertRule
from flowlens.models.asset import Asset, AssetType
from flowlens.models.change import AlertSeverity, ChangeEvent, ChangeType
from flowlens.models.maintenance_window import MaintenanceWindow
from flowlens.resolution.alert_rule_evaluator import (
    AlertRuleEvaluator,
    AlertContext,
    RuleEvaluationResult,
)


def utcnow():
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@pytest.mark.unit
class TestAlertContext:
    """Test cases for AlertContext."""

    def test_context_to_dict(self):
        """Test context serialization to dict."""
        context = AlertContext(
            change_type="asset_discovered",
            summary="New asset found",
            description="Description text",
            asset_name="web-server-01",
            asset_ip="10.0.0.1",
            asset_type="server",
            environment="production",
            datacenter="dc1",
            impact_score=50,
            affected_assets_count=5,
        )

        result = context.to_dict()

        assert result["change_type"] == "Asset Discovered"  # Title cased
        assert result["summary"] == "New asset found"
        assert result["asset_name"] == "web-server-01"
        assert result["asset_ip"] == "10.0.0.1"
        assert result["environment"] == "production"
        assert result["impact_score"] == 50
        assert result["affected_assets_count"] == 5

    def test_context_to_dict_with_none_values(self):
        """Test context serialization handles None values."""
        context = AlertContext(
            change_type="asset_discovered",
            summary="Summary",
            description=None,
            asset_name=None,
            asset_ip=None,
            asset_type=None,
            environment=None,
            datacenter=None,
            impact_score=0,
            affected_assets_count=0,
        )

        result = context.to_dict()

        assert result["description"] == ""
        assert result["asset_name"] == "Unknown"
        assert result["asset_ip"] == "Unknown"
        assert result["asset_type"] == "Unknown"
        assert result["environment"] == "Unknown"
        assert result["datacenter"] == "Unknown"


@pytest.mark.unit
class TestRuleEvaluationResult:
    """Test cases for RuleEvaluationResult."""

    def test_result_should_create_alert_true(self):
        """Test result with should_create_alert=True."""
        result = RuleEvaluationResult(
            should_create_alert=True,
            matching_rule=None,
        )

        assert result.should_create_alert is True
        assert result.matching_rule is None
        assert result.suppression_reason is None

    def test_result_suppressed(self):
        """Test result with suppression."""
        result = RuleEvaluationResult(
            should_create_alert=False,
            suppression_reason="Maintenance window: Weekly maintenance",
        )

        assert result.should_create_alert is False
        assert result.suppression_reason == "Maintenance window: Weekly maintenance"

    def test_result_with_matching_rule(self):
        """Test result with matching rule."""
        mock_rule = MagicMock(spec=AlertRule)
        mock_rule.name = "Critical Alerts"

        result = RuleEvaluationResult(
            should_create_alert=True,
            matching_rule=mock_rule,
            rendered_title="Critical Change Detected",
            rendered_description="A critical change was detected",
            severity=AlertSeverity.CRITICAL,
            notify_channels=["email", "slack"],
        )

        assert result.should_create_alert is True
        assert result.matching_rule.name == "Critical Alerts"
        assert result.rendered_title == "Critical Change Detected"
        assert result.notify_channels == ["email", "slack"]


@pytest.mark.unit
class TestAlertRuleEvaluator:
    """Test cases for AlertRuleEvaluator."""

    @pytest.fixture
    def evaluator(self) -> AlertRuleEvaluator:
        """Create evaluator instance."""
        return AlertRuleEvaluator()

    @pytest.fixture
    def mock_event(self) -> MagicMock:
        """Create mock change event."""
        event = MagicMock(spec=ChangeEvent)
        event.id = uuid4()
        event.change_type = ChangeType.ASSET_DISCOVERED
        event.summary = "New asset discovered: web-server-01"
        event.description = "Asset was discovered via flow analysis"
        event.asset_id = uuid4()
        event.dependency_id = None
        event.impact_score = 30
        event.affected_assets_count = 0
        return event

    @pytest.fixture
    def mock_asset(self) -> MagicMock:
        """Create mock asset."""
        asset = MagicMock(spec=Asset)
        asset.id = uuid4()
        asset.name = "web-server-01"
        asset.ip_address = "10.0.0.1"
        asset.asset_type = AssetType.SERVER
        asset.environment = "production"
        asset.datacenter = "dc1"
        asset.is_critical = True
        asset.is_internal = True
        asset.owner = "platform-team"
        asset.team = "platform"
        return asset

    def test_build_asset_data(self, evaluator: AlertRuleEvaluator, mock_asset: MagicMock):
        """Test asset data extraction for filter matching."""
        result = evaluator._build_asset_data(mock_asset)

        assert result["environment"] == "production"
        assert result["datacenter"] == "dc1"
        assert result["is_critical"] is True
        assert result["is_internal"] is True
        assert result["owner"] == "platform-team"
        assert result["team"] == "platform"

    def test_build_context(
        self,
        evaluator: AlertRuleEvaluator,
        mock_event: MagicMock,
        mock_asset: MagicMock,
    ):
        """Test context building for template rendering."""
        context = evaluator._build_context(mock_event, mock_asset)

        assert context.change_type == "asset_discovered"
        assert context.summary == "New asset discovered: web-server-01"
        assert context.asset_name == "web-server-01"
        assert context.environment == "production"
        assert context.impact_score == 30

    def test_build_context_without_asset(
        self,
        evaluator: AlertRuleEvaluator,
        mock_event: MagicMock,
    ):
        """Test context building when asset is None."""
        context = evaluator._build_context(mock_event, None)

        assert context.change_type == "asset_discovered"
        assert context.asset_name is None
        assert context.asset_ip is None
        assert context.environment is None

    def test_is_rule_scheduled_no_schedule(self, evaluator: AlertRuleEvaluator):
        """Test rule with no schedule is always active."""
        rule = MagicMock(spec=AlertRule)
        rule.schedule = None

        result = evaluator._is_rule_scheduled(rule)

        assert result is True

    def test_is_rule_scheduled_empty_schedule(self, evaluator: AlertRuleEvaluator):
        """Test rule with empty schedule is always active."""
        rule = MagicMock(spec=AlertRule)
        rule.schedule = {}

        result = evaluator._is_rule_scheduled(rule)

        assert result is True

    def test_is_rule_scheduled_matching_day(self, evaluator: AlertRuleEvaluator):
        """Test rule schedule matching current day."""
        rule = MagicMock(spec=AlertRule)
        # Schedule for all weekdays
        rule.schedule = {"days": ["mon", "tue", "wed", "thu", "fri"]}

        with patch("flowlens.resolution.alert_rule_evaluator.datetime") as mock_dt:
            # Mock a Wednesday
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2  # Wednesday
            mock_now.hour = 12
            mock_dt.now.return_value = mock_now

            result = evaluator._is_rule_scheduled(rule)

            assert result is True

    def test_is_rule_scheduled_non_matching_day(self, evaluator: AlertRuleEvaluator):
        """Test rule schedule not matching current day."""
        rule = MagicMock(spec=AlertRule)
        # Schedule only for weekdays
        rule.schedule = {"days": ["mon", "tue", "wed", "thu", "fri"]}

        with patch("flowlens.resolution.alert_rule_evaluator.datetime") as mock_dt:
            # Mock a Saturday
            mock_now = MagicMock()
            mock_now.weekday.return_value = 5  # Saturday
            mock_now.hour = 12
            mock_dt.now.return_value = mock_now

            result = evaluator._is_rule_scheduled(rule)

            assert result is False

    def test_is_rule_scheduled_matching_hours(self, evaluator: AlertRuleEvaluator):
        """Test rule schedule matching current hour."""
        rule = MagicMock(spec=AlertRule)
        # Business hours only
        rule.schedule = {"hours": {"start": 9, "end": 17}}

        with patch("flowlens.resolution.alert_rule_evaluator.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2
            mock_now.hour = 12  # Noon - within business hours
            mock_dt.now.return_value = mock_now

            result = evaluator._is_rule_scheduled(rule)

            assert result is True

    def test_is_rule_scheduled_non_matching_hours(self, evaluator: AlertRuleEvaluator):
        """Test rule schedule not matching current hour."""
        rule = MagicMock(spec=AlertRule)
        # Business hours only
        rule.schedule = {"hours": {"start": 9, "end": 17}}

        with patch("flowlens.resolution.alert_rule_evaluator.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.weekday.return_value = 2
            mock_now.hour = 20  # 8 PM - outside business hours
            mock_dt.now.return_value = mock_now

            result = evaluator._is_rule_scheduled(rule)

            assert result is False


@pytest.mark.unit
class TestAlertRuleMatching:
    """Test cases for alert rule matching logic."""

    def test_matches_change_type(self):
        """Test change type matching."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered", "asset_removed"],
            severity=AlertSeverity.WARNING,
        )

        assert rule.matches_change_type("asset_discovered") is True
        assert rule.matches_change_type("asset_removed") is True
        assert rule.matches_change_type("dependency_created") is False

    def test_matches_asset_filter_no_filter(self):
        """Test asset filter with no filter set."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            asset_filter=None,
        )

        # Should match any asset
        assert rule.matches_asset_filter({}) is True
        assert rule.matches_asset_filter({"environment": "production"}) is True

    def test_matches_asset_filter_environment(self):
        """Test asset filter matching environment."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            asset_filter={"environment": "production"},
        )

        assert rule.matches_asset_filter({"environment": "production"}) is True
        assert rule.matches_asset_filter({"environment": "staging"}) is False

    def test_matches_asset_filter_multiple_criteria(self):
        """Test asset filter with multiple criteria."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            asset_filter={
                "environment": "production",
                "is_critical": True,
            },
        )

        # Both must match
        assert rule.matches_asset_filter({
            "environment": "production",
            "is_critical": True,
        }) is True

        # Only one matches
        assert rule.matches_asset_filter({
            "environment": "production",
            "is_critical": False,
        }) is False

        # Neither matches
        assert rule.matches_asset_filter({
            "environment": "staging",
            "is_critical": False,
        }) is False

    def test_is_on_cooldown_not_triggered(self):
        """Test cooldown check when never triggered."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
            last_triggered_at=None,
        )

        assert rule.is_on_cooldown() is False

    def test_is_on_cooldown_expired(self):
        """Test cooldown check when cooldown has expired."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
            last_triggered_at=utcnow() - timedelta(hours=2),  # 2 hours ago
        )

        assert rule.is_on_cooldown() is False

    def test_is_on_cooldown_active(self):
        """Test cooldown check when still in cooldown period."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            cooldown_minutes=60,
            last_triggered_at=utcnow() - timedelta(minutes=30),  # 30 min ago
        )

        assert rule.is_on_cooldown() is True

    def test_is_on_cooldown_zero_cooldown(self):
        """Test cooldown check with zero cooldown period."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            cooldown_minutes=0,
            last_triggered_at=utcnow(),
        )

        assert rule.is_on_cooldown() is False

    def test_trigger_updates_counters(self):
        """Test that trigger() updates timestamp and count."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            trigger_count=5,
            last_triggered_at=None,
        )

        rule.trigger()

        assert rule.trigger_count == 6
        assert rule.last_triggered_at is not None

    def test_render_title(self):
        """Test title template rendering."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            title_template="{change_type} for {asset_name}",
        )

        title = rule.render_title({
            "change_type": "Asset Discovered",
            "asset_name": "web-server-01",
        })

        assert title == "Asset Discovered for web-server-01"

    def test_render_title_missing_placeholder(self):
        """Test title rendering with missing placeholder."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            title_template="{change_type} for {asset_name}",
        )

        # Missing asset_name should return template as-is
        title = rule.render_title({"change_type": "Asset Discovered"})

        assert title == "{change_type} for {asset_name}"

    def test_render_description(self):
        """Test description template rendering."""
        rule = AlertRule(
            name="Test Rule",
            change_types=["asset_discovered"],
            severity=AlertSeverity.WARNING,
            description_template="{summary}\n\nEnvironment: {environment}",
        )

        description = rule.render_description({
            "summary": "New asset discovered",
            "environment": "production",
        })

        assert description == "New asset discovered\n\nEnvironment: production"


@pytest.mark.unit
class TestMaintenanceWindowChecks:
    """Test cases for maintenance window suppression."""

    def test_maintenance_window_is_active(self):
        """Test maintenance window active check."""
        now = utcnow()
        window = MaintenanceWindow(
            name="Weekly Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert window.is_currently_active() is True

    def test_maintenance_window_not_active_future(self):
        """Test maintenance window that hasn't started."""
        now = utcnow()
        window = MaintenanceWindow(
            name="Future Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
        )

        assert window.is_currently_active() is False

    def test_maintenance_window_not_active_past(self):
        """Test maintenance window that has ended."""
        now = utcnow()
        window = MaintenanceWindow(
            name="Past Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1),
        )

        assert window.is_currently_active() is False

    def test_maintenance_window_disabled(self):
        """Test disabled maintenance window."""
        now = utcnow()
        window = MaintenanceWindow(
            name="Disabled Maintenance",
            created_by="admin",
            is_active=False,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )

        assert window.is_currently_active() is False

    def test_maintenance_window_affects_asset_global(self):
        """Test global maintenance window affects all assets."""
        asset_id = uuid4()
        now = utcnow()
        window = MaintenanceWindow(
            name="Global Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            asset_ids=None,
            environments=None,
            datacenters=None,
        )

        assert window.affects_asset(asset_id) is True

    def test_maintenance_window_affects_asset_by_id(self):
        """Test maintenance window matching asset ID."""
        asset_id = uuid4()
        other_asset_id = uuid4()
        now = utcnow()
        window = MaintenanceWindow(
            name="Asset-specific Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            asset_ids=[asset_id],
        )

        assert window.affects_asset(asset_id) is True
        assert window.affects_asset(other_asset_id) is False

    def test_maintenance_window_affects_asset_by_environment(self):
        """Test maintenance window matching environment."""
        asset_id = uuid4()
        now = utcnow()
        window = MaintenanceWindow(
            name="Env-specific Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            environments=["production", "staging"],
        )

        assert window.affects_asset(asset_id, environment="production") is True
        assert window.affects_asset(asset_id, environment="development") is False

    def test_maintenance_window_affects_asset_by_datacenter(self):
        """Test maintenance window matching datacenter."""
        asset_id = uuid4()
        now = utcnow()
        window = MaintenanceWindow(
            name="DC-specific Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            datacenters=["dc1", "dc2"],
        )

        assert window.affects_asset(asset_id, datacenter="dc1") is True
        assert window.affects_asset(asset_id, datacenter="dc3") is False

    def test_maintenance_window_increment_suppressed(self):
        """Test suppressed count increment."""
        now = utcnow()
        window = MaintenanceWindow(
            name="Test Maintenance",
            created_by="admin",
            is_active=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            suppressed_alerts_count=0,
        )

        window.increment_suppressed()
        assert window.suppressed_alerts_count == 1

        window.increment_suppressed()
        assert window.suppressed_alerts_count == 2
