"""Unit tests for change detection service."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from flowlens.models.change import AlertSeverity, ChangeType, ChangeEvent
from flowlens.resolution.change_detector import ChangeDetector


@pytest.mark.unit
class TestChangeDetector:
    """Test cases for ChangeDetector."""

    @pytest.fixture
    def detector(self) -> ChangeDetector:
        """Create change detector instance."""
        return ChangeDetector()

    def test_detector_initialization(self, detector: ChangeDetector):
        """Test detector initializes with correct defaults."""
        assert detector._stale_threshold_hours > 0
        assert detector._traffic_spike_threshold == 2.0
        assert detector._traffic_drop_threshold == 0.5

    def test_determine_severity_critical_events(self, detector: ChangeDetector):
        """Test critical events return critical severity."""
        critical_types = [
            ChangeType.CRITICAL_PATH_CHANGE,
            ChangeType.ASSET_OFFLINE,
        ]

        for change_type in critical_types:
            event = MagicMock(spec=ChangeEvent)
            event.change_type = change_type
            event.impact_score = 0

            severity = detector._determine_severity(event)
            assert severity == AlertSeverity.CRITICAL, f"{change_type} should be CRITICAL"

    def test_determine_severity_error_events(self, detector: ChangeDetector):
        """Test error-level events return error severity."""
        error_types = [
            ChangeType.DEPENDENCY_REMOVED,
            ChangeType.ASSET_REMOVED,
            ChangeType.DEPENDENCY_TRAFFIC_DROP,
        ]

        for change_type in error_types:
            event = MagicMock(spec=ChangeEvent)
            event.change_type = change_type
            event.impact_score = 0

            severity = detector._determine_severity(event)
            assert severity == AlertSeverity.ERROR, f"{change_type} should be ERROR"

    def test_determine_severity_warning_events(self, detector: ChangeDetector):
        """Test warning-level events return warning severity."""
        warning_types = [
            ChangeType.DEPENDENCY_STALE,
            ChangeType.DEPENDENCY_TRAFFIC_SPIKE,
            ChangeType.NEW_EXTERNAL_CONNECTION,
        ]

        for change_type in warning_types:
            event = MagicMock(spec=ChangeEvent)
            event.change_type = change_type
            event.impact_score = 0

            severity = detector._determine_severity(event)
            assert severity == AlertSeverity.WARNING, f"{change_type} should be WARNING"

    def test_determine_severity_info_events(self, detector: ChangeDetector):
        """Test info-level events return info severity."""
        info_types = [
            ChangeType.DEPENDENCY_CREATED,
            ChangeType.ASSET_DISCOVERED,
            ChangeType.SERVICE_DISCOVERED,
            ChangeType.ASSET_ONLINE,
        ]

        for change_type in info_types:
            event = MagicMock(spec=ChangeEvent)
            event.change_type = change_type
            event.impact_score = 0

            severity = detector._determine_severity(event)
            assert severity == AlertSeverity.INFO, f"{change_type} should be INFO"

    def test_determine_severity_by_impact_score_critical(self, detector: ChangeDetector):
        """Test severity from high impact score."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.SERVICE_REMOVED  # Not in explicit mappings
        event.impact_score = 80

        severity = detector._determine_severity(event)
        assert severity == AlertSeverity.CRITICAL

    def test_determine_severity_by_impact_score_error(self, detector: ChangeDetector):
        """Test severity from medium-high impact score."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.SERVICE_REMOVED
        event.impact_score = 60

        severity = detector._determine_severity(event)
        assert severity == AlertSeverity.ERROR

    def test_determine_severity_by_impact_score_warning(self, detector: ChangeDetector):
        """Test severity from medium impact score."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.SERVICE_REMOVED
        event.impact_score = 40

        severity = detector._determine_severity(event)
        assert severity == AlertSeverity.WARNING

    def test_determine_severity_by_impact_score_info(self, detector: ChangeDetector):
        """Test severity from low impact score."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.SERVICE_REMOVED
        event.impact_score = 10

        severity = detector._determine_severity(event)
        assert severity == AlertSeverity.INFO

    def test_generate_alert_title_dependency_created(self, detector: ChangeDetector):
        """Test alert title generation for new dependency."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.DEPENDENCY_CREATED

        title = detector._generate_alert_title(event)
        assert title == "New Dependency Discovered"

    def test_generate_alert_title_dependency_removed(self, detector: ChangeDetector):
        """Test alert title generation for removed dependency."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.DEPENDENCY_REMOVED

        title = detector._generate_alert_title(event)
        assert title == "Dependency Removed"

    def test_generate_alert_title_asset_offline(self, detector: ChangeDetector):
        """Test alert title generation for offline asset."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.ASSET_OFFLINE

        title = detector._generate_alert_title(event)
        assert title == "Asset Offline"

    def test_generate_alert_title_traffic_spike(self, detector: ChangeDetector):
        """Test alert title generation for traffic spike."""
        event = MagicMock(spec=ChangeEvent)
        event.change_type = ChangeType.DEPENDENCY_TRAFFIC_SPIKE

        title = detector._generate_alert_title(event)
        assert title == "Traffic Spike Detected"

    def test_generate_alert_title_all_change_types(self, detector: ChangeDetector):
        """Test that all change types have titles."""
        for change_type in ChangeType:
            event = MagicMock(spec=ChangeEvent)
            event.change_type = change_type

            title = detector._generate_alert_title(event)
            assert isinstance(title, str)
            assert len(title) > 0

    def test_generate_alert_message_basic(self, detector: ChangeDetector):
        """Test basic alert message generation."""
        event = MagicMock(spec=ChangeEvent)
        event.summary = "Test summary"
        event.description = None
        event.affected_assets_count = 0
        event.previous_state = None
        event.new_state = None

        message = detector._generate_alert_message(event)

        assert "Test summary" in message

    def test_generate_alert_message_with_description(self, detector: ChangeDetector):
        """Test alert message with description."""
        event = MagicMock(spec=ChangeEvent)
        event.summary = "Test summary"
        event.description = "Detailed description"
        event.affected_assets_count = 0
        event.previous_state = None
        event.new_state = None

        message = detector._generate_alert_message(event)

        assert "Test summary" in message
        assert "Detailed description" in message

    def test_generate_alert_message_with_affected_assets(self, detector: ChangeDetector):
        """Test alert message with affected assets count."""
        event = MagicMock(spec=ChangeEvent)
        event.summary = "Test summary"
        event.description = None
        event.affected_assets_count = 5
        event.previous_state = None
        event.new_state = None

        message = detector._generate_alert_message(event)

        assert "Affected assets: 5" in message

    def test_generate_alert_message_with_state_changes(self, detector: ChangeDetector):
        """Test alert message with state change details."""
        event = MagicMock(spec=ChangeEvent)
        event.summary = "Test summary"
        event.description = None
        event.affected_assets_count = 0
        event.previous_state = {"status": "online"}
        event.new_state = {"status": "offline"}

        message = detector._generate_alert_message(event)

        assert "Change details" in message
        assert "Previous" in message
        assert "New" in message


@pytest.mark.unit
class TestChangeTypes:
    """Test cases for change type definitions."""

    def test_all_change_types_defined(self):
        """Test all expected change types are defined."""
        expected_types = [
            "dependency_created",
            "dependency_removed",
            "dependency_stale",
            "dependency_traffic_spike",
            "dependency_traffic_drop",
            "asset_discovered",
            "asset_removed",
            "asset_offline",
            "asset_online",
            "service_discovered",
            "service_removed",
            "new_external_connection",
            "critical_path_change",
        ]

        actual_types = [ct.value for ct in ChangeType]

        for expected in expected_types:
            assert expected in actual_types, f"Missing change type: {expected}"

    def test_change_type_string_conversion(self):
        """Test change type to string conversion."""
        assert ChangeType.DEPENDENCY_CREATED.value == "dependency_created"
        assert ChangeType.ASSET_OFFLINE.value == "asset_offline"

    def test_change_type_from_string(self):
        """Test creating change type from string."""
        assert ChangeType("dependency_created") == ChangeType.DEPENDENCY_CREATED
        assert ChangeType("asset_offline") == ChangeType.ASSET_OFFLINE


@pytest.mark.unit
class TestAlertSeverity:
    """Test cases for alert severity definitions."""

    def test_all_severities_defined(self):
        """Test all expected severities are defined."""
        expected_severities = ["info", "warning", "error", "critical"]

        actual_severities = [s.value for s in AlertSeverity]

        for expected in expected_severities:
            assert expected in actual_severities, f"Missing severity: {expected}"

    def test_severity_ordering(self):
        """Test severity ordering by value."""
        # Verify the expected order exists
        severities = list(AlertSeverity)
        assert AlertSeverity.INFO in severities
        assert AlertSeverity.WARNING in severities
        assert AlertSeverity.ERROR in severities
        assert AlertSeverity.CRITICAL in severities


@pytest.mark.unit
class TestTrafficThresholds:
    """Test cases for traffic anomaly thresholds."""

    @pytest.fixture
    def detector(self) -> ChangeDetector:
        """Create change detector instance."""
        return ChangeDetector()

    def test_spike_threshold(self, detector: ChangeDetector):
        """Test traffic spike threshold is 2x."""
        assert detector._traffic_spike_threshold == 2.0

    def test_drop_threshold(self, detector: ChangeDetector):
        """Test traffic drop threshold is 50%."""
        assert detector._traffic_drop_threshold == 0.5

    def test_spike_calculation(self, detector: ChangeDetector):
        """Test spike detection calculation logic.

        A spike is when: 24h traffic * 7 > 7d traffic * spike_threshold
        This means daily rate exceeds 7-day average by the threshold.
        """
        # Normal case: 100 bytes/day average over 7 days
        bytes_7d = 700
        bytes_24h_normal = 100

        # Spike: 24h traffic is 3x the daily average
        bytes_24h_spike = 300

        # Check spike condition
        is_normal = (bytes_24h_normal * 7) > (bytes_7d * detector._traffic_spike_threshold)
        is_spike = (bytes_24h_spike * 7) > (bytes_7d * detector._traffic_spike_threshold)

        assert is_normal is False  # Normal traffic is not a spike
        assert is_spike is True  # 3x average is a spike

    def test_drop_calculation(self, detector: ChangeDetector):
        """Test drop detection calculation logic.

        A drop is when: 24h traffic * 7 < 7d traffic * drop_threshold
        This means daily rate is below 50% of 7-day average.
        """
        # Normal case: 100 bytes/day average over 7 days
        bytes_7d = 700
        bytes_24h_normal = 100

        # Drop: 24h traffic is only 20% of daily average
        bytes_24h_drop = 20

        # Check drop condition
        is_normal = (bytes_24h_normal * 7) < (bytes_7d * detector._traffic_drop_threshold)
        is_drop = (bytes_24h_drop * 7) < (bytes_7d * detector._traffic_drop_threshold)

        assert is_normal is False  # Normal traffic is not a drop
        assert is_drop is True  # 20% of average is a drop
