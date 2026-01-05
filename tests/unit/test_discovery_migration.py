"""Unit tests for discovery provider migration from environment variables."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from flowlens.discovery.migration import (
    K8S_DEFAULT_NAME,
    NUTANIX_DEFAULT_NAME,
    VCENTER_DEFAULT_NAME,
    _migrate_kubernetes,
    _migrate_nutanix,
    _migrate_vcenter,
    _provider_exists,
    migrate_env_providers,
)


class MockKubernetesSettings:
    """Mock Kubernetes settings for testing."""

    def __init__(
        self,
        enabled=False,
        api_server="https://k8s.example.com:6443",
        cluster_name="test-cluster",
        namespace=None,
        token=None,
        token_file=None,
        ca_cert_path=None,
        verify_ssl=True,
        timeout_seconds=10.0,
    ):
        self.enabled = enabled
        self.api_server = api_server
        self.cluster_name = cluster_name
        self.namespace = namespace
        self.token = token
        self.token_file = token_file
        self.ca_cert_path = ca_cert_path
        self.verify_ssl = verify_ssl
        self.timeout_seconds = timeout_seconds


class MockVCenterSettings:
    """Mock vCenter settings for testing."""

    def __init__(
        self,
        enabled=False,
        api_url="https://vcenter.example.com",
        username=None,
        password=None,
        verify_ssl=True,
        timeout_seconds=15.0,
        include_tags=True,
    ):
        self.enabled = enabled
        self.api_url = api_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout_seconds = timeout_seconds
        self.include_tags = include_tags


class MockNutanixSettings:
    """Mock Nutanix settings for testing."""

    def __init__(
        self,
        enabled=False,
        api_url="https://nutanix.example.com:9440",
        username=None,
        password=None,
        verify_ssl=True,
        timeout_seconds=15.0,
    ):
        self.enabled = enabled
        self.api_url = api_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout_seconds = timeout_seconds


class MockSecretStr:
    """Mock SecretStr for testing."""

    def __init__(self, value):
        self._value = value

    def get_secret_value(self):
        return self._value


@pytest.mark.asyncio
class TestProviderExists:
    """Tests for _provider_exists helper."""

    async def test_provider_exists_true(self) -> None:
        """Test when provider with name exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Returns a provider

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _provider_exists(db, "test-provider")

        assert result is True
        db.execute.assert_called_once()

    async def test_provider_exists_false(self) -> None:
        """Test when provider with name doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await _provider_exists(db, "nonexistent")

        assert result is False


@pytest.mark.asyncio
class TestMigrateKubernetes:
    """Tests for _migrate_kubernetes."""

    async def test_disabled_returns_none(self) -> None:
        """Test that disabled settings returns None."""
        db = AsyncMock()
        settings = MockKubernetesSettings(enabled=False)

        result = await _migrate_kubernetes(db, settings)

        assert result is None
        db.execute.assert_not_called()

    async def test_existing_provider_skipped(self) -> None:
        """Test that existing provider is skipped."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # Provider exists

        db = AsyncMock()
        db.execute.return_value = mock_result

        settings = MockKubernetesSettings(enabled=True)

        result = await _migrate_kubernetes(db, settings)

        assert result is None

    async def test_creates_provider_with_token(self) -> None:
        """Test creating provider with direct token."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing provider

        db = AsyncMock()
        db.execute.return_value = mock_result
        # Override add to be a sync MagicMock with side_effect
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        settings = MockKubernetesSettings(
            enabled=True,
            api_server="https://k8s.prod.com:6443",
            cluster_name="prod-cluster",
            namespace="kube-system",
            token="my-secret-token",
            verify_ssl=True,
            timeout_seconds=10.0,
        )

        result = await _migrate_kubernetes(db, settings)

        # Result should be a UUID since id was set
        assert result is not None
        db.add.assert_called_once()
        db.flush.assert_called_once()

        # Verify the provider was created correctly
        provider = db.add.call_args[0][0]
        assert provider.name == K8S_DEFAULT_NAME
        assert provider.provider_type == "kubernetes"
        assert provider.api_url == "https://k8s.prod.com:6443"
        assert provider.k8s_config["cluster_name"] == "prod-cluster"
        assert provider.k8s_config["namespace"] == "kube-system"
        assert provider.k8s_config["token_encrypted"] == "my-secret-token"

    async def test_reads_token_from_file(self) -> None:
        """Test reading token from token file."""
        with NamedTemporaryFile(mode="w", delete=False, suffix=".token") as f:
            f.write("file-based-token")
            token_file = Path(f.name)

        try:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None

            db = AsyncMock()
            db.execute.return_value = mock_result
            db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

            settings = MockKubernetesSettings(
                enabled=True,
                token=None,  # No direct token
                token_file=token_file,
            )

            result = await _migrate_kubernetes(db, settings)

            assert result is not None
            db.add.assert_called_once()
            provider = db.add.call_args[0][0]
            assert provider.k8s_config["token_encrypted"] == "file-based-token"
        finally:
            token_file.unlink()

    async def test_reads_ca_cert(self) -> None:
        """Test reading CA certificate from file."""
        with NamedTemporaryFile(mode="w", delete=False, suffix=".crt") as f:
            f.write("-----BEGIN CERTIFICATE-----\ntest-cert\n-----END CERTIFICATE-----")
            ca_file = Path(f.name)

        try:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None

            db = AsyncMock()
            db.execute.return_value = mock_result
            db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

            settings = MockKubernetesSettings(
                enabled=True,
                ca_cert_path=ca_file,
            )

            result = await _migrate_kubernetes(db, settings)

            assert result is not None
            db.add.assert_called_once()
            provider = db.add.call_args[0][0]
            assert "BEGIN CERTIFICATE" in provider.k8s_config["ca_cert"]
        finally:
            ca_file.unlink()


@pytest.mark.asyncio
class TestMigrateVCenter:
    """Tests for _migrate_vcenter."""

    async def test_disabled_returns_none(self) -> None:
        """Test that disabled settings returns None."""
        db = AsyncMock()
        settings = MockVCenterSettings(enabled=False)

        result = await _migrate_vcenter(db, settings)

        assert result is None

    async def test_existing_provider_skipped(self) -> None:
        """Test that existing provider is skipped."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()

        db = AsyncMock()
        db.execute.return_value = mock_result

        settings = MockVCenterSettings(enabled=True)

        result = await _migrate_vcenter(db, settings)

        assert result is None

    async def test_creates_provider(self) -> None:
        """Test creating vCenter provider."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        settings = MockVCenterSettings(
            enabled=True,
            api_url="https://vcenter.prod.com",
            username="admin@vsphere.local",
            password=MockSecretStr("secret-password"),
            verify_ssl=False,
            timeout_seconds=30.0,
            include_tags=True,
        )

        result = await _migrate_vcenter(db, settings)

        assert result is not None
        db.add.assert_called_once()

        provider = db.add.call_args[0][0]
        assert provider.name == VCENTER_DEFAULT_NAME
        assert provider.provider_type == "vcenter"
        assert provider.api_url == "https://vcenter.prod.com"
        assert provider.username == "admin@vsphere.local"
        assert provider.password_encrypted == "secret-password"
        assert provider.verify_ssl is False
        assert provider.vcenter_config["include_tags"] is True

    async def test_no_password(self) -> None:
        """Test creating provider without password."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        settings = MockVCenterSettings(
            enabled=True,
            password=None,
        )

        result = await _migrate_vcenter(db, settings)

        assert result is not None
        db.add.assert_called_once()
        provider = db.add.call_args[0][0]
        assert provider.password_encrypted is None


@pytest.mark.asyncio
class TestMigrateNutanix:
    """Tests for _migrate_nutanix."""

    async def test_disabled_returns_none(self) -> None:
        """Test that disabled settings returns None."""
        db = AsyncMock()
        settings = MockNutanixSettings(enabled=False)

        result = await _migrate_nutanix(db, settings)

        assert result is None

    async def test_existing_provider_skipped(self) -> None:
        """Test that existing provider is skipped."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()

        db = AsyncMock()
        db.execute.return_value = mock_result

        settings = MockNutanixSettings(enabled=True)

        result = await _migrate_nutanix(db, settings)

        assert result is None

    async def test_creates_provider(self) -> None:
        """Test creating Nutanix provider."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        settings = MockNutanixSettings(
            enabled=True,
            api_url="https://nutanix.prod.com:9440",
            username="admin",
            password=MockSecretStr("nutanix-pass"),
            verify_ssl=True,
            timeout_seconds=20.0,
        )

        result = await _migrate_nutanix(db, settings)

        assert result is not None
        db.add.assert_called_once()

        provider = db.add.call_args[0][0]
        assert provider.name == NUTANIX_DEFAULT_NAME
        assert provider.provider_type == "nutanix"
        assert provider.api_url == "https://nutanix.prod.com:9440"
        assert provider.username == "admin"
        assert provider.password_encrypted == "nutanix-pass"


@pytest.mark.asyncio
class TestMigrateEnvProviders:
    """Tests for migrate_env_providers main function."""

    async def test_migrates_all_enabled_providers(self) -> None:
        """Test migrating all enabled providers."""

        class MockSettings:
            kubernetes = MockKubernetesSettings(enabled=True, cluster_name="k8s-prod")
            vcenter = MockVCenterSettings(enabled=True)
            nutanix = MockNutanixSettings(enabled=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing providers

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        with patch("flowlens.discovery.migration.get_settings", return_value=MockSettings()):
            results = await migrate_env_providers(db)

        # All should be migrated (have UUIDs)
        assert results["kubernetes"] is not None
        assert results["vcenter"] is not None
        assert results["nutanix"] is not None

        # Should have committed
        db.commit.assert_called_once()

    async def test_skips_disabled_providers(self) -> None:
        """Test skipping disabled providers."""

        class MockSettings:
            kubernetes = MockKubernetesSettings(enabled=False)
            vcenter = MockVCenterSettings(enabled=True)
            nutanix = MockNutanixSettings(enabled=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute.return_value = mock_result
        db.add = MagicMock(side_effect=lambda p: setattr(p, 'id', uuid4()))

        with patch("flowlens.discovery.migration.get_settings", return_value=MockSettings()):
            results = await migrate_env_providers(db)

        assert results["kubernetes"] is None
        assert results["vcenter"] is not None
        assert results["nutanix"] is None

    async def test_no_providers_enabled(self) -> None:
        """Test when no providers are enabled."""

        class MockSettings:
            kubernetes = MockKubernetesSettings(enabled=False)
            vcenter = MockVCenterSettings(enabled=False)
            nutanix = MockNutanixSettings(enabled=False)

        db = AsyncMock()

        with patch("flowlens.discovery.migration.get_settings", return_value=MockSettings()):
            results = await migrate_env_providers(db)

        assert results["kubernetes"] is None
        assert results["vcenter"] is None
        assert results["nutanix"] is None

        # Should still commit (even if nothing to do)
        db.commit.assert_called_once()
