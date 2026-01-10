"""Synthetic data generator for ML classification.

Generates realistic BehavioralFeatures for each asset type based on
characteristic traffic patterns. Used to build the shipped model.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar

import numpy as np

from flowlens.classification.constants import (
    DATABASE_PORTS,
    LOAD_BALANCER_PORTS,
    NETWORK_DEVICE_PORTS,
    STORAGE_PORTS,
    WEB_PORTS,
)
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.ml.dataset import DatasetBuilder, TrainingDataset
from flowlens.classification.ml.feature_transformer import FeatureTransformer
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FeatureProfile:
    """Profile defining characteristic ranges for an asset type.

    All ranges are (min, max) tuples. Values are sampled uniformly
    within these ranges with optional Gaussian noise.
    """

    # Traffic directionality
    fan_in_range: tuple[int, int] = (0, 10)
    fan_out_range: tuple[int, int] = (0, 10)
    inbound_flows_range: tuple[int, int] = (100, 1000)
    outbound_flows_range: tuple[int, int] = (100, 1000)

    # Byte volumes (relative to flows)
    bytes_per_flow_range: tuple[int, int] = (1000, 10000)

    # Port behavior
    listener_ports: list[int] = field(default_factory=list)
    unique_dst_ports_range: tuple[int, int] = (5, 20)

    # Temporal patterns
    active_hours_range: tuple[int, int] = (12, 24)
    business_hours_ratio_range: tuple[float, float] = (0.4, 0.6)

    # Protocol distribution (TCP %, UDP %, rest is other)
    tcp_ratio_range: tuple[float, float] = (0.7, 0.95)
    udp_ratio_range: tuple[float, float] = (0.02, 0.2)


class SyntheticDataGenerator:
    """Generates synthetic BehavioralFeatures for building the shipped model.

    Profiles are based on:
    - Heuristic signals in heuristics.py
    - Test fixtures in tests/conftest.py
    - Real-world traffic pattern knowledge
    """

    # Asset type profiles based on characteristic traffic patterns
    PROFILES: ClassVar[dict[str, FeatureProfile]] = {
        "server": FeatureProfile(
            fan_in_range=(30, 100),
            fan_out_range=(2, 10),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(50, 500),
            bytes_per_flow_range=(500, 5000),
            listener_ports=list(WEB_PORTS | {22}),  # Web + SSH
            unique_dst_ports_range=(2, 10),
            active_hours_range=(18, 24),
            business_hours_ratio_range=(0.3, 0.5),
            tcp_ratio_range=(0.85, 0.98),
            udp_ratio_range=(0.01, 0.1),
        ),
        "workstation": FeatureProfile(
            fan_in_range=(0, 5),
            fan_out_range=(50, 150),
            inbound_flows_range=(20, 200),
            outbound_flows_range=(200, 2000),
            bytes_per_flow_range=(1000, 8000),
            listener_ports=[],  # No listeners
            unique_dst_ports_range=(20, 100),
            active_hours_range=(8, 14),
            business_hours_ratio_range=(0.7, 0.95),
            tcp_ratio_range=(0.6, 0.85),
            udp_ratio_range=(0.1, 0.3),
        ),
        "database": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(1, 5),
            inbound_flows_range=(200, 2000),
            outbound_flows_range=(20, 200),
            bytes_per_flow_range=(5000, 50000),  # Large data transfers
            listener_ports=list(DATABASE_PORTS)[:3],  # Top 3 DB ports
            unique_dst_ports_range=(1, 5),
            active_hours_range=(20, 24),
            business_hours_ratio_range=(0.4, 0.6),
            tcp_ratio_range=(0.95, 0.99),
            udp_ratio_range=(0.005, 0.03),
        ),
        "load_balancer": FeatureProfile(
            fan_in_range=(100, 500),
            fan_out_range=(5, 20),
            inbound_flows_range=(5000, 50000),
            outbound_flows_range=(5000, 50000),  # Symmetric
            bytes_per_flow_range=(500, 3000),
            listener_ports=list(LOAD_BALANCER_PORTS)[:3],
            unique_dst_ports_range=(2, 8),
            active_hours_range=(24, 24),  # Always on
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.9, 0.98),
            udp_ratio_range=(0.01, 0.08),
        ),
        "network_device": FeatureProfile(
            fan_in_range=(5, 20),
            fan_out_range=(5, 20),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(500, 5000),  # Symmetric
            bytes_per_flow_range=(100, 1000),  # Small packets
            listener_ports=list(NETWORK_DEVICE_PORTS)[:3],
            unique_dst_ports_range=(3, 15),
            active_hours_range=(24, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.3, 0.6),
            udp_ratio_range=(0.2, 0.5),  # More UDP (SNMP, etc.)
        ),
        "storage": FeatureProfile(
            fan_in_range=(10, 50),
            fan_out_range=(1, 5),
            inbound_flows_range=(500, 5000),
            outbound_flows_range=(100, 1000),
            bytes_per_flow_range=(10000, 100000),  # Large transfers
            listener_ports=list(STORAGE_PORTS)[:3],
            unique_dst_ports_range=(1, 5),
            active_hours_range=(22, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.9, 0.99),
            udp_ratio_range=(0.005, 0.05),
        ),
        "container": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(5, 30),
            inbound_flows_range=(100, 2000),
            outbound_flows_range=(100, 2000),
            bytes_per_flow_range=(500, 5000),
            listener_ports=[3000, 8000, 8080, 9000],  # Common container ports
            unique_dst_ports_range=(5, 30),
            active_hours_range=(16, 22),
            business_hours_ratio_range=(0.5, 0.7),
            tcp_ratio_range=(0.85, 0.98),
            udp_ratio_range=(0.01, 0.1),
        ),
        "cloud_service": FeatureProfile(
            fan_in_range=(200, 1000),
            fan_out_range=(1, 10),
            inbound_flows_range=(10000, 100000),
            outbound_flows_range=(1000, 10000),
            bytes_per_flow_range=(500, 3000),
            listener_ports=[443, 80],
            unique_dst_ports_range=(1, 5),
            active_hours_range=(24, 24),
            business_hours_ratio_range=(0.45, 0.55),
            tcp_ratio_range=(0.95, 0.99),
            udp_ratio_range=(0.005, 0.03),
        ),
        "virtual_machine": FeatureProfile(
            fan_in_range=(5, 30),
            fan_out_range=(5, 30),
            inbound_flows_range=(100, 2000),
            outbound_flows_range=(100, 2000),
            bytes_per_flow_range=(1000, 10000),
            listener_ports=[22, 80, 443],  # Common VM services
            unique_dst_ports_range=(5, 30),
            active_hours_range=(14, 20),
            business_hours_ratio_range=(0.5, 0.7),
            tcp_ratio_range=(0.8, 0.95),
            udp_ratio_range=(0.03, 0.15),
        ),
    }

    def __init__(self, seed: int | None = None) -> None:
        """Initialize the generator.

        Args:
            seed: Random seed for reproducibility.
        """
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.transformer = FeatureTransformer()

    def generate_sample(self, asset_type: str) -> BehavioralFeatures:
        """Generate a single synthetic sample for an asset type.

        Args:
            asset_type: One of the supported asset types.

        Returns:
            BehavioralFeatures with realistic values for the type.

        Raises:
            ValueError: If asset_type is not supported.
        """
        if asset_type not in self.PROFILES:
            raise ValueError(
                f"Unknown asset type: {asset_type}. "
                f"Supported: {list(self.PROFILES.keys())}"
            )

        profile = self.PROFILES[asset_type]
        return self._generate_from_profile(profile, asset_type)

    def generate_samples(
        self,
        asset_type: str,
        n: int,
    ) -> list[BehavioralFeatures]:
        """Generate multiple samples for an asset type.

        Args:
            asset_type: One of the supported asset types.
            n: Number of samples to generate.

        Returns:
            List of BehavioralFeatures instances.
        """
        return [self.generate_sample(asset_type) for _ in range(n)]

    def generate_balanced_dataset(
        self,
        samples_per_class: int = 200,
    ) -> TrainingDataset:
        """Generate a balanced dataset with equal samples per class.

        Args:
            samples_per_class: Number of samples per asset type.

        Returns:
            TrainingDataset with all asset types equally represented.
        """
        features_list: list[BehavioralFeatures] = []
        labels: list[str] = []

        for asset_type in self.PROFILES:
            samples = self.generate_samples(asset_type, samples_per_class)
            features_list.extend(samples)
            labels.extend([asset_type] * samples_per_class)

        logger.info(
            "Generated balanced synthetic dataset",
            samples_per_class=samples_per_class,
            total_samples=len(features_list),
            classes=list(self.PROFILES.keys()),
        )

        builder = DatasetBuilder()
        return builder.from_behavioral_features(features_list, labels)

    def _generate_from_profile(
        self,
        profile: FeatureProfile,
        asset_type: str,
    ) -> BehavioralFeatures:
        """Generate features from a profile with realistic noise.

        Args:
            profile: Feature profile to sample from.
            asset_type: Asset type name for logging.

        Returns:
            BehavioralFeatures with sampled values.
        """
        # Sample basic metrics
        fan_in = self._sample_int(profile.fan_in_range)
        fan_out = self._sample_int(profile.fan_out_range)
        inbound_flows = self._sample_int(profile.inbound_flows_range)
        outbound_flows = self._sample_int(profile.outbound_flows_range)
        bytes_per_flow = self._sample_int(profile.bytes_per_flow_range)

        # Compute byte volumes
        inbound_bytes = inbound_flows * bytes_per_flow
        outbound_bytes = outbound_flows * bytes_per_flow

        # Sample temporal patterns
        active_hours = self._sample_int(profile.active_hours_range)
        business_hours_ratio = self._sample_float(profile.business_hours_ratio_range)

        # Sample port diversity
        unique_dst_ports = self._sample_int(profile.unique_dst_ports_range)

        # Generate protocol distribution
        tcp_ratio = self._sample_float(profile.tcp_ratio_range)
        udp_ratio = self._sample_float(profile.udp_ratio_range)

        # Ensure ratios sum to <= 1
        if tcp_ratio + udp_ratio > 0.99:
            udp_ratio = 0.99 - tcp_ratio

        total_flows = inbound_flows + outbound_flows
        tcp_flows = int(total_flows * tcp_ratio)
        udp_flows = int(total_flows * udp_ratio)
        other_flows = total_flows - tcp_flows - udp_flows

        protocol_distribution = {
            6: tcp_flows,   # TCP
            17: udp_flows,  # UDP
            1: max(0, other_flows),  # ICMP/other
        }

        # Determine listener ports (with some variation)
        listener_ports = profile.listener_ports.copy()
        if listener_ports and self.rng.random() < 0.3:
            # 30% chance to add a random extra port
            extra_port = self.rng.choice([8080, 8443, 3000, 5000, 9000])
            if extra_port not in listener_ports:
                listener_ports.append(extra_port)

        # Compute derived metrics
        total_connections = fan_in + fan_out
        fan_in_ratio = fan_in / total_connections if total_connections > 0 else 0.5

        # Well-known port ratio based on listener ports
        if listener_ports:
            well_known_count = sum(1 for p in listener_ports if p < 1024)
            well_known_port_ratio = well_known_count / len(listener_ports)
        else:
            well_known_port_ratio = 0.0

        # Ephemeral port ratio (inverse correlation with being a server)
        ephemeral_port_ratio = max(0.0, 1.0 - well_known_port_ratio - 0.2)

        # Compute traffic variance (servers tend to have lower variance)
        if active_hours >= 22:
            traffic_variance = self._sample_float((0.1, 0.3))  # Stable 24x7
        elif active_hours >= 16:
            traffic_variance = self._sample_float((0.3, 0.5))  # Some variation
        else:
            traffic_variance = self._sample_float((0.5, 0.8))  # Business hours only

        return BehavioralFeatures(
            ip_address=f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}/32",
            window_size="5min",
            computed_at=datetime.now(timezone.utc),
            inbound_flows=inbound_flows,
            outbound_flows=outbound_flows,
            inbound_bytes=inbound_bytes,
            outbound_bytes=outbound_bytes,
            fan_in_count=fan_in,
            fan_out_count=fan_out,
            fan_in_ratio=fan_in_ratio,
            unique_dst_ports=unique_dst_ports,
            unique_src_ports=len(listener_ports),
            well_known_port_ratio=well_known_port_ratio,
            ephemeral_port_ratio=ephemeral_port_ratio,
            persistent_listener_ports=listener_ports,
            protocol_distribution=protocol_distribution,
            total_flows=total_flows,
            active_hours_count=active_hours,
            business_hours_ratio=business_hours_ratio,
            traffic_variance=traffic_variance,
            has_db_ports=bool(set(listener_ports) & DATABASE_PORTS),
            has_storage_ports=bool(set(listener_ports) & STORAGE_PORTS),
            has_web_ports=bool(set(listener_ports) & WEB_PORTS),
            has_ssh_ports=22 in listener_ports,
        )

    def _sample_int(self, range_tuple: tuple[int, int]) -> int:
        """Sample an integer uniformly from a range."""
        return self.rng.randint(range_tuple[0], range_tuple[1])

    def _sample_float(self, range_tuple: tuple[float, float]) -> float:
        """Sample a float uniformly from a range."""
        return self.rng.uniform(range_tuple[0], range_tuple[1])
