"""Visualization functions for simulation results."""

from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt

from src.analysis.metrics import calculate_btc_days
from src.simulation.runner import SimulationResult

SECONDS_PER_DAY: int = 86400
SATS_PER_BTC: int = 100_000_000

# Color palette for consistent engine styling
ENGINE_COLORS: Dict[str, str] = {
    "Passthrough": "#6B7280",  # Gray
    "Legacy": "#EF4444",  # Red
    "LegacyRefill": "#F59E0B",  # Amber
    "Ark": "#10B981",  # Emerald
}


def _get_engine_color(engine_name: str) -> str:
    """Get color for an engine, with fallback for unknown engines."""
    return ENGINE_COLORS.get(engine_name, "#3B82F6")


def plot_comparison(
    results: Dict[str, SimulationResult],
    output_dir: str,
    filename_suffix: str = "",
) -> None:
    """
    Generate comparison charts for simulation results.

    Creates two charts:
    1. TVL Over Time - Line chart showing TVL evolution for each engine
    2. Cost Tradeoff - Bar chart comparing BTC-Days vs Operational Fees

    Args:
        results: Dictionary mapping engine name to SimulationResult.
        output_dir: Directory path to save the generated plots.
        filename_suffix: Optional suffix for output filenames (e.g., "_1000_users").
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _plot_tvl_comparison(results, output_path, filename_suffix)
    _plot_cost_tradeoff(results, output_path, filename_suffix)


def _plot_tvl_comparison(
    results: Dict[str, SimulationResult],
    output_path: Path,
    filename_suffix: str = "",
) -> None:
    """Generate TVL over time comparison chart."""
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12, 6))

    for engine_name, result in results.items():
        if not result.tvl_history:
            continue

        # Convert timestamps to days and TVL to BTC
        days = [(ts / SECONDS_PER_DAY) for ts, _ in result.tvl_history]
        tvl_btc = [(tvl / SATS_PER_BTC) for _, tvl in result.tvl_history]

        # Downsample for cleaner plotting (every 100th point)
        sample_rate = max(1, len(days) // 1000)
        days_sampled = days[::sample_rate]
        tvl_sampled = tvl_btc[::sample_rate]

        color = _get_engine_color(engine_name)
        ax.plot(
            days_sampled,
            tvl_sampled,
            label=engine_name,
            color=color,
            linewidth=1.5,
            alpha=0.8,
        )

    ax.set_xlabel("Simulation Day", fontsize=12)
    ax.set_ylabel("TVL (BTC)", fontsize=12)
    ax.set_title("Total Value Locked Over Time", fontsize=14, fontweight="bold")
    ax.legend(loc="best", frameon=True)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    filename = f"tvl_comparison{filename_suffix}.png"
    plt.tight_layout()
    plt.savefig(output_path / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path / filename}")


def _plot_cost_tradeoff(
    results: Dict[str, SimulationResult],
    output_path: Path,
    filename_suffix: str = "",
) -> None:
    """Generate cost tradeoff bar chart (BTC-Days vs Operational Fees)."""
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    engine_names = list(results.keys())
    btc_days_values = []
    op_fees_values = []
    colors = []

    for engine_name in engine_names:
        result = results[engine_name]
        btc_days = calculate_btc_days(result.tvl_history)
        op_fees = result.operational_stats.get("total_fees_btc", 0.0)

        btc_days_values.append(btc_days)
        op_fees_values.append(op_fees)
        colors.append(_get_engine_color(engine_name))

    x_positions = range(len(engine_names))

    # Subplot 1: BTC-Days (Capital Cost)
    bars1 = ax1.bar(x_positions, btc_days_values, color=colors, edgecolor="white", linewidth=1.5)
    ax1.set_xlabel("Engine", fontsize=12)
    ax1.set_ylabel("BTC-Days", fontsize=12)
    ax1.set_title("Capital Cost (BTC-Days)\n↓ Lower is Better", fontsize=13, fontweight="bold")
    ax1.set_xticks(x_positions)
    ax1.set_xticklabels(engine_names, rotation=15, ha="right")
    ax1.set_ylim(bottom=0)

    # Add value labels on bars
    for bar, value in zip(bars1, btc_days_values):
        height = bar.get_height()
        ax1.annotate(
            f"{value:.1f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    # Subplot 2: Operational Fees
    bars2 = ax2.bar(x_positions, op_fees_values, color=colors, edgecolor="white", linewidth=1.5)
    ax2.set_xlabel("Engine", fontsize=12)
    ax2.set_ylabel("Operational Fees (BTC)", fontsize=12)
    ax2.set_title("Operational Cost (Fees)\n↓ Lower is Better", fontsize=13, fontweight="bold")
    ax2.set_xticks(x_positions)
    ax2.set_xticklabels(engine_names, rotation=15, ha="right")
    ax2.set_ylim(bottom=0)

    # Add value labels on bars
    for bar, value in zip(bars2, op_fees_values):
        height = bar.get_height()
        label = f"{value:.6f}" if value > 0 else "0"
        ax2.annotate(
            label,
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    filename = f"cost_tradeoff{filename_suffix}.png"
    plt.tight_layout()
    plt.savefig(output_path / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {output_path / filename}")

