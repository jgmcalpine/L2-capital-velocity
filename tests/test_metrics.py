"""Tests for the metrics module."""

import pytest

from src.analysis.metrics import calculate_btc_days, SECONDS_PER_DAY, SATS_PER_BTC


class TestBtcDaysCalculation:
    """Tests for calculate_btc_days function."""

    def test_empty_history_returns_zero(self) -> None:
        """Empty TVL history should return 0.0."""
        assert calculate_btc_days([]) == 0.0

    def test_single_point_returns_zero(self) -> None:
        """Single data point cannot calculate area under curve."""
        tvl_history = [(0.0, 1_000_000)]
        assert calculate_btc_days(tvl_history) == 0.0

    def test_constant_tvl_one_day(self) -> None:
        """1 BTC held for 1 day = 1 BTC-Day."""
        tvl_history = [
            (0.0, SATS_PER_BTC),  # 1 BTC at t=0
            (SECONDS_PER_DAY, SATS_PER_BTC),  # Still 1 BTC at t=1 day
        ]
        result = calculate_btc_days(tvl_history)
        assert result == pytest.approx(1.0, rel=1e-9)

    def test_constant_tvl_multiple_days(self) -> None:
        """1 BTC held for 30 days = 30 BTC-Days."""
        tvl_history = [
            (0.0, SATS_PER_BTC),
            (30 * SECONDS_PER_DAY, SATS_PER_BTC),
        ]
        result = calculate_btc_days(tvl_history)
        assert result == pytest.approx(30.0, rel=1e-9)

    def test_varying_tvl(self) -> None:
        """Test with varying TVL over time (left Riemann sum)."""
        # 1 BTC for 1 day, then 2 BTC for 1 day
        # Using left Riemann sum: 1*1 + 2*1 = 3 BTC-Days
        tvl_history = [
            (0.0, SATS_PER_BTC),  # 1 BTC
            (SECONDS_PER_DAY, 2 * SATS_PER_BTC),  # 2 BTC
            (2 * SECONDS_PER_DAY, 2 * SATS_PER_BTC),  # 2 BTC (end point)
        ]
        result = calculate_btc_days(tvl_history)
        # Day 0-1: 1 BTC * 1 day = 1
        # Day 1-2: 2 BTC * 1 day = 2
        # Total: 3 BTC-Days
        assert result == pytest.approx(3.0, rel=1e-9)

    def test_fractional_btc(self) -> None:
        """Test with fractional BTC amounts."""
        tvl_history = [
            (0.0, SATS_PER_BTC // 2),  # 0.5 BTC
            (SECONDS_PER_DAY, SATS_PER_BTC // 2),
        ]
        result = calculate_btc_days(tvl_history)
        assert result == pytest.approx(0.5, rel=1e-9)

    def test_zero_tvl(self) -> None:
        """Zero TVL for entire period should return 0."""
        tvl_history = [
            (0.0, 0),
            (SECONDS_PER_DAY, 0),
        ]
        result = calculate_btc_days(tvl_history)
        assert result == 0.0

    def test_decreasing_tvl(self) -> None:
        """Test TVL that decreases over time."""
        # 2 BTC for 1 day, then 1 BTC for 1 day
        tvl_history = [
            (0.0, 2 * SATS_PER_BTC),
            (SECONDS_PER_DAY, SATS_PER_BTC),
            (2 * SECONDS_PER_DAY, SATS_PER_BTC),
        ]
        result = calculate_btc_days(tvl_history)
        # Day 0-1: 2 BTC * 1 day = 2
        # Day 1-2: 1 BTC * 1 day = 1
        # Total: 3 BTC-Days
        assert result == pytest.approx(3.0, rel=1e-9)

    def test_high_frequency_samples(self) -> None:
        """Test with many data points (simulating per-transaction sampling)."""
        # 1 BTC held for 1 day with hourly samples
        samples_per_day = 24
        interval = SECONDS_PER_DAY / samples_per_day
        tvl_history = [
            (i * interval, SATS_PER_BTC)
            for i in range(samples_per_day + 1)
        ]
        result = calculate_btc_days(tvl_history)
        assert result == pytest.approx(1.0, rel=1e-9)

