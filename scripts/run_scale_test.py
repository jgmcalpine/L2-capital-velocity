#!/usr/bin/env python3
"""
Victory Lap 1 - Scale Test

Runs the L2 Capital Velocity simulation with 1,000 users to validate
scalability and compare operational costs at scale.
"""
import sys
from collections import Counter
from pathlib import Path
from typing import Dict

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Apply configuration overrides BEFORE importing dependent modules
import src.config

src.config.TOTAL_USERS = 1000
src.config.TARGET_TRANSACTIONS = 100_000
src.config.ARK_POOL_CAPACITY = 500_000_000  # 500M sats (maintaining 10% ratio vs Legacy)
src.config.LEGACY_CHANNEL_CAPACITY = 5_000_000  # Keep per-user channel size same

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
from src.analysis.plotting import plot_comparison
from src.config import ARK_POOL_CAPACITY, SimulationConfig
from src.engines.ark_engine import ArkEngine
from src.engines.legacy_engine import LegacyEngine
from src.engines.legacy_refill_engine import LegacyRefillEngine
from src.engines.passthrough_engine import PassthroughEngine
from src.models import Transaction, TransactionType, UserType
from src.simulation.runner import SimulationResult, SimulationRunner
from src.traffic.traffic_generator import TrafficGenerator
from src.traffic.user_generator import generate_users

SATS_PER_BTC: int = 100_000_000
DATA_DIR: Path = PROJECT_ROOT / "data"
TRAFFIC_CSV_PATH: Path = DATA_DIR / "traffic_seed_1000_users.csv"
OUTPUT_DIR: Path = PROJECT_ROOT / "output"


def print_user_summary(users: list) -> None:
    """Print a formatted summary table of user type distribution."""
    counts = Counter(user.user_type for user in users)

    print("\n" + "=" * 40)
    print("L2 Capital Velocity - Scale Test (1000 Users)")
    print("=" * 40)
    print(f"{'User Type':<15} {'Count':>10} {'Percentage':>12}")
    print("-" * 40)

    total = len(users)
    for user_type in UserType:
        count = counts.get(user_type, 0)
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"{user_type.value:<15} {count:>10} {percentage:>11.1f}%")

    print("-" * 40)
    print(f"{'TOTAL':<15} {total:>10}")
    print("=" * 40 + "\n")


def transactions_to_dataframe(transactions: list[Transaction]) -> pd.DataFrame:
    """Convert list of Transaction objects to a Pandas DataFrame."""
    return pd.DataFrame([tx.model_dump() for tx in transactions])


def print_traffic_summary(df: pd.DataFrame) -> None:
    """Print a formatted summary of traffic statistics."""
    total_volume_sats = df["amount_sats"].sum()
    total_volume_btc = total_volume_sats / SATS_PER_BTC

    type_counts = df["tx_type"].value_counts()

    internal_count = type_counts.get(TransactionType.INTERNAL.value, 0)
    external_inbound = type_counts.get(TransactionType.EXTERNAL_INBOUND.value, 0)
    external_outbound = type_counts.get(TransactionType.EXTERNAL_OUTBOUND.value, 0)
    external_total = external_inbound + external_outbound

    print("=" * 50)
    print("Traffic Summary - Scale Test")
    print("=" * 50)
    print(f"{'Total Transactions:':<30} {len(df):>15,}")
    print(f"{'Total Volume (sats):':<30} {total_volume_sats:>15,}")
    print(f"{'Total Volume (BTC):':<30} {total_volume_btc:>15.4f}")
    print("-" * 50)
    print(f"{'Internal Transactions:':<30} {internal_count:>15,}")
    print(f"{'External Inbound:':<30} {external_inbound:>15,}")
    print(f"{'External Outbound:':<30} {external_outbound:>15,}")
    print(f"{'External Total:':<30} {external_total:>15,}")
    print("-" * 50)
    print(f"{'Avg Amount (sats):':<30} {df['amount_sats'].mean():>15,.0f}")
    print(f"{'Median Amount (sats):':<30} {df['amount_sats'].median():>15,.0f}")
    print(f"{'Max Amount (sats):':<30} {df['amount_sats'].max():>15,}")
    print("=" * 50 + "\n")


def save_traffic_csv(df: pd.DataFrame, path: Path) -> None:
    """Save traffic DataFrame to CSV, creating directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Traffic data saved to: {path}")


def print_simulation_results(result: SimulationResult) -> None:
    """Print a formatted summary of simulation results."""
    total_volume_btc = result.total_volume_processed / SATS_PER_BTC
    failed_volume_btc = result.total_volume_failed / SATS_PER_BTC

    print("\n" + "=" * 50)
    print(f"Simulation Results - {result.engine_name} Engine")
    print("=" * 50)
    print(f"{'Total Transactions:':<30} {result.total_transactions:>15,}")
    print(f"{'Successful:':<30} {result.tx_success_count:>15,}")
    print(f"{'Failed:':<30} {result.tx_failure_count:>15,}")
    print("-" * 50)
    print(f"{'Success Rate:':<30} {result.success_rate * 100:>14.1f}%")
    print("-" * 50)
    print(f"{'Volume Processed (BTC):':<30} {total_volume_btc:>15.4f}")
    print(f"{'Volume Failed (BTC):':<30} {failed_volume_btc:>15.4f}")
    print("=" * 50 + "\n")


def print_capital_efficiency_summary(results: Dict[str, SimulationResult]) -> None:
    """
    Print Delving Bitcoin style summary table with capital efficiency metrics.

    Focus on Operational Fees row for scale test validation.
    """
    print("\n" + "=" * 80)
    print("CAPITAL EFFICIENCY SUMMARY - SCALE TEST (1000 USERS)")
    print("Delving Bitcoin Style Analysis")
    print("=" * 80)
    print(
        f"{'Engine':<16} "
        f"{'Success Rate':>14} "
        f"{'BTC-Days':>16} "
        f"{'Op Fees (BTC)':>18} "
        f"{'Score':>10}"
    )
    print("-" * 80)

    metrics = []
    for engine_name, result in results.items():
        btc_days = calculate_btc_days(result.tvl_history)
        op_fees = result.operational_stats.get("total_fees_btc", 0.0)
        success_rate = result.success_rate
        score = success_rate * 100

        metrics.append({
            "name": engine_name,
            "success_rate": success_rate,
            "btc_days": btc_days,
            "op_fees": op_fees,
            "score": score,
        })

    for m in metrics:
        btc_days_str = f"{m['btc_days']:.2f}" if m["btc_days"] > 0 else "N/A"
        op_fees_str = f"{m['op_fees']:.8f}" if m["op_fees"] > 0 else "0.00000000"

        print(
            f"{m['name']:<16} "
            f"{m['success_rate'] * 100:>13.1f}% "
            f"{btc_days_str:>16} "
            f"{op_fees_str:>18} "
            f"{m['score']:>10.1f}"
        )

    print("-" * 80)

    # Find the most capital-efficient engine with acceptable success rate
    viable_engines = [m for m in metrics if m["success_rate"] >= 0.95]
    if viable_engines:
        best = min(viable_engines, key=lambda x: x["btc_days"])
        print(f"\n{'Best Capital Efficiency (≥95% success):':<40} {best['name']}")
        print(f"{'  → BTC-Days required:':<40} {best['btc_days']:.2f}")

        legacy_metrics = next((m for m in metrics if m["name"] == "Legacy"), None)
        if legacy_metrics and best["name"] != "Legacy":
            savings_pct = (1 - best["btc_days"] / legacy_metrics["btc_days"]) * 100
            print(f"{'  → Capital savings vs Legacy:':<40} {savings_pct:.1f}%")

    # Highlight operational fees comparison
    print("\n" + "-" * 80)
    print("OPERATIONAL FEES COMPARISON (Key Metric for Scale Test)")
    print("-" * 80)
    refill = next((m for m in metrics if m["name"] == "LegacyRefill"), None)
    ark = next((m for m in metrics if m["name"] == "Ark"), None)
    if refill and ark:
        print(f"{'LegacyRefill Op Fees:':<30} {refill['op_fees']:.8f} BTC")
        print(f"{'Ark Op Fees:':<30} {ark['op_fees']:.8f} BTC")
        if refill["op_fees"] > 0:
            ratio = ark["op_fees"] / refill["op_fees"]
            savings = (1 - ratio) * 100
            print(f"{'Ark Fee Savings vs LegacyRefill:':<30} {savings:.1f}%")

    print("=" * 80 + "\n")


def main() -> None:
    """Run the 1000-user scale test simulation."""
    print("\n" + "#" * 80)
    print("#" + " " * 78 + "#")
    print("#" + "VICTORY LAP 1 - SCALE TEST (1000 USERS)".center(78) + "#")
    print("#" + " " * 78 + "#")
    print("#" * 80 + "\n")

    config = SimulationConfig()

    # Display configuration
    print("Configuration:")
    print(f"  Total Users:           {config.TOTAL_USERS:,}")
    print(f"  Target Transactions:   {config.TARGET_TRANSACTIONS:,}")
    print(f"  Ark Pool Capacity:     {ARK_POOL_CAPACITY:,} sats ({ARK_POOL_CAPACITY / SATS_PER_BTC:.1f} BTC)")
    print(f"  Legacy Channel Cap:    {src.config.LEGACY_CHANNEL_CAPACITY:,} sats")
    print()

    # Generate user population
    users = generate_users(config)
    print_user_summary(users)

    # Generate traffic
    print("Generating transaction traffic (this may take a moment)...")
    generator = TrafficGenerator(config)
    transactions = generator.generate_month_of_traffic(users)

    # Convert to DataFrame and display summary
    df = transactions_to_dataframe(transactions)
    print_traffic_summary(df)

    # Save to CSV
    save_traffic_csv(df, TRAFFIC_CSV_PATH)

    # Collect all results for analysis
    results: Dict[str, SimulationResult] = {}
    user_ids = [user.user_id for user in users]

    # Run simulation with PassthroughEngine (baseline - 100% success)
    print("\nRunning simulation with PassthroughEngine...")
    passthrough_engine = PassthroughEngine()
    passthrough_runner = SimulationRunner(TRAFFIC_CSV_PATH, passthrough_engine)
    passthrough_result = passthrough_runner.run()
    results["Passthrough"] = passthrough_result
    print_simulation_results(passthrough_result)

    # Run simulation with LegacyEngine (static Lightning channels)
    print("Running simulation with LegacyEngine...")
    legacy_engine = LegacyEngine(user_ids)
    legacy_runner = SimulationRunner(TRAFFIC_CSV_PATH, legacy_engine)
    legacy_result = legacy_runner.run()
    results["Legacy"] = legacy_result
    print_simulation_results(legacy_result)

    # Run simulation with LegacyRefillEngine (JIT/Splicing liquidity management)
    print("Running simulation with LegacyRefillEngine...")
    refill_engine = LegacyRefillEngine(user_ids)
    refill_runner = SimulationRunner(TRAFFIC_CSV_PATH, refill_engine)
    refill_result = refill_runner.run()
    results["LegacyRefill"] = refill_result
    print_simulation_results(refill_result)

    # Run simulation with ArkEngine (Pooled liquidity with round-based settlement)
    print("Running simulation with ArkEngine...")
    ark_engine = ArkEngine(user_ids)
    ark_runner = SimulationRunner(TRAFFIC_CSV_PATH, ark_engine)
    ark_result = ark_runner.run()
    results["Ark"] = ark_result
    print_simulation_results(ark_result)

    # Print Delving Bitcoin style capital efficiency summary
    print_capital_efficiency_summary(results)

    # Generate visualization plots with scale test suffix
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plot_comparison(results, str(OUTPUT_DIR), filename_suffix="_1000_users")
    print(f"\nVisualization plots saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

