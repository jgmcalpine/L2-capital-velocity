from typing import List

import numpy as np

from src.config import SimulationConfig
from src.models import User, UserType


def generate_users(config: SimulationConfig) -> List[User]:
    """
    Generate a deterministic population of users based on config.

    Args:
        config: SimulationConfig containing SEED, TOTAL_USERS, and USER_DISTRIBUTION.

    Returns:
        List of User objects with probabilistically assigned types.
    """
    rng = np.random.default_rng(config.SEED)

    user_types = list(config.USER_DISTRIBUTION.keys())
    probabilities = list(config.USER_DISTRIBUTION.values())

    type_indices = rng.choice(
        len(user_types),
        size=config.TOTAL_USERS,
        p=probabilities,
    )

    users = [
        User(user_id=i, user_type=UserType(user_types[type_idx]))
        for i, type_idx in enumerate(type_indices)
    ]

    return users

