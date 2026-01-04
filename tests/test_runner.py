"""Tests for the simulation runner."""

from pathlib import Path

import pytest

from src.engines.abstract_engine import AbstractLSPEngine
from src.engines.passthrough_engine import PassthroughEngine
from src.models import Transaction
from src.simulation.runner import SimulationResult, SimulationRunner


TRAFFIC_CSV_PATH = Path("data/traffic_seed.csv")
SATS_PER_BTC = 100_000_000
EXPECTED_TOTAL_BTC = 3.67  # Expected total volume from seed data
BTC_TOLERANCE = 0.05  # Allow 5% tolerance for volume matching


class MockAlternatingFailureEngine(AbstractLSPEngine):
    """Mock engine that fails every other transaction."""

    def __init__(self) -> None:
        self._call_count = 0

    def process_transaction(self, tx: Transaction) -> bool:
        """Returns True for even calls, False for odd calls."""
        self._call_count += 1
        return self._call_count % 2 == 1  # Odd calls succeed (1st, 3rd, etc.)

    def get_current_tvl(self) -> float:
        """Returns 0.0 - no TVL tracking."""
        return 0.0

    def get_name(self) -> str:
        """Returns mock engine name."""
        return "MockAlternatingFailure"


class TestSimulationRunnerHappyPath:
    """Tests for successful simulation runs."""

    @pytest.fixture
    def passthrough_runner(self) -> SimulationRunner:
        """Create a runner with PassthroughEngine."""
        engine = PassthroughEngine()
        return SimulationRunner(TRAFFIC_CSV_PATH, engine)

    def test_runner_happy_path(self, passthrough_runner: SimulationRunner) -> None:
        """Assert 100% success rate and correct total volume with PassthroughEngine."""
        result = passthrough_runner.run()

        # Verify 100% success rate
        assert result.success_rate == 1.0, (
            f"Expected 100% success rate, got {result.success_rate * 100:.2f}%"
        )
        assert result.tx_failure_count == 0, (
            f"Expected 0 failures, got {result.tx_failure_count}"
        )

        # Verify total volume matches expected ~3.67 BTC
        total_btc = result.total_volume_processed / SATS_PER_BTC
        lower_bound = EXPECTED_TOTAL_BTC * (1 - BTC_TOLERANCE)
        upper_bound = EXPECTED_TOTAL_BTC * (1 + BTC_TOLERANCE)

        assert lower_bound <= total_btc <= upper_bound, (
            f"Expected ~{EXPECTED_TOTAL_BTC} BTC, got {total_btc:.4f} BTC"
        )

        # Verify no failed volume
        assert result.total_volume_failed == 0, (
            f"Expected 0 failed volume, got {result.total_volume_failed}"
        )

    def test_runner_engine_name(self, passthrough_runner: SimulationRunner) -> None:
        """Assert engine name is correctly recorded."""
        result = passthrough_runner.run()
        assert result.engine_name == "Passthrough"

    def test_runner_tvl_history_populated(self, passthrough_runner: SimulationRunner) -> None:
        """Assert TVL history is populated with timestamps."""
        result = passthrough_runner.run()

        assert len(result.tvl_history) > 0, "TVL history should not be empty"
        assert len(result.tvl_history) == result.total_transactions, (
            "TVL history should have one entry per transaction"
        )

        # Verify each entry is a (timestamp, tvl) tuple
        for timestamp, tvl in result.tvl_history:
            assert isinstance(timestamp, float), "Timestamp should be a float"
            assert isinstance(tvl, float), "TVL should be a float"


class TestSimulationRunnerFailureTracking:
    """Tests for failure tracking in simulation runs."""

    def test_runner_failure_tracking(self) -> None:
        """Assert 50% failure rate when engine fails every other transaction."""
        engine = MockAlternatingFailureEngine()
        runner = SimulationRunner(TRAFFIC_CSV_PATH, engine)

        result = runner.run()

        # With alternating failures, we expect approximately 50% success rate
        # First transaction succeeds, second fails, etc.
        # For N transactions: ceil(N/2) succeed, floor(N/2) fail
        expected_success = (result.total_transactions + 1) // 2
        expected_failure = result.total_transactions // 2

        assert result.tx_success_count == expected_success, (
            f"Expected {expected_success} successes, got {result.tx_success_count}"
        )
        assert result.tx_failure_count == expected_failure, (
            f"Expected {expected_failure} failures, got {result.tx_failure_count}"
        )

        # Verify the rate is approximately 50%
        assert 0.49 <= result.success_rate <= 0.51, (
            f"Expected ~50% success rate, got {result.success_rate * 100:.2f}%"
        )

    def test_runner_failed_volume_tracked(self) -> None:
        """Assert failed transaction volumes are correctly tracked."""
        engine = MockAlternatingFailureEngine()
        runner = SimulationRunner(TRAFFIC_CSV_PATH, engine)

        result = runner.run()

        # Total volume should equal processed + failed
        total_volume = result.total_volume_processed + result.total_volume_failed
        assert total_volume > 0, "Total volume should be positive"

        # Both processed and failed should be non-zero with alternating failures
        assert result.total_volume_processed > 0, "Processed volume should be positive"
        assert result.total_volume_failed > 0, "Failed volume should be positive"


class TestSimulationResult:
    """Tests for SimulationResult dataclass."""

    def test_result_success_rate_calculation(self) -> None:
        """Assert success rate is calculated correctly."""
        result = SimulationResult(
            engine_name="Test",
            total_volume_processed=1000,
            total_volume_failed=500,
            tx_success_count=8,
            tx_failure_count=2,
            tvl_history=[],
        )

        assert result.success_rate == pytest.approx(0.8)
        assert result.failure_rate == pytest.approx(0.2)
        assert result.total_transactions == 10

    def test_result_zero_transactions(self) -> None:
        """Assert success rate is 0 when no transactions processed."""
        result = SimulationResult(
            engine_name="Test",
            total_volume_processed=0,
            total_volume_failed=0,
            tx_success_count=0,
            tx_failure_count=0,
            tvl_history=[],
        )

        assert result.success_rate == 0.0
        assert result.failure_rate == 1.0
        assert result.total_transactions == 0

