"""Feature transformer for ML classification.

Transforms BehavioralFeatures into ML-ready numpy arrays with
appropriate normalization and encoding.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

if TYPE_CHECKING:
    from flowlens.classification.feature_extractor import BehavioralFeatures


class FeatureTransformer:
    """Transform BehavioralFeatures to ML-ready feature vectors.

    Applies:
    - Log transformation for count features (handles wide ranges)
    - Normalization for ratios (already 0-1)
    - Binary encoding for boolean flags
    - Protocol distribution extraction
    """

    # Feature column names in order
    FEATURE_COLUMNS: ClassVar[list[str]] = [
        # Traffic features (log-transformed)
        "inbound_flows_log",
        "outbound_flows_log",
        "inbound_bytes_log",
        "outbound_bytes_log",
        "fan_in_count_log",
        "fan_out_count_log",
        "total_flows_log",

        # Ratio features (already normalized 0-1)
        "fan_in_ratio",
        "well_known_port_ratio",
        "ephemeral_port_ratio",
        "business_hours_ratio",

        # Port diversity (log-transformed)
        "unique_dst_ports_log",
        "unique_src_ports_log",

        # Temporal features
        "active_hours_normalized",  # 0-24 -> 0-1
        "traffic_variance",

        # Boolean flags - existing (0 or 1)
        "has_db_ports",
        "has_storage_ports",
        "has_web_ports",
        "has_ssh_ports",

        # Boolean flags - network services
        "has_dns_ports",
        "has_dhcp_ports",
        "has_ntp_ports",
        "has_directory_ports",

        # Boolean flags - communication
        "has_mail_ports",
        "has_voip_ports",

        # Boolean flags - security & access
        "has_vpn_ports",
        "has_proxy_ports",
        "has_log_collector_ports",
        "has_remote_access_ports",

        # Boolean flags - endpoints
        "has_printer_ports",
        "has_iot_ports",
        "has_camera_ports",

        # Boolean flags - app infrastructure
        "has_message_queue_ports",
        "has_monitoring_ports",

        # Protocol ratios
        "tcp_ratio",
        "udp_ratio",
        "icmp_ratio",

        # Derived metrics
        "bytes_per_flow_log",
        "inbound_outbound_ratio",
    ]

    def __init__(self) -> None:
        """Initialize the feature transformer."""
        self._feature_count = len(self.FEATURE_COLUMNS)

    @property
    def feature_count(self) -> int:
        """Return the number of features produced."""
        return self._feature_count

    @property
    def feature_names(self) -> list[str]:
        """Return the feature column names."""
        return self.FEATURE_COLUMNS.copy()

    def transform(self, features: BehavioralFeatures) -> np.ndarray:
        """Convert BehavioralFeatures to a feature vector.

        Args:
            features: Behavioral features extracted from flow data.

        Returns:
            1D numpy array of transformed features.
        """
        vector = np.zeros(self._feature_count, dtype=np.float32)

        # Traffic features (log1p to handle zeros)
        vector[0] = self._log_transform(features.inbound_flows)
        vector[1] = self._log_transform(features.outbound_flows)
        vector[2] = self._log_transform(features.inbound_bytes)
        vector[3] = self._log_transform(features.outbound_bytes)
        vector[4] = self._log_transform(features.fan_in_count)
        vector[5] = self._log_transform(features.fan_out_count)
        vector[6] = self._log_transform(features.total_flows)

        # Ratio features (0-1 range, default to 0.5 if None)
        vector[7] = features.fan_in_ratio if features.fan_in_ratio is not None else 0.5
        vector[8] = features.well_known_port_ratio if features.well_known_port_ratio is not None else 0.5
        vector[9] = features.ephemeral_port_ratio if features.ephemeral_port_ratio is not None else 0.5
        vector[10] = features.business_hours_ratio if features.business_hours_ratio is not None else 0.5

        # Port diversity
        vector[11] = self._log_transform(features.unique_dst_ports)
        vector[12] = self._log_transform(features.unique_src_ports)

        # Temporal features
        active_hours = features.active_hours_count if features.active_hours_count is not None else 12
        vector[13] = active_hours / 24.0  # Normalize to 0-1
        vector[14] = features.traffic_variance if features.traffic_variance is not None else 0.5

        # Boolean flags - existing
        vector[15] = 1.0 if features.has_db_ports else 0.0
        vector[16] = 1.0 if features.has_storage_ports else 0.0
        vector[17] = 1.0 if features.has_web_ports else 0.0
        vector[18] = 1.0 if features.has_ssh_ports else 0.0

        # Boolean flags - network services
        vector[19] = 1.0 if features.has_dns_ports else 0.0
        vector[20] = 1.0 if features.has_dhcp_ports else 0.0
        vector[21] = 1.0 if features.has_ntp_ports else 0.0
        vector[22] = 1.0 if features.has_directory_ports else 0.0

        # Boolean flags - communication
        vector[23] = 1.0 if features.has_mail_ports else 0.0
        vector[24] = 1.0 if features.has_voip_ports else 0.0

        # Boolean flags - security & access
        vector[25] = 1.0 if features.has_vpn_ports else 0.0
        vector[26] = 1.0 if features.has_proxy_ports else 0.0
        vector[27] = 1.0 if features.has_log_collector_ports else 0.0
        vector[28] = 1.0 if features.has_remote_access_ports else 0.0

        # Boolean flags - endpoints
        vector[29] = 1.0 if features.has_printer_ports else 0.0
        vector[30] = 1.0 if features.has_iot_ports else 0.0
        vector[31] = 1.0 if features.has_camera_ports else 0.0

        # Boolean flags - app infrastructure
        vector[32] = 1.0 if features.has_message_queue_ports else 0.0
        vector[33] = 1.0 if features.has_monitoring_ports else 0.0

        # Protocol ratios from distribution
        total_protocol_flows = sum(features.protocol_distribution.values()) if features.protocol_distribution else 0
        if total_protocol_flows > 0:
            vector[34] = features.protocol_distribution.get(6, 0) / total_protocol_flows  # TCP
            vector[35] = features.protocol_distribution.get(17, 0) / total_protocol_flows  # UDP
            icmp_flows = features.protocol_distribution.get(1, 0) + features.protocol_distribution.get(58, 0)
            vector[36] = icmp_flows / total_protocol_flows  # ICMP + ICMPv6
        else:
            vector[34] = 0.8  # Default assume mostly TCP
            vector[35] = 0.15
            vector[36] = 0.05

        # Derived metrics
        total_bytes = features.inbound_bytes + features.outbound_bytes
        total_flows = features.total_flows if features.total_flows > 0 else 1
        vector[37] = self._log_transform(total_bytes / total_flows)  # bytes per flow

        total_traffic = features.inbound_flows + features.outbound_flows
        if total_traffic > 0:
            vector[38] = features.inbound_flows / total_traffic  # inbound ratio
        else:
            vector[38] = 0.5

        return vector

    def transform_batch(self, features_list: list[BehavioralFeatures]) -> np.ndarray:
        """Batch transform multiple BehavioralFeatures instances.

        Args:
            features_list: List of behavioral features.

        Returns:
            2D numpy array of shape (n_samples, n_features).
        """
        if not features_list:
            return np.empty((0, self._feature_count), dtype=np.float32)

        return np.vstack([self.transform(f) for f in features_list])

    def transform_dict(self, features_dict: dict[str, Any]) -> np.ndarray:
        """Transform a dictionary of features (e.g., from JSON/database).

        Args:
            features_dict: Dictionary with feature values.

        Returns:
            1D numpy array of transformed features.
        """
        vector = np.zeros(self._feature_count, dtype=np.float32)

        # Traffic features
        vector[0] = self._log_transform(features_dict.get("inbound_flows", 0))
        vector[1] = self._log_transform(features_dict.get("outbound_flows", 0))
        vector[2] = self._log_transform(features_dict.get("inbound_bytes", 0))
        vector[3] = self._log_transform(features_dict.get("outbound_bytes", 0))
        vector[4] = self._log_transform(features_dict.get("fan_in_count", 0))
        vector[5] = self._log_transform(features_dict.get("fan_out_count", 0))
        vector[6] = self._log_transform(features_dict.get("total_flows", 0))

        # Ratio features
        vector[7] = features_dict.get("fan_in_ratio") or 0.5
        vector[8] = features_dict.get("well_known_port_ratio") or 0.5
        vector[9] = features_dict.get("ephemeral_port_ratio") or 0.5
        vector[10] = features_dict.get("business_hours_ratio") or 0.5

        # Port diversity
        vector[11] = self._log_transform(features_dict.get("unique_dst_ports", 0))
        vector[12] = self._log_transform(features_dict.get("unique_src_ports", 0))

        # Temporal
        active_hours = features_dict.get("active_hours_count") or 12
        vector[13] = active_hours / 24.0
        vector[14] = features_dict.get("traffic_variance") or 0.5

        # Boolean flags - existing
        vector[15] = 1.0 if features_dict.get("has_db_ports") else 0.0
        vector[16] = 1.0 if features_dict.get("has_storage_ports") else 0.0
        vector[17] = 1.0 if features_dict.get("has_web_ports") else 0.0
        vector[18] = 1.0 if features_dict.get("has_ssh_ports") else 0.0

        # Boolean flags - network services
        vector[19] = 1.0 if features_dict.get("has_dns_ports") else 0.0
        vector[20] = 1.0 if features_dict.get("has_dhcp_ports") else 0.0
        vector[21] = 1.0 if features_dict.get("has_ntp_ports") else 0.0
        vector[22] = 1.0 if features_dict.get("has_directory_ports") else 0.0

        # Boolean flags - communication
        vector[23] = 1.0 if features_dict.get("has_mail_ports") else 0.0
        vector[24] = 1.0 if features_dict.get("has_voip_ports") else 0.0

        # Boolean flags - security & access
        vector[25] = 1.0 if features_dict.get("has_vpn_ports") else 0.0
        vector[26] = 1.0 if features_dict.get("has_proxy_ports") else 0.0
        vector[27] = 1.0 if features_dict.get("has_log_collector_ports") else 0.0
        vector[28] = 1.0 if features_dict.get("has_remote_access_ports") else 0.0

        # Boolean flags - endpoints
        vector[29] = 1.0 if features_dict.get("has_printer_ports") else 0.0
        vector[30] = 1.0 if features_dict.get("has_iot_ports") else 0.0
        vector[31] = 1.0 if features_dict.get("has_camera_ports") else 0.0

        # Boolean flags - app infrastructure
        vector[32] = 1.0 if features_dict.get("has_message_queue_ports") else 0.0
        vector[33] = 1.0 if features_dict.get("has_monitoring_ports") else 0.0

        # Protocol distribution
        protocol_dist = features_dict.get("protocol_distribution", {})
        total_protocol_flows = sum(protocol_dist.values()) if protocol_dist else 0
        if total_protocol_flows > 0:
            vector[34] = protocol_dist.get(6, protocol_dist.get("6", 0)) / total_protocol_flows
            vector[35] = protocol_dist.get(17, protocol_dist.get("17", 0)) / total_protocol_flows
            icmp = protocol_dist.get(1, protocol_dist.get("1", 0)) + protocol_dist.get(58, protocol_dist.get("58", 0))
            vector[36] = icmp / total_protocol_flows
        else:
            vector[34] = 0.8
            vector[35] = 0.15
            vector[36] = 0.05

        # Derived
        total_bytes = features_dict.get("inbound_bytes", 0) + features_dict.get("outbound_bytes", 0)
        total_flows = features_dict.get("total_flows", 1) or 1
        vector[37] = self._log_transform(total_bytes / total_flows)

        inbound = features_dict.get("inbound_flows", 0)
        outbound = features_dict.get("outbound_flows", 0)
        total = inbound + outbound
        vector[38] = inbound / total if total > 0 else 0.5

        return vector

    @staticmethod
    def _log_transform(value: float | int) -> float:
        """Apply log1p transformation (handles zeros gracefully).

        Args:
            value: Raw value to transform.

        Returns:
            Log-transformed value.
        """
        if value is None or value < 0:
            return 0.0
        return math.log1p(float(value))
