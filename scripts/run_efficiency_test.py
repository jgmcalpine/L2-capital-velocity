#!/usr/bin/env python3
"""
The Efficiency Crossover Test

Demonstrates the trade-off between Round Interval (Operational Cost) and
Liquidity Reliability by comparing LegacyRefill with Ark at different round intervals.
"""
import sys
from pathlib import Path
from typing import Dict

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Apply configuration overrides BEFORE importing dependent modules
import src.config

src.config.TOTAL_USERS = 1000
src.config.TARGET_TRANSACTIONS = 100_000
src.config.ARK_POOL_CAPACITY = 500_000_000  # 500M sats

# Patch the SimulationConfig defaults
_original_init = src.config.SimulationConfig.__init__


def _patched_init(self):
    object.__setattr__(self, "SEED", 42)
    object.__setattr__(self, "TOTAL_USERS", 1000)
    object.__setattr__(
        self,
        "USER_DISTRIBUTION",
        {"MERCHANT": 0.05, "CONSUMER": 0.85, "HODLER": 0.10},
    )
    object.__setattr__(self, "SIMULATION_DAYS", 30)
    object.__setattr__(self, "TARGET_TRANSACTIONS", 100_000)
    object.__setattr__(self, "INTERNAL_TX_RATIO", 0.20)
    object.__setattr__(self, "AMOUNT_MU", 9.8)
    object.__setattr__(self, "AMOUNT_SIGMA", 1.2)
    object.__setattr__(self, "PEAK_HOUR_START", 8)
    object.__setattr__(self, "PEAK_HOUR_END", 20)
    object.__setattr__(self, "PEAK_MULTIPLIER", 2.0)
    object.__setattr__(
        self,
        "SENDER_WEIGHTS",
        {"MERCHANT": 0.02, "CONSUMER": 0.93, "HODLER": 0.05},
    )
    object.__setattr__(
        self,
        "RECEIVER_WEIGHTS",
        {"MERCHANT": 0.60, "CONSUMER": 0.30, "HODLER": 0.10},
    )


src.config.SimulationConfig.__init__ = _patched_init

# Now import the rest of the modules
import pandas as pd

from src.analysis.metrics import calculate_btc_days
from src.config import ARK_POOL_CAPACITY, SimulationConfig
from src.engines.ark_engine import ArkEngine
from src.engines.legacy_refill_engine import LegacyRefillEngine
from src.models import Transaction
from src.simulation.runner import SimulationResult, SimulationRunner
from src.traffic.traffic_generator import TrafficGenerator
from src.traffic.user_generator import generate_users

SATS_PER_BTC: int = 100_000_000
DATA_DIR: Path = PROJECT_ROOT / "data"
TRAFFIC_CSV_PATH: Path = DATA_DIR / "traffic_seed_efficiency_test.csv"
OUTPUT_DIR: Path = PROJECT_ROOT / "output"


def transactions_to_dataframe(transactions: list[Transaction]) -> pd.DataFrame:
    """Convert list of Transaction objects to a Pandas DataFrame."""
    return pd.DataFrame([tx.model_dump() for tx in transactions])


def save_traffic_csv(df: pd.DataFrame, path: Path) -> None:
    """Save traffic DataFrame to CSV, creating directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Traffic data saved to: {path}\n")


def print_efficiency_comparison(results: Dict[str, SimulationResult]) -> None:
    """
    Print comparison table showing trade-offs between round intervals.

    Compares:
    - Config (Legacy, Ark-10m, Ark-1h, Ark-2h)
    - Success Rate (Did the pool drain?)
    - Op Fees (Did we undercut Legacy?)
    - BTC-Days (Did we keep capital low?)
    """
    print("\n" + "=" * 90)
    print("EFFICIENCY CROSSOVER TEST - Round Interval Trade-offs")
    print("=" * 90)
    print(
        f"{'Config':<20} "
        f"{'Success Rate':>14} "
        f"{'Op Fees (BTC)':>18} "
        f"{'BTC-Days':>16} "
        f"{'Round Count':>14}"
    )
    print("-" * 90)

    metrics = []
    for config_name, result in results.items():
        btc_days = calculate_btc_days(result.tvl_history)
        op_fees = result.operational_stats.get("total_fees_btc", 0.0)
        success_rate = result.success_rate
        round_count = result.operational_stats.get("round_count", 0.0)

        metrics.append({
            "name": config_name,
            "success_rate": success_rate,
            "btc_days": btc_days,
            "op_fees": op_fees,
            "round_count": round_count,
        })

    # Sort by config name for consistent display
    config_order = ["Legacy", "Ark-10m", "Ark-1h", "Ark-2h"]
    sorted_metrics = sorted(
        metrics,
        key=lambda x: config_order.index(x["name"]) if x["name"] in config_order else 999
    )

    for m in sorted_metrics:
        success_rate_str = f"{m['success_rate'] * 100:.1f}%"
        op_fees_str = f"{m['op_fees']:.8f}"
        btc_days_str = f"{m['btc_days']:.2f}" if m["btc_days"] > 0 else "N/A"
        round_count_str = f"{int(m['round_count']):,}" if m["round_count"] > 0 else "N/A"

        print(
            f"{m['name']:<20} "
            f"{success_rate_str:>14} "
            f"{op_fees_str:>18} "
            f"{btc_days_str:>16} "
            f"{round_count_str:>14}"
        )

    print("-" * 90)

    # Analysis and insights
    legacy = next((m for m in metrics if m["name"] == "Legacy"), None)
    ark_10m = next((m for m in metrics if m["name"] == "Ark-10m"), None)
    ark_1h = next((m for m in metrics if m["name"] == "Ark-1h"), None)
    ark_2h = next((m for m in metrics if m["name"] == "Ark-2h"), None)

    print("\n" + "=" * 90)
    print("ANALYSIS")
    print("=" * 90)

    if legacy and ark_10m:
        if ark_10m["op_fees"] < legacy["op_fees"]:
            savings = (1 - ark_10m["op_fees"] / legacy["op_fees"]) * 100
            print(f"✓ Ark-10m undercuts Legacy by {savings:.1f}% on operational fees")
        else:
            increase = (ark_10m["op_fees"] / legacy["op_fees"] - 1) * 100
            print(f"✗ Ark-10m costs {increase:.1f}% more than Legacy on operational fees")

        if ark_10m["success_rate"] >= 0.95:
            print(f"✓ Ark-10m maintains liquidity reliability ({ark_10m['success_rate'] * 100:.1f}% success)")
        else:
            print(f"✗ Ark-10m pool drained ({ark_10m['success_rate'] * 100:.1f}% success)")

    if ark_1h and ark_10m:
        fee_reduction = (1 - ark_1h["op_fees"] / ark_10m["op_fees"]) * 100 if ark_10m["op_fees"] > 0 else 0
        success_diff = (ark_1h["success_rate"] - ark_10m["success_rate"]) * 100
        print(f"\nArk-1h vs Ark-10m:")
        print(f"  Fee reduction: {fee_reduction:.1f}%")
        print(f"  Success rate change: {success_diff:+.1f}%")

    if ark_2h and ark_1h:
        fee_reduction = (1 - ark_2h["op_fees"] / ark_1h["op_fees"]) * 100 if ark_1h["op_fees"] > 0 else 0
        success_diff = (ark_2h["success_rate"] - ark_1h["success_rate"]) * 100
        print(f"\nArk-2h vs Ark-1h:")
        print(f"  Fee reduction: {fee_reduction:.1f}%")
        print(f"  Success rate change: {success_diff:+.1f}%")

    # Find the efficiency crossover point
    viable_configs = [m for m in metrics if m["success_rate"] >= 0.95]
    if viable_configs:
        best_efficiency = min(viable_configs, key=lambda x: x["op_fees"])
        print(f"\n{'Best Efficiency (≥95% success, lowest fees):':<50} {best_efficiency['name']}")
        print(f"{'  → Operational Fees:':<50} {best_efficiency['op_fees']:.8f} BTC")
        print(f"{'  → Success Rate:':<50} {best_efficiency['success_rate'] * 100:.1f}%")

    print("=" * 90 + "\n")


def main() -> None:
    """Run the efficiency crossover test."""
    print("\n" + "#" * 90)
    print("#" + " " * 88 + "#")
    print("#" + "EFFICIENCY CROSSOVER TEST".center(88) + "#")
    print("#" + " " * 88 + "#")
    print("#" * 90 + "\n")

    config = SimulationConfig()

    # Display configuration
    print("Configuration:")
    print(f"  Total Users:           {config.TOTAL_USERS:,}")
    print(f"  Target Transactions:   {config.TARGET_TRANSACTIONS:,}")
    print(f"  Ark Pool Capacity:     {ARK_POOL_CAPACITY:,} sats ({ARK_POOL_CAPACITY / SATS_PER_BTC:.1f} BTC)")
    print()

    # Generate user population
    print("Generating user population...")
    users = generate_users(config)
    user_ids = [user.user_id for user in users]
    print(f"Generated {len(users):,} users\n")

    # Generate traffic ONCE (so all engines fight the same dataset)
    print("Generating transaction traffic (this may take a moment)...")
    generator = TrafficGenerator(config)
    transactions = generator.generate_month_of_traffic(users)
    print(f"Generated {len(transactions):,} transactions\n")

    # Convert to DataFrame and save
    df = transactions_to_dataframe(transactions)
    save_traffic_csv(df, TRAFFIC_CSV_PATH)

    # Collect all results for comparison
    results: Dict[str, SimulationResult] = {}

    # Pass 1: Legacy Refill (Baseline)
    print("=" * 90)
    print("PASS 1: Legacy Refill (Baseline)")
    print("=" * 90)
    legacy_refill_engine = LegacyRefillEngine(user_ids)
    legacy_refill_runner = SimulationRunner(TRAFFIC_CSV_PATH, legacy_refill_engine)
    legacy_refill_result = legacy_refill_runner.run()
    results["Legacy"] = legacy_refill_result
    print(f"Success Rate: {legacy_refill_result.success_rate * 100:.1f}%")
    print(f"Op Fees: {legacy_refill_result.operational_stats.get('total_fees_btc', 0.0):.8f} BTC")
    print(f"BTC-Days: {calculate_btc_days(legacy_refill_result.tvl_history):.2f}\n")

    # Pass 2: Ark (10 Minute Rounds)
    print("=" * 90)
    print("PASS 2: Ark (10 Minute Rounds)")
    print("=" * 90)
    ark_10m_engine = ArkEngine(user_ids, round_interval=600)
    ark_10m_runner = SimulationRunner(TRAFFIC_CSV_PATH, ark_10m_engine)
    ark_10m_result = ark_10m_runner.run()
    results["Ark-10m"] = ark_10m_result
    print(f"Success Rate: {ark_10m_result.success_rate * 100:.1f}%")
    print(f"Op Fees: {ark_10m_result.operational_stats.get('total_fees_btc', 0.0):.8f} BTC")
    print(f"BTC-Days: {calculate_btc_days(ark_10m_result.tvl_history):.2f}")
    print(f"Round Count: {int(ark_10m_result.operational_stats.get('round_count', 0)):,}\n")

    # Pass 3: Ark (1 Hour Rounds)
    print("=" * 90)
    print("PASS 3: Ark (1 Hour Rounds)")
    print("=" * 90)
    ark_1h_engine = ArkEngine(user_ids, round_interval=3600)
    ark_1h_runner = SimulationRunner(TRAFFIC_CSV_PATH, ark_1h_engine)
    ark_1h_result = ark_1h_runner.run()
    results["Ark-1h"] = ark_1h_result
    print(f"Success Rate: {ark_1h_result.success_rate * 100:.1f}%")
    print(f"Op Fees: {ark_1h_result.operational_stats.get('total_fees_btc', 0.0):.8f} BTC")
    print(f"BTC-Days: {calculate_btc_days(ark_1h_result.tvl_history):.2f}")
    print(f"Round Count: {int(ark_1h_result.operational_stats.get('round_count', 0)):,}\n")

    # Pass 4: Ark (2 Hour Rounds)
    print("=" * 90)
    print("PASS 4: Ark (2 Hour Rounds)")
    print("=" * 90)
    ark_2h_engine = ArkEngine(user_ids, round_interval=7200)
    ark_2h_runner = SimulationRunner(TRAFFIC_CSV_PATH, ark_2h_engine)
    ark_2h_result = ark_2h_runner.run()
    results["Ark-2h"] = ark_2h_result
    print(f"Success Rate: {ark_2h_result.success_rate * 100:.1f}%")
    print(f"Op Fees: {ark_2h_result.operational_stats.get('total_fees_btc', 0.0):.8f} BTC")
    print(f"BTC-Days: {calculate_btc_days(ark_2h_result.tvl_history):.2f}")
    print(f"Round Count: {int(ark_2h_result.operational_stats.get('round_count', 0)):,}\n")

    # Print comparison table
    print_efficiency_comparison(results)


if __name__ == "__main__":
    main()

