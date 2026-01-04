"""Metrics calculations for simulation analysis."""

from typing import List, Tuple

SECONDS_PER_DAY: int = 86400
SATS_PER_BTC: int = 100_000_000


def calculate_btc_days(tvl_history: List[Tuple[float, float]]) -> float:
    """
    Calculate the BTC-Days metric from TVL history.

    BTC-Days represents the cumulative capital locked over time, measured as
    the integral of TVL (in BTC) over time (in days). Lower values indicate
    more capital-efficient systems.

    Args:
        tvl_history: List of (timestamp, tvl_in_sats) tuples, sorted by timestamp.

    Returns:
        Total BTC-Days as a float. Returns 0.0 if history has fewer than 2 points.
    """
    if len(tvl_history) < 2:
        return 0.0

    total_sat_seconds = 0.0

    for i in range(1, len(tvl_history)):
        prev_timestamp, prev_tvl = tvl_history[i - 1]
        curr_timestamp, _ = tvl_history[i]

        time_delta_seconds = curr_timestamp - prev_timestamp
        if time_delta_seconds > 0:
            # Use the TVL at the start of the interval (left Riemann sum)
            total_sat_seconds += prev_tvl * time_delta_seconds

    # Convert sat-seconds to BTC-days
    btc_days = total_sat_seconds / SATS_PER_BTC / SECONDS_PER_DAY
    return btc_days

