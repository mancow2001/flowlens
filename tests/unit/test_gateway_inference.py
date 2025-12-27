"""Unit tests for gateway inference service."""

from datetime import datetime, timedelta, timezone

import pytest

from flowlens.resolution.gateway_inference import GatewayCandidate, GatewayInferenceService


@pytest.mark.unit
class TestGatewayCandidate:
    """Test cases for GatewayCandidate dataclass."""

    def test_create_gateway_candidate(self, sample_gateway_candidate: dict):
        """Test creating a gateway candidate."""
        candidate = GatewayCandidate(**sample_gateway_candidate)

        assert candidate.source_ip == "192.168.1.100"
        assert candidate.gateway_ip == "192.168.1.1"
        assert candidate.bytes_total == 5_000_000
        assert candidate.flows_total == 500
        assert candidate.observation_count == 100

    def test_candidate_time_span(self, sample_gateway_candidate: dict):
        """Test candidate time span calculation."""
        candidate = GatewayCandidate(**sample_gateway_candidate)
        time_span = (candidate.last_seen - candidate.first_seen).total_seconds()

        assert time_span > 0  # 7 days


@pytest.mark.unit
class TestGatewayInferenceService:
    """Test cases for GatewayInferenceService."""

    @pytest.fixture
    def service(self) -> GatewayInferenceService:
        """Create gateway inference service instance."""
        return GatewayInferenceService()

    def test_service_initialization(self, service: GatewayInferenceService):
        """Test service initializes with correct defaults."""
        assert service.MIN_FLOWS_FOR_CONFIDENCE == 10
        assert service.MIN_OBSERVATIONS_FOR_CONFIDENCE == 3
        assert service.HIGH_CONFIDENCE_THRESHOLD == 0.8
        assert service.AUTO_CREATE_THRESHOLD == 0.6

    def test_calculate_confidence_high_values(self, service: GatewayInferenceService):
        """Test confidence calculation with high values."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=10_000_000,  # 10MB
            flows_total=500,
            first_seen=now - timedelta(days=7),
            last_seen=now,
            observation_count=50,
        )

        confidence, scores = service._calculate_confidence(candidate)

        assert 0 <= confidence <= 1.0
        assert "flow_count" in scores
        assert "observation_count" in scores
        assert "time_consistency" in scores
        assert "bytes_volume" in scores
        # High values should give high confidence
        assert confidence > 0.5

    def test_calculate_confidence_low_values(self, service: GatewayInferenceService):
        """Test confidence calculation with low values."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=1000,  # Very low
            flows_total=5,  # Very low
            first_seen=now - timedelta(minutes=5),
            last_seen=now,
            observation_count=1,
        )

        confidence, scores = service._calculate_confidence(candidate)

        assert 0 <= confidence <= 1.0
        # Low values should give low confidence
        assert confidence < 0.5

    def test_calculate_confidence_score_components(self, service: GatewayInferenceService):
        """Test that confidence score components are properly weighted."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=1_000_000,
            flows_total=100,
            first_seen=now - timedelta(days=1),
            last_seen=now,
            observation_count=10,
        )

        confidence, scores = service._calculate_confidence(candidate)

        # Check weights are applied correctly
        # flow_count: 0.30, observation_count: 0.30, time_consistency: 0.20, bytes_volume: 0.20
        total_from_scores = sum(scores.values())
        assert abs(confidence - total_from_scores) < 0.01

    def test_calculate_confidence_max_values(self, service: GatewayInferenceService):
        """Test confidence with max possible values."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=100_000_000,  # 100MB
            flows_total=1000,  # Very high
            first_seen=now - timedelta(days=30),  # Long observation
            last_seen=now,
            observation_count=100,  # Many observations
        )

        confidence, scores = service._calculate_confidence(candidate)

        # Max values should approach 1.0
        assert confidence >= 0.9

    def test_calculate_confidence_zero_flows(self, service: GatewayInferenceService):
        """Test confidence with zero flows."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=0,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )

        confidence, scores = service._calculate_confidence(candidate)

        assert confidence == 0.0

    def test_confidence_flow_count_factor(self, service: GatewayInferenceService):
        """Test flow count factor calculation."""
        now = datetime.now(timezone.utc)

        # Low flows
        candidate_low = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=10,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )
        _, scores_low = service._calculate_confidence(candidate_low)

        # High flows
        candidate_high = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=200,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )
        _, scores_high = service._calculate_confidence(candidate_high)

        # Higher flows should give higher score
        assert scores_high["flow_count"] > scores_low["flow_count"]

    def test_confidence_observation_count_factor(self, service: GatewayInferenceService):
        """Test observation count factor calculation."""
        now = datetime.now(timezone.utc)

        # Few observations
        candidate_few = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=0,
            first_seen=now,
            last_seen=now,
            observation_count=2,
        )
        _, scores_few = service._calculate_confidence(candidate_few)

        # Many observations
        candidate_many = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=0,
            first_seen=now,
            last_seen=now,
            observation_count=20,
        )
        _, scores_many = service._calculate_confidence(candidate_many)

        # More observations should give higher score
        assert scores_many["observation_count"] > scores_few["observation_count"]

    def test_confidence_time_consistency_factor(self, service: GatewayInferenceService):
        """Test time consistency factor calculation."""
        now = datetime.now(timezone.utc)

        # Short time span
        candidate_short = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=0,
            first_seen=now - timedelta(hours=1),
            last_seen=now,
            observation_count=0,
        )
        _, scores_short = service._calculate_confidence(candidate_short)

        # Long time span
        candidate_long = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=0,
            flows_total=0,
            first_seen=now - timedelta(days=7),
            last_seen=now,
            observation_count=0,
        )
        _, scores_long = service._calculate_confidence(candidate_long)

        # Longer time span should give higher score
        assert scores_long["time_consistency"] > scores_short["time_consistency"]

    def test_confidence_bytes_volume_factor(self, service: GatewayInferenceService):
        """Test bytes volume factor calculation."""
        now = datetime.now(timezone.utc)

        # Low bytes
        candidate_low = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=10000,
            flows_total=0,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )
        _, scores_low = service._calculate_confidence(candidate_low)

        # High bytes
        candidate_high = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=10_000_000,
            flows_total=0,
            first_seen=now,
            last_seen=now,
            observation_count=0,
        )
        _, scores_high = service._calculate_confidence(candidate_high)

        # More bytes should give higher score
        assert scores_high["bytes_volume"] > scores_low["bytes_volume"]

    def test_clear_cache(self, service: GatewayInferenceService):
        """Test cache clearing."""
        # Manually add to cache
        from uuid import uuid4
        service._asset_cache["192.168.1.1"] = uuid4()
        service._asset_cache["192.168.1.2"] = uuid4()

        assert len(service._asset_cache) == 2

        service.clear_cache()

        assert len(service._asset_cache) == 0

    def test_confidence_handles_decimal_types(self, service: GatewayInferenceService):
        """Test confidence calculation handles Decimal types from PostgreSQL."""
        from decimal import Decimal
        now = datetime.now(timezone.utc)

        # Simulate PostgreSQL returning Decimal types
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=Decimal("5000000"),
            flows_total=Decimal("500"),
            first_seen=now - timedelta(days=1),
            last_seen=now,
            observation_count=Decimal("10"),
        )

        # Should not raise an error
        confidence, scores = service._calculate_confidence(candidate)

        assert 0 <= confidence <= 1.0
        assert all(isinstance(v, float) for v in scores.values())

    def test_below_auto_create_threshold_not_created(self, service: GatewayInferenceService):
        """Test that candidates below threshold are not auto-created."""
        now = datetime.now(timezone.utc)
        candidate = GatewayCandidate(
            source_ip="192.168.1.100",
            gateway_ip="192.168.1.1",
            bytes_total=100,
            flows_total=2,
            first_seen=now,
            last_seen=now,
            observation_count=1,
        )

        confidence, _ = service._calculate_confidence(candidate)

        # Should be below auto-create threshold
        assert confidence < service.AUTO_CREATE_THRESHOLD
