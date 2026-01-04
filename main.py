from collections import Counter
from pathlib import Path
from typing import List

import pandas as pd

from src.config import SimulationConfig
from src.engines.legacy_engine import LegacyEngine
from src.engines.passthrough_engine import PassthroughEngine
from src.models import Transaction, TransactionType, User, UserType
from src.simulation.runner import SimulationResult, SimulationRunner
from src.traffic.traffic_generator import TrafficGenerator
from src.traffic.user_generator import generate_users


SATS_PER_BTC: int = 100_000_000
DATA_DIR: Path = Path("data")
TRAFFIC_CSV_PATH: Path = DATA_DIR / "traffic_seed.csv"


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

    # Run simulation with PassthroughEngine (baseline - 100% success)
    print("\nRunning simulation with PassthroughEngine...")
    passthrough_engine = PassthroughEngine()
    passthrough_runner = SimulationRunner(TRAFFIC_CSV_PATH, passthrough_engine)
    passthrough_result = passthrough_runner.run()
    print_simulation_results(passthrough_result)

    # Run simulation with LegacyEngine (static Lightning channels)
    print("\nRunning simulation with LegacyEngine...")
    user_ids = [user.user_id for user in users]
    legacy_engine = LegacyEngine(user_ids)
    legacy_runner = SimulationRunner(TRAFFIC_CSV_PATH, legacy_engine)
    legacy_result = legacy_runner.run()
    print_simulation_results(legacy_result)

    # Print comparison summary
    print_comparison_summary(passthrough_result, legacy_result)


def print_comparison_summary(baseline: SimulationResult, legacy: SimulationResult) -> None:
    """Print a comparison of baseline vs legacy engine results."""
    baseline_btc = baseline.total_volume_processed / SATS_PER_BTC
    legacy_btc = legacy.total_volume_processed / SATS_PER_BTC
    legacy_failed_btc = legacy.total_volume_failed / SATS_PER_BTC

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


if __name__ == "__main__":
    main()

