"""Traffic generation module for L2 Capital Velocity simulation."""

import uuid
from typing import Dict, List

import numpy as np

from src.config import SECONDS_PER_DAY, SECONDS_PER_HOUR, SimulationConfig
from src.models import Transaction, TransactionType, User, UserType


class TrafficGenerator:
    """Generates synthetic transaction traffic based on user population."""

    EXTERNAL_ENTITY_ID: int = -1

    def __init__(self, config: SimulationConfig) -> None:
        """
        Initialize traffic generator with configuration.

        Args:
            config: SimulationConfig with traffic generation parameters.
        """
        self.config = config
        self.rng = np.random.default_rng(config.SEED)
        self._simulation_duration = config.SIMULATION_DAYS * SECONDS_PER_DAY

    def generate_month_of_traffic(self, users: List[User]) -> List[Transaction]:
        """
        Generate a month of synthetic transaction traffic.

        Uses a Poisson process with day/night weighting for arrival times,
        lognormal distribution for amounts, and user-type-based selection
        for participants.

        Args:
            users: List of User objects to participate in transactions.

        Returns:
            List of Transaction objects sorted by timestamp.
        """
        if not users:
            return []

        # Build user indices by type for efficient selection
        users_by_type = self._build_user_type_index(users)

        # Generate transaction timestamps using Poisson process with day/night cycle
        timestamps = self._generate_timestamps()

        transactions: List[Transaction] = []

        for timestamp in timestamps:
            tx = self._generate_single_transaction(timestamp, users, users_by_type)
            transactions.append(tx)

        return transactions

    def _build_user_type_index(
        self, users: List[User]
    ) -> Dict[UserType, List[User]]:
        """Group users by their type for weighted selection."""
        users_by_type: Dict[UserType, List[User]] = {
            user_type: [] for user_type in UserType
        }
        for user in users:
            users_by_type[user.user_type].append(user)
        return users_by_type

    def _generate_timestamps(self) -> List[float]:
        """
        Generate transaction timestamps using Poisson process with day/night weighting.

        Uses thinning (rejection sampling) on a non-homogeneous Poisson process
        to achieve higher transaction rates during peak hours.
        """
        # For thinning: we generate at max_rate, then accept with probability p(t)
        # Expected events = max_rate * duration * avg_acceptance
        # So: max_rate = TARGET / (duration * avg_acceptance)
        avg_acceptance = self._calculate_average_intensity()
        max_rate = self.config.TARGET_TRANSACTIONS / (
            self._simulation_duration * avg_acceptance
        )

        timestamps: List[float] = []
        current_time = 0.0

        while current_time < self._simulation_duration:
            # Generate candidate inter-arrival time using max rate
            inter_arrival = self.rng.exponential(1.0 / max_rate)
            current_time += inter_arrival

            if current_time >= self._simulation_duration:
                break

            # Accept/reject based on time-varying intensity
            intensity_ratio = self._get_time_intensity(current_time)
            if self.rng.random() < intensity_ratio:
                timestamps.append(current_time)

        return timestamps

    def _calculate_average_intensity(self) -> float:
        """Calculate average acceptance probability over a 24-hour cycle."""
        # Peak hours have acceptance probability 1.0
        # Off-peak hours have acceptance probability 1/PEAK_MULTIPLIER
        peak_hours = self.config.PEAK_HOUR_END - self.config.PEAK_HOUR_START
        off_peak_hours = 24 - peak_hours

        # Average acceptance rate
        avg_acceptance = (
            peak_hours * 1.0 + off_peak_hours * (1.0 / self.config.PEAK_MULTIPLIER)
        ) / 24
        return avg_acceptance

    def _get_time_intensity(self, timestamp: float) -> float:
        """
        Get intensity multiplier for a given timestamp.

        Returns value between 0 and 1, where 1 = peak rate.
        """
        hour_of_day = (timestamp % SECONDS_PER_DAY) / SECONDS_PER_HOUR

        if self.config.PEAK_HOUR_START <= hour_of_day < self.config.PEAK_HOUR_END:
            return 1.0  # Peak hours: full intensity
        else:
            return 1.0 / self.config.PEAK_MULTIPLIER  # Off-peak: reduced

    def _generate_single_transaction(
        self,
        timestamp: float,
        users: List[User],
        users_by_type: Dict[UserType, List[User]],
    ) -> Transaction:
        """Generate a single transaction at the given timestamp."""
        tx_type = self._select_transaction_type()
        amount = self._generate_amount()
        sender_id, receiver_id = self._select_participants(
            tx_type, users, users_by_type
        )

        return Transaction(
            tx_id=str(uuid.uuid4()),
            timestamp=timestamp,
            sender_id=sender_id,
            receiver_id=receiver_id,
            amount_sats=amount,
            tx_type=tx_type,
        )

    def _select_transaction_type(self) -> TransactionType:
        """Select transaction type based on configured ratios."""
        if self.rng.random() < self.config.INTERNAL_TX_RATIO:
            return TransactionType.INTERNAL
        else:
            # External: 50/50 split between inbound and outbound
            if self.rng.random() < 0.5:
                return TransactionType.EXTERNAL_INBOUND
            else:
                return TransactionType.EXTERNAL_OUTBOUND

    def _generate_amount(self) -> int:
        """Generate transaction amount using lognormal distribution."""
        amount = self.rng.lognormal(
            mean=self.config.AMOUNT_MU,
            sigma=self.config.AMOUNT_SIGMA,
        )
        # Clamp to reasonable range: min 100 sats, max 10M sats
        amount = max(100, min(int(amount), 10_000_000))
        return amount

    def _select_participants(
        self,
        tx_type: TransactionType,
        users: List[User],
        users_by_type: Dict[UserType, List[User]],
    ) -> tuple[int, int]:
        """
        Select sender and receiver based on transaction type and user weights.

        Returns:
            Tuple of (sender_id, receiver_id).
        """
        if tx_type == TransactionType.EXTERNAL_INBOUND:
            receiver = self._select_user_weighted(
                users, users_by_type, self.config.RECEIVER_WEIGHTS
            )
            return self.EXTERNAL_ENTITY_ID, receiver.user_id

        elif tx_type == TransactionType.EXTERNAL_OUTBOUND:
            sender = self._select_user_weighted(
                users, users_by_type, self.config.SENDER_WEIGHTS
            )
            return sender.user_id, self.EXTERNAL_ENTITY_ID

        else:  # INTERNAL
            sender = self._select_user_weighted(
                users, users_by_type, self.config.SENDER_WEIGHTS
            )
            # Ensure receiver is different from sender
            receiver = self._select_user_weighted(
                users, users_by_type, self.config.RECEIVER_WEIGHTS
            )
            # Retry if same user selected (rare with 100+ users)
            attempts = 0
            while receiver.user_id == sender.user_id and attempts < 10:
                receiver = self._select_user_weighted(
                    users, users_by_type, self.config.RECEIVER_WEIGHTS
                )
                attempts += 1

            # Fallback: pick any other user
            if receiver.user_id == sender.user_id:
                other_users = [u for u in users if u.user_id != sender.user_id]
                if other_users:
                    receiver = self.rng.choice(other_users)

            return sender.user_id, receiver.user_id

    def _select_user_weighted(
        self,
        users: List[User],
        users_by_type: Dict[UserType, List[User]],
        type_weights: Dict[str, float],
    ) -> User:
        """
        Select a user based on user type weights.

        First selects a user type based on weights, then uniformly
        selects a user of that type.
        """
        # Filter to types that have users
        available_types = [
            ut for ut in UserType if users_by_type.get(ut)
        ]

        if not available_types:
            return self.rng.choice(users)

        # Calculate weights for available types
        weights = np.array([
            type_weights.get(ut.value, 0.0) for ut in available_types
        ])

        # Handle case where all weights are zero
        if weights.sum() == 0:
            weights = np.ones(len(available_types))

        weights = weights / weights.sum()

        # Select user type index (use integer index to avoid numpy string conversion)
        type_idx = self.rng.choice(len(available_types), p=weights)
        selected_type = available_types[type_idx]

        # Select user from that type
        user_list = users_by_type[selected_type]
        user_idx = self.rng.integers(len(user_list))
        return user_list[user_idx]

