from collections import Counter
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.analysis.metrics import calculate_btc_days
from src.analysis.plotting import plot_comparison
from src.config import ARK_POOL_CAPACITY, SimulationConfig
from src.engines.ark_engine import ArkEngine
from src.engines.legacy_engine import LegacyEngine
from src.engines.legacy_refill_engine import LegacyRefillEngine
from src.engines.passthrough_engine import PassthroughEngine
from src.models import Transaction, TransactionType, User, UserType
from src.simulation.runner import SimulationResult, SimulationRunner
from src.traffic.traffic_generator import TrafficGenerator
from src.traffic.user_generator import generate_users


SATS_PER_BTC: int = 100_000_000
DATA_DIR: Path = Path("data")
TRAFFIC_CSV_PATH: Path = DATA_DIR / "traffic_seed.csv"
OUTPUT_DIR: Path = Path("output")


def print_user_summary(users: list) -> None:
    """Print a formatted summary table of user type distribution."""
    counts = Counter(user.user_type for user in users)

    print("\n" + "=" * 40)
    print("L2 Capital Velocity - User Population")
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


def transactions_to_dataframe(transactions: List[Transaction]) -> pd.DataFrame:
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
    print("L2 Capital Velocity - Traffic Summary")
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


def main() -> None:
    """Initialize simulation, generate traffic, export to CSV, and run simulation."""
    config = SimulationConfig()

    # Generate user population
    users = generate_users(config)
    print_user_summary(users)

    # Generate traffic
    print("Generating transaction traffic...")
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
    print("\nRunning simulation with LegacyEngine...")
    legacy_engine = LegacyEngine(user_ids)
    legacy_runner = SimulationRunner(TRAFFIC_CSV_PATH, legacy_engine)
    legacy_result = legacy_runner.run()
    results["Legacy"] = legacy_result
    print_simulation_results(legacy_result)

    # Run simulation with LegacyRefillEngine (JIT/Splicing liquidity management)
    print("\nRunning simulation with LegacyRefillEngine...")
    refill_engine = LegacyRefillEngine(user_ids)
    refill_runner = SimulationRunner(TRAFFIC_CSV_PATH, refill_engine)
    refill_result = refill_runner.run()
    results["LegacyRefill"] = refill_result
    print_simulation_results(refill_result)
    print_operational_costs(refill_result)

    # Run simulation with ArkEngine (Pooled liquidity with round-based settlement)
    print("\nRunning simulation with ArkEngine...")
    ark_engine = ArkEngine(user_ids)
    ark_runner = SimulationRunner(TRAFFIC_CSV_PATH, ark_engine)
    ark_result = ark_runner.run()
    results["Ark"] = ark_result
    print_simulation_results(ark_result)
    print_ark_operational_stats(ark_result)

    # Print comparison summary
    print_comparison_summary(passthrough_result, legacy_result, refill_result, ark_result)
    print_ark_vs_legacy_comparison(legacy_result, ark_result)

    # Print Delving Bitcoin style capital efficiency summary
    print_capital_efficiency_summary(results)

    # Generate visualization plots
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    plot_comparison(results, str(OUTPUT_DIR))
    print(f"\nVisualization plots saved to: {OUTPUT_DIR}/")


def print_operational_costs(result: SimulationResult) -> None:
    """Print operational costs summary for engines with refill capability."""
    stats = result.operational_stats
    if not stats:
        return

    print("=" * 50)
    print(f"Operational Costs - {result.engine_name} Engine")
    print("=" * 50)
    print(f"{'Refill Operations:':<30} {int(stats.get('refill_count', 0)):>15,}")
    print(f"{'Total Fees Paid (BTC):':<30} {stats.get('total_fees_btc', 0):>15.8f}")
    print(f"{'Avg Latency (seconds):':<30} {stats.get('avg_latency_seconds', 0):>15.2f}")
    print("=" * 50 + "\n")


def print_ark_operational_stats(result: SimulationResult) -> None:
    """Print operational statistics for Ark engine."""
    stats = result.operational_stats
    if not stats:
        return

    print("=" * 50)
    print(f"Operational Stats - {result.engine_name} Engine")
    print("=" * 50)
    print(f"{'Settlement Rounds:':<30} {int(stats.get('round_count', 0)):>15,}")
    print(f"{'Total Round Fees (BTC):':<30} {stats.get('total_fees_btc', 0):>15.8f}")
    print(f"{'Avg TVL (sats):':<30} {stats.get('avg_tvl', 0):>15,.0f}")
    print("=" * 50 + "\n")


def print_comparison_summary(
    baseline: SimulationResult,
    legacy: SimulationResult,
    refill: SimulationResult | None = None,
    ark: SimulationResult | None = None,
) -> None:
    """Print a comparison of all engine results."""
    baseline_btc = baseline.total_volume_processed / SATS_PER_BTC
    legacy_btc = legacy.total_volume_processed / SATS_PER_BTC
    legacy_failed_btc = legacy.total_volume_failed / SATS_PER_BTC

    if refill is None and ark is None:
        # Two-column comparison
        print("=" * 50)
        print("Engine Comparison Summary")
        print("=" * 50)
        print(f"{'Metric':<30} {'Passthrough':>10} {'Legacy':>10}")
        print("-" * 50)
        print(f"{'Success Rate:':<30} {baseline.success_rate * 100:>9.1f}% {legacy.success_rate * 100:>9.1f}%")
        print(f"{'Volume Processed (BTC):':<30} {baseline_btc:>10.4f} {legacy_btc:>10.4f}")
        print(f"{'Failed Transactions:':<30} {baseline.tx_failure_count:>10,} {legacy.tx_failure_count:>10,}")
        print(f"{'Failed Volume (BTC):':<30} {0.0:>10.4f} {legacy_failed_btc:>10.4f}")
        print("=" * 50 + "\n")
    elif ark is None:
        # Three-column comparison (no Ark)
        refill_btc = refill.total_volume_processed / SATS_PER_BTC
        refill_failed_btc = refill.total_volume_failed / SATS_PER_BTC
        refill_fees = refill.operational_stats.get("total_fees_btc", 0)

        print("=" * 70)
        print("Engine Comparison Summary")
        print("=" * 70)
        print(f"{'Metric':<30} {'Passthrough':>12} {'Legacy':>12} {'Refill':>12}")
        print("-" * 70)
        print(
            f"{'Success Rate:':<30} "
            f"{baseline.success_rate * 100:>11.1f}% "
            f"{legacy.success_rate * 100:>11.1f}% "
            f"{refill.success_rate * 100:>11.1f}%"
        )
        print(
            f"{'Volume Processed (BTC):':<30} "
            f"{baseline_btc:>12.4f} "
            f"{legacy_btc:>12.4f} "
            f"{refill_btc:>12.4f}"
        )
        print(
            f"{'Failed Transactions:':<30} "
            f"{baseline.tx_failure_count:>12,} "
            f"{legacy.tx_failure_count:>12,} "
            f"{refill.tx_failure_count:>12,}"
        )
        print(
            f"{'Failed Volume (BTC):':<30} "
            f"{0.0:>12.4f} "
            f"{legacy_failed_btc:>12.4f} "
            f"{refill_failed_btc:>12.4f}"
        )
        print(
            f"{'Operational Fees (BTC):':<30} "
            f"{0.0:>12.4f} "
            f"{0.0:>12.4f} "
            f"{refill_fees:>12.8f}"
        )
        print("=" * 70 + "\n")
    else:
        # Four-column comparison (all engines)
        refill_btc = refill.total_volume_processed / SATS_PER_BTC
        refill_failed_btc = refill.total_volume_failed / SATS_PER_BTC
        refill_fees = refill.operational_stats.get("total_fees_btc", 0)

        ark_btc = ark.total_volume_processed / SATS_PER_BTC
        ark_failed_btc = ark.total_volume_failed / SATS_PER_BTC
        ark_fees = ark.operational_stats.get("total_fees_btc", 0)

        print("=" * 90)
        print("Engine Comparison Summary")
        print("=" * 90)
        print(f"{'Metric':<26} {'Passthrough':>12} {'Legacy':>12} {'Refill':>12} {'Ark':>12}")
        print("-" * 90)
        print(
            f"{'Success Rate:':<26} "
            f"{baseline.success_rate * 100:>11.1f}% "
            f"{legacy.success_rate * 100:>11.1f}% "
            f"{refill.success_rate * 100:>11.1f}% "
            f"{ark.success_rate * 100:>11.1f}%"
        )
        print(
            f"{'Volume Processed (BTC):':<26} "
            f"{baseline_btc:>12.4f} "
            f"{legacy_btc:>12.4f} "
            f"{refill_btc:>12.4f} "
            f"{ark_btc:>12.4f}"
        )
        print(
            f"{'Failed Transactions:':<26} "
            f"{baseline.tx_failure_count:>12,} "
            f"{legacy.tx_failure_count:>12,} "
            f"{refill.tx_failure_count:>12,} "
            f"{ark.tx_failure_count:>12,}"
        )
        print(
            f"{'Failed Volume (BTC):':<26} "
            f"{0.0:>12.4f} "
            f"{legacy_failed_btc:>12.4f} "
            f"{refill_failed_btc:>12.4f} "
            f"{ark_failed_btc:>12.4f}"
        )
        print(
            f"{'Operational Fees (BTC):':<26} "
            f"{0.0:>12.8f} "
            f"{0.0:>12.8f} "
            f"{refill_fees:>12.8f} "
            f"{ark_fees:>12.8f}"
        )
        print("=" * 90 + "\n")


def print_ark_vs_legacy_comparison(legacy: SimulationResult, ark: SimulationResult) -> None:
    """Print detailed comparison of Ark vs Legacy highlighting capital efficiency."""
    legacy_tvl = 100 * 5_000_000 * 0.5  # 100 users * 5M capacity * 50% split
    ark_tvl = ARK_POOL_CAPACITY

    print("=" * 70)
    print("Ark vs Legacy - Capital Efficiency Analysis")
    print("=" * 70)
    print(f"{'Metric':<40} {'Legacy':>12} {'Ark':>12}")
    print("-" * 70)
    print(
        f"{'TVL (sats):':<40} "
        f"{legacy_tvl:>12,} "
        f"{ark_tvl:>12,}"
    )
    print(
        f"{'TVL (BTC):':<40} "
        f"{legacy_tvl / SATS_PER_BTC:>12.2f} "
        f"{ark_tvl / SATS_PER_BTC:>12.2f}"
    )
    print(
        f"{'Capital Reduction:':<40} "
        f"{'--':>12} "
        f"{(1 - ark_tvl / legacy_tvl) * 100:>11.0f}%"
    )
    print("-" * 70)
    print(
        f"{'Success Rate:':<40} "
        f"{legacy.success_rate * 100:>11.1f}% "
        f"{ark.success_rate * 100:>11.1f}%"
    )
    success_diff = ark.success_rate - legacy.success_rate
    success_symbol = "+" if success_diff >= 0 else ""
    print(
        f"{'Success Rate Difference:':<40} "
        f"{'--':>12} "
        f"{success_symbol}{success_diff * 100:>10.1f}%"
    )
    print("-" * 70)
    print(
        f"{'Failed Transactions:':<40} "
        f"{legacy.tx_failure_count:>12,} "
        f"{ark.tx_failure_count:>12,}"
    )

    # Capital efficiency metric: volume processed per BTC of TVL
    legacy_vol = legacy.total_volume_processed
    ark_vol = ark.total_volume_processed
    legacy_efficiency = legacy_vol / legacy_tvl if legacy_tvl > 0 else 0
    ark_efficiency = ark_vol / ark_tvl if ark_tvl > 0 else 0

    print("-" * 70)
    print(
        f"{'Volume/TVL Ratio:':<40} "
        f"{legacy_efficiency:>12.2f}x "
        f"{ark_efficiency:>12.2f}x"
    )
    print("=" * 70 + "\n")


def print_capital_efficiency_summary(results: Dict[str, SimulationResult]) -> None:
    """
    Print Delving Bitcoin style summary table with capital efficiency metrics.

    Includes Success Rate, BTC-Days (capital cost), and Operational Fees.
    """
    print("\n" + "=" * 80)
    print("CAPITAL EFFICIENCY SUMMARY")
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

    # Calculate metrics for each engine
    metrics = []
    for engine_name, result in results.items():
        btc_days = calculate_btc_days(result.tvl_history)
        op_fees = result.operational_stats.get("total_fees_btc", 0.0)
        success_rate = result.success_rate

        # Composite score: penalize low success, high capital, and high fees
        # Higher score = better (normalized against worst case)
        score = success_rate * 100  # Base score from success rate
        metrics.append({
            "name": engine_name,
            "success_rate": success_rate,
            "btc_days": btc_days,
            "op_fees": op_fees,
            "score": score,
        })

    # Sort by BTC-Days (capital efficiency) for display
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

        # Compare to Legacy baseline
        legacy_metrics = next((m for m in metrics if m["name"] == "Legacy"), None)
        if legacy_metrics and best["name"] != "Legacy":
            savings_pct = (1 - best["btc_days"] / legacy_metrics["btc_days"]) * 100
            print(f"{'  → Capital savings vs Legacy:':<40} {savings_pct:.1f}%")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

