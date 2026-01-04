from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for the L2 Capital Velocity simulation."""

    SEED: int = 42
    TOTAL_USERS: int = 100
    USER_DISTRIBUTION: Dict[str, float] = field(
        default_factory=lambda: {
            "MERCHANT": 0.05,
            "CONSUMER": 0.85,
            "HODLER": 0.10,
        }
    )

    def __post_init__(self) -> None:
        total_prob = sum(self.USER_DISTRIBUTION.values())
        if not abs(total_prob - 1.0) < 1e-9:
            raise ValueError(
                f"USER_DISTRIBUTION probabilities must sum to 1.0, got {total_prob}"
            )

