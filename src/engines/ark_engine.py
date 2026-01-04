"""Ark protocol engine with pooled liquidity and round-based settlement."""

from typing import Dict, List

from src.config import (
    ARK_POOL_CAPACITY,
    ARK_ROUND_COST_SATS,
    ARK_ROUND_INTERVAL,
    LEGACY_CHANNEL_CAPACITY,
    LEGACY_INITIAL_SPLIT,
)
from src.engines.abstract_engine import AbstractLSPEngine
from src.models import Transaction, TransactionType


SATS_PER_BTC: int = 100_000_000


class ArkEngine(AbstractLSPEngine):
    """
    Models Ark protocol with pooled ASP liquidity and round-based settlement.

    Unlike Legacy Lightning where each user has an isolated channel, Ark uses
    a shared liquidity pool. Users share the ASP's outbound capacity, and
    internal transfers don't consume pool liquidity at all (zero-sum within ASP).

    Key advantages over Legacy:
    - Pool liquidity is shared across all users (capital efficient)
    - Internal transfers require no pool liquidity (instant, free)
    - Settlement happens in periodic rounds (batched on-chain)
    """

    def __init__(
        self,
        user_ids: List[int],
        pool_capacity: int = ARK_POOL_CAPACITY,
        user_initial_balance: int | None = None,
    ) -> None:
        """
        Initialize Ark engine with shared pool and user balances.

        Args:
            user_ids: List of user IDs to register.
            pool_capacity: Total ASP pool capacity in sats.
            user_initial_balance: Initial balance per user in sats.
                Defaults to LEGACY_CHANNEL_CAPACITY * (1 - LEGACY_INITIAL_SPLIT)
                for fair comparison with Legacy engine.
        """
        self._pool_capacity = pool_capacity
        self._pool_balance = pool_capacity

        # Default to same starting user funds as Legacy for fairness
        if user_initial_balance is None:
            user_initial_balance = int(
                LEGACY_CHANNEL_CAPACITY * (1 - LEGACY_INITIAL_SPLIT)
            )

        self._user_balances: Dict[int, int] = {
            user_id: user_initial_balance for user_id in user_ids
        }

        # Round tracking
        self._last_round_time: float = 0.0
        self._round_count: int = 0

        # For avg TVL tracking
        self._tvl_samples: List[int] = [pool_capacity]

    def process_transaction(self, tx: Transaction) -> bool:
        """
        Process a transaction through the Ark pool.

        Args:
            tx: The Transaction to process.

        Returns:
            True if successful, False if insufficient balance/liquidity.
        """
        self._check_round(tx.timestamp)

        if tx.tx_type == TransactionType.EXTERNAL_OUTBOUND:
            return self._process_external_outbound(tx.sender_id, tx.amount_sats)
        elif tx.tx_type == TransactionType.EXTERNAL_INBOUND:
            return self._process_external_inbound(tx.receiver_id, tx.amount_sats)
        elif tx.tx_type == TransactionType.INTERNAL:
            return self._process_internal(tx.sender_id, tx.receiver_id, tx.amount_sats)
        return False

    def _check_round(self, current_time: float) -> None:
        """
        Check if new settlement rounds have passed and update tracking.

        Args:
            current_time: Current simulation timestamp in seconds.
        """
        if current_time <= self._last_round_time:
            return

        elapsed = current_time - self._last_round_time
        rounds_passed = int(elapsed // ARK_ROUND_INTERVAL)

        if rounds_passed > 0:
            self._round_count += rounds_passed
            self._last_round_time += rounds_passed * ARK_ROUND_INTERVAL
            self._tvl_samples.append(self._pool_balance)

    def _process_external_outbound(self, sender_id: int, amount: int) -> bool:
        """
        Process user sending to external world.

        Requires both user balance AND pool liquidity (ASP pays the world).
        """
        user_balance = self._user_balances.get(sender_id)
        if user_balance is None or user_balance < amount:
            return False

        if self._pool_balance < amount:
            return False

        self._user_balances[sender_id] -= amount
        self._pool_balance -= amount
        return True

    def _process_external_inbound(self, receiver_id: int, amount: int) -> bool:
        """
        Process external world sending to user.

        ASP receives real BTC (pool grows) and credits user's virtual balance.
        No cap enforced - ASP can always accept inbound liquidity.
        """
        if receiver_id not in self._user_balances:
            return False

        self._user_balances[receiver_id] += amount
        self._pool_balance += amount
        return True

    def _process_internal(self, sender_id: int, receiver_id: int, amount: int) -> bool:
        """
        Process internal transfer between two Ark users.

        Key advantage: NO pool liquidity required! Funds stay inside ASP,
        just moving between user virtual balances.
        """
        sender_balance = self._user_balances.get(sender_id)
        if sender_balance is None or sender_balance < amount:
            return False

        if receiver_id not in self._user_balances:
            return False

        self._user_balances[sender_id] -= amount
        self._user_balances[receiver_id] += amount
        return True

    def get_current_tvl(self) -> float:
        """
        Get the ASP's locked capital (pool balance).

        Returns:
            Current pool balance in sats (as float for interface compat).
        """
        return float(self._pool_balance)

    def get_name(self) -> str:
        """Returns the engine identifier."""
        return "Ark"

    def get_operational_stats(self) -> Dict[str, float]:
        """
        Get operational statistics for round-based settlement.

        Returns:
            Dictionary with:
                - round_count: Number of settlement rounds
                - total_fees_btc: Total on-chain fees for rounds
                - avg_tvl: Average TVL across the simulation
        """
        total_fees_sats = self._round_count * ARK_ROUND_COST_SATS
        avg_tvl = sum(self._tvl_samples) / len(self._tvl_samples) if self._tvl_samples else 0.0

        return {
            "round_count": float(self._round_count),
            "total_fees_btc": total_fees_sats / SATS_PER_BTC,
            "avg_tvl": avg_tvl,
        }

    def get_user_balance(self, user_id: int) -> int | None:
        """
        Get the current balance for a specific user.

        Args:
            user_id: The user ID to look up.

        Returns:
            User's balance in sats or None if user not found.
        """
        return self._user_balances.get(user_id)

    def get_pool_balance(self) -> int:
        """Get the current pool balance."""
        return self._pool_balance

    def get_total_user_count(self) -> int:
        """Get the number of registered users."""
        return len(self._user_balances)

