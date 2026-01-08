#!/usr/bin/env python3
"""
Generate a clean, minimalist Pareto scatter plot comparing operational fees against
liquidity cost. High-signal, low-noise visualization for scientific publications.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

# Ensure project root is available for imports when run directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR: Path = PROJECT_ROOT / "output"


@dataclass(frozen=True)
class DataPoint:
    """Represents a single data point on the Pareto plot."""
    x: float  # Operational Fees (BTC)
    y: float  # Liquidity Cost (BTC-Days)
    color: str
    marker: str
    label: str
    alpha: float = 1.0


# Data points as specified
POINTS: tuple[DataPoint, ...] = (
    DataPoint(
        x=0.0,
        y=918.0,
        color='red',
        marker='x',
        label='Legacy (Static) - 30% Fail',
        alpha=0.7,
    ),
    DataPoint(
        x=0.01018,
        y=918.88,
        color='#1f77b4',
        marker='o',
        label='Legacy (Optimized)',
    ),
    DataPoint(
        x=0.08638,
        y=156.53,
        color='#e377c2',
        marker='o',
        label='Ark (10m Rounds)',
    ),
    DataPoint(
        x=0.01438,
        y=156.53,
        color='#ff7f0e',
        marker='o',
        label='Ark (1h Rounds)',
    ),
    DataPoint(
        x=0.00718,
        y=156.53,
        color='#2ca02c',
        marker='D',
        label='Ark (2h Rounds)',
    ),
)


def draw_crosshairs(ax: plt.Axes, anchor_point: DataPoint) -> None:
    """
    Draw crosshairs from the anchor point (Legacy Optimized).
    Creates a visual boundary - points in bottom-left rectangle are strictly better.
    """
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    
    # Vertical line from anchor down to X-axis
    ax.axvline(
        x=anchor_point.x,
        ymin=0,
        ymax=anchor_point.y / ylim[1],
        color='grey',
        linestyle='--',
        linewidth=0.8,
        alpha=0.6,
        zorder=2,
    )
    
    # Horizontal line from anchor left to Y-axis (x=0)
    # Calculate relative position of x=0 in the axis range
    x0_relative = (0 - xlim[0]) / (xlim[1] - xlim[0])
    x_anchor_relative = (anchor_point.x - xlim[0]) / (xlim[1] - xlim[0])
    ax.axhline(
        y=anchor_point.y,
        xmin=x0_relative,
        xmax=x_anchor_relative,
        color='grey',
        linestyle='--',
        linewidth=0.8,
        alpha=0.6,
        zorder=2,
    )


def draw_ark_trajectory(ax: plt.Axes) -> None:
    """
    Draw a faint line connecting the three Ark points.
    Shows they are the result of tuning one variable (round duration).
    """
    ark_points = [p for p in POINTS if p.label.startswith('Ark')]
    # Sort by x-value (operational fees) to connect in order
    ark_points_sorted = sorted(ark_points, key=lambda p: p.x)
    
    if len(ark_points_sorted) >= 2:
        x_coords = [p.x for p in ark_points_sorted]
        y_coords = [p.y for p in ark_points_sorted]
        
        ax.plot(
            x_coords,
            y_coords,
            color='grey',
            linestyle='-',
            linewidth=0.5,
            alpha=0.3,
            zorder=1,
        )


def add_simulation_context_box(ax: plt.Axes) -> None:
    """
    Add a text box with simulation parameters in the center-right area.
    """
    context_text = (
        "Simulation Parameters\n"
        "• Users: 1,000 (91% Consumer / 4% Merchant)\n"
        "• Duration: 30 Days\n"
        "• Total Volume: ~37 BTC\n"
        "• Traffic: Poisson + LogNormal"
    )
    
    # Get axis limits to position box
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    
    # Position in center-right (y=0.6 relative to axes)
    box_x = xlim[1] * 0.65  # 65% across x-axis
    box_y = ylim[0] + (ylim[1] - ylim[0]) * 0.6  # 60% up y-axis (center-right)
    
    ax.text(
        box_x,
        box_y,
        context_text,
        bbox=dict(
            boxstyle='round,pad=0.8',
            facecolor='white',
            edgecolor='grey',
            linewidth=1.0,
            alpha=0.85,  # Semi-transparent so grid lines show through slightly
        ),
        fontsize=9,
        verticalalignment='center',
        horizontalalignment='left',
        zorder=20,
    )


def plot_points(ax: plt.Axes) -> None:
    """Plot all data points with their specified styles."""
    for point in POINTS:
        scatter_kwargs = {
            'x': point.x,
            'y': point.y,
            'c': point.color,
            'marker': point.marker,
            's': 100,
            'alpha': point.alpha,
            'label': point.label,
            'zorder': 10,
        }
        
        # Only set edgecolors for filled markers
        if point.marker != 'x':
            scatter_kwargs['edgecolors'] = 'white'
            scatter_kwargs['linewidths'] = 1.0
        else:
            scatter_kwargs['linewidths'] = 1.5
        
        ax.scatter(**scatter_kwargs)


def main() -> None:
    """Generate and save the clean, uncluttered Pareto scatter plot."""
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 7))
    
    # Set axis limits first (needed for crosshairs calculation)
    max_x = max(p.x for p in POINTS) * 1.15
    max_y = max(p.y for p in POINTS) * 1.15  # Increased padding for headroom above Legacy points
    ax.set_xlim(left=-0.005, right=max_x)  # Negative left limit to show x=0 marker fully
    ax.set_ylim(bottom=0, top=max_y)
    
    # Draw trajectory first (lowest zorder)
    draw_ark_trajectory(ax)
    
    # Draw crosshairs from Legacy (Optimized)
    legacy_opt = next(p for p in POINTS if 'Legacy (Optimized)' in p.label)
    draw_crosshairs(ax, legacy_opt)
    
    # Plot points on top
    plot_points(ax)
    
    # Add simulation context box
    add_simulation_context_box(ax)
    
    # Enhanced formatting
    ax.set_title(
        "Capital Efficiency vs. Operational Cost",
        fontsize=18,
        fontweight="bold",
        pad=20,
    )
    ax.set_xlabel(
        "Operational Fees (BTC) $\\leftarrow$ Lower is Better",
        fontsize=13,
        fontweight='medium',
    )
    ax.set_ylabel(
        "Liquidity Cost (BTC-Days) $\\downarrow$ Lower is Better",
        fontsize=13,
        fontweight='medium',
    )
    
    ax.grid(alpha=0.3, linestyle='-', linewidth=0.5)
    
    # Legend in upper right to clear top-left corner
    ax.legend(
        loc="upper right",
        frameon=True,
        fontsize=10,
        framealpha=0.95,
        edgecolor='lightgrey',
    )
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "pareto_final_clean.png"
    plt.tight_layout(pad=2.0)  # Tighter layout
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    
    print(f"Clean Pareto chart saved to {output_path}")


if __name__ == "__main__":
    main()
