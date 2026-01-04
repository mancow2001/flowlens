"""Unit tests for dependency builder external filtering logic."""

import pytest

from flowlens.common.config import ResolutionSettings
from flowlens.enrichment.resolvers.geoip import PrivateIPClassifier
from flowlens.resolution.dependency_builder import DependencyBuilder


@pytest.mark.unit
class TestPrivateIPClassifier:
    """Test cases for PrivateIPClassifier."""

    @pytest.fixture
    def classifier(self) -> PrivateIPClassifier:
        """Create classifier instance."""
        return PrivateIPClassifier()

    # RFC 1918 Private Ranges
    def test_class_a_private_range(self, classifier: PrivateIPClassifier):
        """Test Class A private range (10.0.0.0/8)."""
        assert classifier.is_private("10.0.0.1") is True
        assert classifier.is_private("10.255.255.255") is True
        assert classifier.is_private("10.100.50.25") is True

    def test_class_b_private_range(self, classifier: PrivateIPClassifier):
        """Test Class B private range (172.16.0.0/12)."""
        assert classifier.is_private("172.16.0.1") is True
        assert classifier.is_private("172.31.255.255") is True
        assert classifier.is_private("172.20.10.5") is True
        # 172.15.x and 172.32.x should NOT be private
        assert classifier.is_private("172.15.255.255") is False
        assert classifier.is_private("172.32.0.1") is False

    def test_class_c_private_range(self, classifier: PrivateIPClassifier):
        """Test Class C private range (192.168.0.0/16)."""
        assert classifier.is_private("192.168.0.1") is True
        assert classifier.is_private("192.168.255.255") is True
        assert classifier.is_private("192.168.1.100") is True

    def test_loopback_range(self, classifier: PrivateIPClassifier):
        """Test loopback range (127.0.0.0/8)."""
        assert classifier.is_private("127.0.0.1") is True
        assert classifier.is_private("127.255.255.255") is True

    def test_link_local_range(self, classifier: PrivateIPClassifier):
        """Test link-local range (169.254.0.0/16)."""
        assert classifier.is_private("169.254.0.1") is True
        assert classifier.is_private("169.254.255.255") is True

    # Public IPs
    def test_public_ip_addresses(self, classifier: PrivateIPClassifier):
        """Test public IP addresses are not private."""
        assert classifier.is_private("8.8.8.8") is False  # Google DNS
        assert classifier.is_private("1.1.1.1") is False  # Cloudflare DNS
        assert classifier.is_private("52.94.76.1") is False  # AWS
        assert classifier.is_private("104.16.0.1") is False  # Cloudflare
        assert classifier.is_private("142.250.80.14") is False  # Google

    def test_boundary_addresses(self, classifier: PrivateIPClassifier):
        """Test boundary addresses between private and public."""
        # Just before 10.0.0.0 range
        assert classifier.is_private("9.255.255.255") is False
        # Just after 10.255.255.255
        assert classifier.is_private("11.0.0.0") is False
        # Just before 192.168.0.0
        assert classifier.is_private("192.167.255.255") is False
        # Just after 192.168.255.255
        assert classifier.is_private("192.169.0.0") is False

    def test_classify_method(self, classifier: PrivateIPClassifier):
        """Test classify method returns correct strings."""
        assert classifier.classify("192.168.1.1") == "private"
        assert classifier.classify("8.8.8.8") == "public"

    def test_special_addresses(self, classifier: PrivateIPClassifier):
        """Test special use addresses are detected."""
        # CGNAT range
        assert classifier.is_special("100.64.0.1") is True
        assert classifier.is_special("100.127.255.255") is True
        # Documentation ranges
        assert classifier.is_special("192.0.2.1") is True
        assert classifier.is_special("198.51.100.1") is True
        assert classifier.is_special("203.0.113.1") is True
        # Multicast
        assert classifier.is_special("224.0.0.1") is True

    def test_invalid_ip_returns_false(self, classifier: PrivateIPClassifier):
        """Test invalid IPs return False for is_private."""
        assert classifier.is_private("invalid") is False
        assert classifier.is_private("") is False
        assert classifier.is_private("999.999.999.999") is False


@pytest.mark.unit
class TestDependencyBuilderExternalFiltering:
    """Test cases for DependencyBuilder._should_exclude_external method."""

    @pytest.fixture
    def settings_discard_external(self) -> ResolutionSettings:
        """Settings with discard_external_flows=True (default)."""
        return ResolutionSettings(discard_external_flows=True)

    @pytest.fixture
    def settings_allow_external(self) -> ResolutionSettings:
        """Settings with discard_external_flows=False."""
        return ResolutionSettings(discard_external_flows=False)

    @pytest.fixture
    def settings_exclude_external_ips(self) -> ResolutionSettings:
        """Settings with exclude_external_ips=True."""
        return ResolutionSettings(
            discard_external_flows=False,
            exclude_external_ips=True,
        )

    @pytest.fixture
    def settings_exclude_external_sources(self) -> ResolutionSettings:
        """Settings with exclude_external_sources=True."""
        return ResolutionSettings(
            discard_external_flows=False,
            exclude_external_sources=True,
        )

    @pytest.fixture
    def settings_exclude_external_targets(self) -> ResolutionSettings:
        """Settings with exclude_external_targets=True."""
        return ResolutionSettings(
            discard_external_flows=False,
            exclude_external_targets=True,
        )

    def test_discard_external_internal_to_internal_allowed(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test internal→internal is ALLOWED when discard_external_flows=True."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # Internal to internal should NOT be excluded
        assert builder._should_exclude_external("192.168.1.100", "192.168.1.200") is False
        assert builder._should_exclude_external("10.0.0.1", "10.0.0.2") is False
        assert builder._should_exclude_external("172.16.0.1", "172.31.255.255") is False

    def test_discard_external_internal_to_external_excluded(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test internal→external is EXCLUDED when discard_external_flows=True."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # Internal to external should be excluded
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is True
        assert builder._should_exclude_external("10.0.0.1", "1.1.1.1") is True

    def test_discard_external_external_to_internal_excluded(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test external→internal is EXCLUDED when discard_external_flows=True."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # External to internal should be excluded
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is True
        assert builder._should_exclude_external("1.1.1.1", "10.0.0.1") is True

    def test_discard_external_external_to_external_excluded(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test external→external is EXCLUDED when discard_external_flows=True."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # External to external should be excluded
        assert builder._should_exclude_external("8.8.8.8", "1.1.1.1") is True
        assert builder._should_exclude_external("52.94.76.1", "104.16.0.1") is True

    def test_allow_external_all_flows_allowed(
        self, settings_allow_external: ResolutionSettings
    ):
        """Test all flows allowed when discard_external_flows=False and no granular settings."""
        builder = DependencyBuilder(settings=settings_allow_external)

        # All flow types should be allowed
        assert builder._should_exclude_external("192.168.1.100", "192.168.1.200") is False
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is False
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is False
        assert builder._should_exclude_external("8.8.8.8", "1.1.1.1") is False

    def test_exclude_external_ips_filters_any_external(
        self, settings_exclude_external_ips: ResolutionSettings
    ):
        """Test exclude_external_ips filters any flow with external IP."""
        builder = DependencyBuilder(settings=settings_exclude_external_ips)

        # Internal to internal - allowed
        assert builder._should_exclude_external("192.168.1.100", "192.168.1.200") is False

        # Any external involvement - excluded
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is True
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is True
        assert builder._should_exclude_external("8.8.8.8", "1.1.1.1") is True

    def test_exclude_external_sources_only(
        self, settings_exclude_external_sources: ResolutionSettings
    ):
        """Test exclude_external_sources only filters external sources."""
        builder = DependencyBuilder(settings=settings_exclude_external_sources)

        # Internal to internal - allowed
        assert builder._should_exclude_external("192.168.1.100", "192.168.1.200") is False

        # Internal to external - allowed (target is external, source is internal)
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is False

        # External to internal - excluded (source is external)
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is True

        # External to external - excluded (source is external)
        assert builder._should_exclude_external("8.8.8.8", "1.1.1.1") is True

    def test_exclude_external_targets_only(
        self, settings_exclude_external_targets: ResolutionSettings
    ):
        """Test exclude_external_targets only filters external targets."""
        builder = DependencyBuilder(settings=settings_exclude_external_targets)

        # Internal to internal - allowed
        assert builder._should_exclude_external("192.168.1.100", "192.168.1.200") is False

        # Internal to external - excluded (target is external)
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is True

        # External to internal - allowed (target is internal)
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is False

        # External to external - excluded (target is external)
        assert builder._should_exclude_external("8.8.8.8", "1.1.1.1") is True

    def test_discard_external_with_different_private_ranges(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test filtering works across different RFC 1918 ranges."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # Cross-range internal traffic should be allowed
        assert builder._should_exclude_external("10.0.0.1", "192.168.1.1") is False
        assert builder._should_exclude_external("172.16.0.1", "10.0.0.1") is False
        assert builder._should_exclude_external("192.168.1.1", "172.20.0.1") is False

    def test_loopback_treated_as_internal(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test loopback addresses are treated as internal."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # Loopback to internal - allowed
        assert builder._should_exclude_external("127.0.0.1", "192.168.1.100") is False
        # Internal to loopback - allowed
        assert builder._should_exclude_external("192.168.1.100", "127.0.0.1") is False

    def test_link_local_treated_as_internal(
        self, settings_discard_external: ResolutionSettings
    ):
        """Test link-local addresses are treated as internal."""
        builder = DependencyBuilder(settings=settings_discard_external)

        # Link-local to internal - allowed
        assert builder._should_exclude_external("169.254.1.1", "192.168.1.100") is False


@pytest.mark.unit
class TestDependencyBuilderSettingsInjection:
    """Test that DependencyBuilder correctly uses injected settings."""

    def test_uses_injected_settings(self):
        """Test builder uses provided settings instead of global config."""
        # Create settings with specific configuration
        custom_settings = ResolutionSettings(
            discard_external_flows=False,
            exclude_external_sources=True,
        )

        builder = DependencyBuilder(settings=custom_settings)

        # Should use custom settings: external sources excluded, but external targets allowed
        # External source → internal target: excluded
        assert builder._should_exclude_external("8.8.8.8", "192.168.1.100") is True
        # Internal source → external target: allowed
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is False

    def test_default_settings_discard_external(self):
        """Test default settings have discard_external_flows=True."""
        default_settings = ResolutionSettings()
        assert default_settings.discard_external_flows is True

        builder = DependencyBuilder(settings=default_settings)
        # With default settings, any external IP should be excluded
        assert builder._should_exclude_external("192.168.1.100", "8.8.8.8") is True
