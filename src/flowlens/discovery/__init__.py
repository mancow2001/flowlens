"""Discovery modules for external systems."""

from flowlens.discovery.cache import (
    MultiProviderAssetCache,
    get_multi_provider_cache,
)
from flowlens.discovery.enricher import (
    MultiProviderAssetEnricher,
    get_multi_provider_enricher,
)
from flowlens.discovery.migration import migrate_env_providers
from flowlens.discovery.kubernetes import (
    KubernetesApplicationMapping,
    KubernetesAssetMetadata,
    KubernetesAssetEnricher,
    KubernetesDiscoveryClient,
    KubernetesDiscoveryService,
    KubernetesProviderClient,
    KubernetesProviderDiscoveryService,
    KubernetesSnapshot,
    get_kubernetes_asset_cache,
)
from flowlens.discovery.nutanix import (
    NutanixApplicationMapping,
    NutanixAssetEnricher,
    NutanixDiscoveryClient,
    NutanixDiscoveryService,
    NutanixProviderClient,
    NutanixProviderDiscoveryService,
    NutanixSnapshot,
    NutanixVMMetadata,
    get_nutanix_asset_cache,
)
from flowlens.discovery.vcenter import (
    VCenterApplicationMapping,
    VCenterAssetEnricher,
    VCenterDiscoveryClient,
    VCenterDiscoveryService,
    VCenterProviderClient,
    VCenterProviderDiscoveryService,
    VCenterSnapshot,
    VCenterVMMetadata,
    get_vcenter_asset_cache,
)

__all__ = [
    # Multi-provider cache and enricher
    "MultiProviderAssetCache",
    "MultiProviderAssetEnricher",
    "get_multi_provider_cache",
    "get_multi_provider_enricher",
    "migrate_env_providers",
    # Kubernetes
    "KubernetesApplicationMapping",
    "KubernetesAssetMetadata",
    "KubernetesAssetEnricher",
    "KubernetesDiscoveryClient",
    "KubernetesDiscoveryService",
    "KubernetesProviderClient",
    "KubernetesProviderDiscoveryService",
    "KubernetesSnapshot",
    "get_kubernetes_asset_cache",
    # Nutanix
    "NutanixApplicationMapping",
    "NutanixAssetEnricher",
    "NutanixDiscoveryClient",
    "NutanixDiscoveryService",
    "NutanixProviderClient",
    "NutanixProviderDiscoveryService",
    "NutanixSnapshot",
    "NutanixVMMetadata",
    "get_nutanix_asset_cache",
    # vCenter
    "VCenterApplicationMapping",
    "VCenterAssetEnricher",
    "VCenterDiscoveryClient",
    "VCenterDiscoveryService",
    "VCenterProviderClient",
    "VCenterProviderDiscoveryService",
    "VCenterSnapshot",
    "VCenterVMMetadata",
    "get_vcenter_asset_cache",
]
