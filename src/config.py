from dataclasses import dataclass, field
from typing import Dict


# Time constants
SECONDS_PER_DAY: int = 86400
SECONDS_PER_HOUR: int = 3600


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for the L2 Capital Velocity simulation."""

    # Random seed for reproducibility
    SEED: int = 42

    # User generation
    TOTAL_USERS: int = 100
    USER_DISTRIBUTION: Dict[str, float] = field(
        default_factory=lambda: {
            "MERCHANT": 0.05,
            "CONSUMER": 0.85,
            "HODLER": 0.10,
        }
    )

    # Traffic generation
    SIMULATION_DAYS: int = 30
    TARGET_TRANSACTIONS: int = 10_000
    INTERNAL_TX_RATIO: float = 0.20  # 20% internal, 80% external

    # Amount distribution (lognormal parameters tuned for ~25k sats mean)
    AMOUNT_MU: float = 9.8  # ln(mean) - sigma^2/2 ≈ 9.8 for mean ~25k
    AMOUNT_SIGMA: float = 1.2  # Controls spread; lower = tighter distribution

    # Day/night cycle parameters (hours in 24h format)
    PEAK_HOUR_START: int = 8  # 8 AM
    PEAK_HOUR_END: int = 20  # 8 PM
    PEAK_MULTIPLIER: float = 2.0  # Peak hours are 2x more likely

    # User type transaction weights (relative to population share)
    # To ensure consumers send more per-capita: weight/pop_share must be higher
    SENDER_WEIGHTS: Dict[str, float] = field(
        default_factory=lambda: {
            "MERCHANT": 0.02,  # Merchants rarely send (mostly receive)
            "CONSUMER": 0.93,  # Consumers send the most
            "HODLER": 0.05,  # Hodlers rarely transact
        }
    )
    RECEIVER_WEIGHTS: Dict[str, float] = field(
        default_factory=lambda: {
            "MERCHANT": 0.60,  # Merchants receive most payments
            "CONSUMER": 0.30,  # Consumers receive some (P2P)
            "HODLER": 0.10,  # Hodlers occasionally receive
        }
    )

    def __post_init__(self) -> None:
        total_prob = sum(self.USER_DISTRIBUTION.values())
        if not abs(total_prob - 1.0) < 1e-9:
            raise ValueError(
                f"USER_DISTRIBUTION probabilities must sum to 1.0, got {total_prob}"
            )

