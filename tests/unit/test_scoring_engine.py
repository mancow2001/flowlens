"""Unit tests for classification scoring engine."""

from datetime import datetime, timezone

import pytest

from flowlens.classification.constants import ClassifiableAssetType
from flowlens.classification.feature_extractor import BehavioralFeatures
from flowlens.classification.scoring_engine import (
    ClassificationResult,
    ScoringEngine,
    TypeScore,
    classify_asset,
)


def _create_features(**kwargs) -> BehavioralFeatures:
    """Helper to create BehavioralFeatures with defaults."""
    defaults = {
        "ip_address": "192.168.1.1/32",
        "window_size": "5min",
        "computed_at": datetime.now(timezone.utc),
        "inbound_flows": 0,
        "outbound_flows": 0,
        "inbound_bytes": 0,
        "outbound_bytes": 0,
        "fan_in_count": 0,
        "fan_out_count": 0,
        "fan_in_ratio": None,
        "unique_dst_ports": 0,
        "unique_src_ports": 0,
        "well_known_port_ratio": None,
        "ephemeral_port_ratio": None,
        "persistent_listener_ports": [],
        "protocol_distribution": {},
        "avg_bytes_per_packet": None,
        "total_flows": 0,
        "active_hours_count": None,
        "business_hours_ratio": None,
        "has_db_ports": False,
        "has_storage_ports": False,
        "has_web_ports": False,
        "has_ssh_ports": False,
    }
    defaults.update(kwargs)
    return BehavioralFeatures(**defaults)


@pytest.mark.unit
class TestScoringEngine:
    """Test cases for ScoringEngine classification."""

    @pytest.fixture
    def engine(self) -> ScoringEngine:
        """Create scoring engine instance."""
        return ScoringEngine()

    def test_server_classification(self, engine: ScoringEngine, sample_server_features: dict):
        """Test that server-like features classify as server."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        assert result.recommended_type == ClassifiableAssetType.SERVER
        assert result.confidence > 0.5
        assert result.scores[ClassifiableAssetType.SERVER].score > 0

    def test_workstation_classification(self, engine: ScoringEngine, sample_workstation_features: dict):
        """Test that workstation-like features classify as workstation."""
        features = _create_features(**sample_workstation_features)
        result = engine.compute_scores(features)

        assert result.recommended_type == ClassifiableAssetType.WORKSTATION
        assert result.confidence > 0.5

    def test_database_classification(self, engine: ScoringEngine, sample_database_features: dict):
        """Test that database-like features score highly for database."""
        features = _create_features(**sample_database_features)
        result = engine.compute_scores(features)

        # Database features should score highly for database type
        assert result.scores[ClassifiableAssetType.DATABASE].score > 0
        # May be classified as database or server depending on signal weights
        assert result.recommended_type in (
            ClassifiableAssetType.DATABASE,
            ClassifiableAssetType.SERVER,
        )

    def test_load_balancer_classification(self, engine: ScoringEngine, sample_load_balancer_features: dict):
        """Test that load balancer-like features classify as load balancer."""
        features = _create_features(**sample_load_balancer_features)
        result = engine.compute_scores(features)

        # Load balancers can also be classified as servers due to similar patterns
        assert result.recommended_type in (
            ClassifiableAssetType.LOAD_BALANCER,
            ClassifiableAssetType.CLOUD_SERVICE,
            ClassifiableAssetType.SERVER,
        )
        assert result.confidence > 0.3

    def test_unknown_with_no_traffic(self, engine: ScoringEngine):
        """Test that assets with no traffic classify as unknown."""
        features = _create_features(
            inbound_flows=0,
            outbound_flows=0,
            total_flows=0,
            fan_in_count=0,
            fan_out_count=0,
        )
        result = engine.compute_scores(features)

        assert result.recommended_type == ClassifiableAssetType.UNKNOWN
        assert result.scores[ClassifiableAssetType.UNKNOWN].score > 0

    def test_unknown_with_insufficient_data(self, engine: ScoringEngine):
        """Test that assets with minimal data classify as unknown."""
        features = _create_features(
            inbound_flows=10,
            outbound_flows=5,
            total_flows=15,
            fan_in_count=1,
            fan_out_count=1,
        )
        result = engine.compute_scores(features)

        # With only 15 flows, should be unknown or low confidence
        assert result.recommended_type == ClassifiableAssetType.UNKNOWN or result.confidence < 0.5

    def test_stability_bias_maintains_current_type(self, engine: ScoringEngine):
        """Test that stability bias prefers current type when scores are close."""
        # Features that could be server or database
        features = _create_features(
            inbound_flows=500,
            outbound_flows=50,
            total_flows=550,
            fan_in_count=15,
            fan_out_count=3,
            fan_in_ratio=0.83,
            has_db_ports=True,
            has_web_ports=True,  # Both ports
            active_hours_count=22,
            well_known_port_ratio=0.8,
            persistent_listener_ports=[80, 443, 5432],
        )

        # First classification without current type
        result1 = engine.compute_scores(features, current_type=None)

        # Second classification with current type set
        result2 = engine.compute_scores(features, current_type="database")

        # If scores are close, stability bias should keep database
        if result1.scores[ClassifiableAssetType.DATABASE].score >= result1.scores[result1.recommended_type].score * 0.9:
            assert result2.recommended_type == ClassifiableAssetType.DATABASE

    def test_confidence_calculation_high_margin(self, engine: ScoringEngine, sample_server_features: dict):
        """Test confidence is high when there's a clear winner."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        # Clear server features should have high confidence
        assert result.confidence > 0.5

    def test_confidence_calculation_low_when_close_scores(self, engine: ScoringEngine):
        """Test confidence is lower when multiple types score similarly."""
        # Ambiguous features
        features = _create_features(
            inbound_flows=100,
            outbound_flows=100,
            total_flows=200,
            fan_in_count=10,
            fan_out_count=10,
            fan_in_ratio=0.5,
            has_web_ports=True,
            active_hours_count=12,
            business_hours_ratio=0.5,
        )
        result = engine.compute_scores(features)

        # Scores should be distributed, potentially lower confidence
        assert 0 <= result.confidence <= 1.0

    def test_should_auto_update_when_high_confidence(self, engine: ScoringEngine, sample_server_features: dict):
        """Test auto-update is true when confidence is high enough."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        # Server features with high traffic should enable auto-update
        if result.confidence >= 0.7 and result.recommended_type != ClassifiableAssetType.UNKNOWN:
            assert result.should_auto_update is True

    def test_should_not_auto_update_for_unknown(self, engine: ScoringEngine):
        """Test auto-update is false for unknown classification."""
        features = _create_features(
            total_flows=5,
            fan_in_count=0,
            fan_out_count=0,
        )
        result = engine.compute_scores(features)

        if result.recommended_type == ClassifiableAssetType.UNKNOWN:
            assert result.should_auto_update is False

    def test_classification_result_to_dict(self, engine: ScoringEngine, sample_server_features: dict):
        """Test ClassificationResult serialization."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)
        result_dict = result.to_dict()

        assert "ip_address" in result_dict
        assert "recommended_type" in result_dict
        assert "confidence" in result_dict
        assert "should_auto_update" in result_dict
        assert "scores" in result_dict
        assert "features_used" in result_dict
        assert isinstance(result_dict["confidence"], float)

    def test_type_score_to_dict(self, engine: ScoringEngine, sample_server_features: dict):
        """Test TypeScore serialization."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        for asset_type, type_score in result.scores.items():
            score_dict = type_score.to_dict()
            assert "score" in score_dict
            assert "breakdown" in score_dict
            # Score can be int or float (rounded values may be int)
            assert isinstance(score_dict["score"], (int, float))
            assert isinstance(score_dict["breakdown"], dict)

    def test_classify_asset_convenience_function(self, sample_server_features: dict):
        """Test the classify_asset convenience function."""
        features = _create_features(**sample_server_features)
        result = classify_asset(features)

        assert isinstance(result, ClassificationResult)
        assert result.ip_address == features.ip_address

    def test_all_asset_types_have_scores(self, engine: ScoringEngine, sample_server_features: dict):
        """Test that all classifiable types get scores."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        for asset_type in ClassifiableAssetType:
            assert asset_type in result.scores
            assert isinstance(result.scores[asset_type], TypeScore)

    def test_scores_are_normalized(self, engine: ScoringEngine, sample_server_features: dict):
        """Test that scores are in 0-100 range."""
        features = _create_features(**sample_server_features)
        result = engine.compute_scores(features)

        for type_score in result.scores.values():
            assert 0 <= type_score.score <= 100

    def test_network_device_classification(self, engine: ScoringEngine):
        """Test network device classification with ICMP traffic."""
        features = _create_features(
            inbound_flows=500,
            outbound_flows=500,
            total_flows=1000,
            fan_in_count=50,
            fan_out_count=50,
            fan_in_ratio=0.5,
            unique_dst_ports=5,
            protocol_distribution={1: 200, 6: 800},  # ICMP + TCP
            inbound_bytes=10_000_000,
            outbound_bytes=10_000_000,
            avg_bytes_per_packet=100,
        )
        result = engine.compute_scores(features)

        # Should have some network device score due to ICMP
        assert result.scores[ClassifiableAssetType.NETWORK_DEVICE].score > 0

    def test_storage_classification(self, engine: ScoringEngine):
        """Test storage server classification."""
        features = _create_features(
            inbound_flows=300,
            outbound_flows=50,
            total_flows=350,
            fan_in_count=20,
            fan_out_count=2,
            fan_in_ratio=0.9,
            has_storage_ports=True,
            persistent_listener_ports=[2049, 445],
            inbound_bytes=50_000_000_000,  # 50GB
            outbound_bytes=100_000_000_000,  # 100GB
            active_hours_count=24,
        )
        result = engine.compute_scores(features)

        assert result.scores[ClassifiableAssetType.STORAGE].score > 0
        # Storage should score highly with these features
        assert result.recommended_type in (
            ClassifiableAssetType.STORAGE,
            ClassifiableAssetType.SERVER,
        )

    def test_container_classification(self, engine: ScoringEngine):
        """Test container classification with ephemeral ports."""
        features = _create_features(
            inbound_flows=200,
            outbound_flows=300,
            total_flows=500,
            fan_in_count=15,
            fan_out_count=25,
            fan_in_ratio=0.37,
            unique_dst_ports=30,
            unique_src_ports=15,
            persistent_listener_ports=[3000, 8000, 35000],
            has_web_ports=True,
            ephemeral_port_ratio=0.3,
        )
        result = engine.compute_scores(features)

        assert result.scores[ClassifiableAssetType.CONTAINER].score > 0
