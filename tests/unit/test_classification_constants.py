"""Unit tests for classification constants."""

import pytest

from flowlens.classification.constants import (
    DATABASE_PORTS,
    STORAGE_PORTS,
    WEB_PORTS,
    SSH_PORTS,
    LOAD_BALANCER_PORTS,
    NETWORK_DEVICE_PORTS,
    CONTAINER_PORTS,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    PROTOCOL_ICMP,
    WELL_KNOWN_PORT_MAX,
    EPHEMERAL_PORT_MIN,
    ClassifiableAssetType,
    get_port_category,
    is_well_known_port,
    is_ephemeral_port,
    is_registered_port,
)


@pytest.mark.unit
class TestPortCategories:
    """Test cases for port category definitions."""

    def test_database_ports_defined(self):
        """Test database ports are defined."""
        assert 3306 in DATABASE_PORTS  # MySQL
        assert 5432 in DATABASE_PORTS  # PostgreSQL
        assert 1433 in DATABASE_PORTS  # MSSQL
        assert 27017 in DATABASE_PORTS  # MongoDB

    def test_storage_ports_defined(self):
        """Test storage ports are defined."""
        assert 2049 in STORAGE_PORTS  # NFS
        assert 445 in STORAGE_PORTS  # SMB
        assert 3260 in STORAGE_PORTS  # iSCSI

    def test_web_ports_defined(self):
        """Test web ports are defined."""
        assert 80 in WEB_PORTS  # HTTP
        assert 443 in WEB_PORTS  # HTTPS
        assert 8080 in WEB_PORTS  # Alt HTTP

    def test_ssh_ports_defined(self):
        """Test SSH ports are defined."""
        assert 22 in SSH_PORTS

    def test_load_balancer_ports_overlap_with_web(self):
        """Test load balancer ports include web ports."""
        assert 80 in LOAD_BALANCER_PORTS
        assert 443 in LOAD_BALANCER_PORTS

    def test_network_device_ports_defined(self):
        """Test network device ports are defined."""
        assert 161 in NETWORK_DEVICE_PORTS  # SNMP
        assert 179 in NETWORK_DEVICE_PORTS  # BGP

    def test_container_ports_defined(self):
        """Test container ports are defined."""
        assert 2375 in CONTAINER_PORTS  # Docker API
        assert 6443 in CONTAINER_PORTS  # K8s API


@pytest.mark.unit
class TestProtocolConstants:
    """Test cases for protocol number constants."""

    def test_tcp_protocol_number(self):
        """Test TCP protocol number is correct."""
        assert PROTOCOL_TCP == 6

    def test_udp_protocol_number(self):
        """Test UDP protocol number is correct."""
        assert PROTOCOL_UDP == 17

    def test_icmp_protocol_number(self):
        """Test ICMP protocol number is correct."""
        assert PROTOCOL_ICMP == 1


@pytest.mark.unit
class TestPortRangeFunctions:
    """Test cases for port range helper functions."""

    def test_well_known_port_valid(self):
        """Test well-known port detection for valid ports."""
        assert is_well_known_port(22) is True
        assert is_well_known_port(80) is True
        assert is_well_known_port(443) is True
        assert is_well_known_port(0) is True
        assert is_well_known_port(1023) is True

    def test_well_known_port_invalid(self):
        """Test well-known port detection for invalid ports."""
        assert is_well_known_port(1024) is False
        assert is_well_known_port(8080) is False
        assert is_well_known_port(50000) is False

    def test_ephemeral_port_valid(self):
        """Test ephemeral port detection for valid ports."""
        assert is_ephemeral_port(32768) is True
        assert is_ephemeral_port(50000) is True
        assert is_ephemeral_port(65535) is True

    def test_ephemeral_port_invalid(self):
        """Test ephemeral port detection for invalid ports."""
        assert is_ephemeral_port(22) is False
        assert is_ephemeral_port(8080) is False
        assert is_ephemeral_port(32767) is False

    def test_registered_port_valid(self):
        """Test registered port detection for valid ports."""
        assert is_registered_port(1024) is True
        assert is_registered_port(8080) is True
        assert is_registered_port(3306) is True
        assert is_registered_port(49151) is True

    def test_registered_port_invalid(self):
        """Test registered port detection for invalid ports."""
        assert is_registered_port(22) is False
        assert is_registered_port(80) is False
        assert is_registered_port(1023) is False
        assert is_registered_port(49152) is False


@pytest.mark.unit
class TestGetPortCategory:
    """Test cases for get_port_category function."""

    def test_database_port_category(self):
        """Test database ports return correct category."""
        assert get_port_category(3306) == "database"
        assert get_port_category(5432) == "database"

    def test_storage_port_category(self):
        """Test storage ports return correct category."""
        assert get_port_category(2049) == "storage"
        assert get_port_category(445) == "storage"

    def test_web_port_category(self):
        """Test web ports return correct category."""
        assert get_port_category(80) == "web"
        assert get_port_category(443) == "web"

    def test_ssh_port_category(self):
        """Test SSH port returns correct category."""
        assert get_port_category(22) == "ssh"

    def test_network_device_port_category(self):
        """Test network device ports return correct category."""
        assert get_port_category(161) == "network_device"

    def test_container_port_category(self):
        """Test container ports return correct category."""
        assert get_port_category(2375) == "container"
        assert get_port_category(6443) == "container"

    def test_unknown_port_category(self):
        """Test unknown ports return None."""
        assert get_port_category(12345) is None
        assert get_port_category(54321) is None

    def test_category_priority(self):
        """Test port category priority when port is in multiple sets.

        Note: Some ports may be in multiple sets (e.g., 80 is in both WEB_PORTS
        and LOAD_BALANCER_PORTS). The function should return the first match.
        """
        # 80 is checked for web before load_balancer
        result = get_port_category(80)
        assert result in ("web", "load_balancer")


@pytest.mark.unit
class TestClassifiableAssetType:
    """Test cases for ClassifiableAssetType enum."""

    def test_all_types_defined(self):
        """Test all expected types are defined."""
        expected = [
            "server",
            "workstation",
            "database",
            "load_balancer",
            "network_device",
            "storage",
            "container",
            "virtual_machine",
            "cloud_service",
            "unknown",
        ]
        actual = [t.value for t in ClassifiableAssetType]
        for expected_type in expected:
            assert expected_type in actual

    def test_type_string_conversion(self):
        """Test type to string conversion."""
        assert str(ClassifiableAssetType.SERVER) == "ClassifiableAssetType.SERVER"
        assert ClassifiableAssetType.SERVER.value == "server"

    def test_type_from_string(self):
        """Test creating type from string value."""
        assert ClassifiableAssetType("server") == ClassifiableAssetType.SERVER
        assert ClassifiableAssetType("database") == ClassifiableAssetType.DATABASE

    def test_invalid_type_raises_error(self):
        """Test invalid type string raises ValueError."""
        with pytest.raises(ValueError):
            ClassifiableAssetType("invalid")
