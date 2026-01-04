"""Legacy Lightning Network engine with JIT/Splicing refill capability."""

from typing import Dict, List

from src.config import (
    LEGACY_CHANNEL_CAPACITY,
    LEGACY_INITIAL_SPLIT,
    REBALANCE_COST_SATS,
    REBALANCE_LATENCY_SECONDS,
    REFILL_TARGET_PCT,
)
from src.engines.legacy_engine import LegacyEngine
from src.models import Transaction, TransactionType


SATS_PER_BTC: int = 100_000_000


class LegacyRefillEngine(LegacyEngine):
    """
    Models Lightning Network channels with JIT/Splicing liquidity management.

    Extends LegacyEngine by adding automatic refill capability when LSP
    liquidity is insufficient for inbound transactions. Tracks operational
    costs including fees and latency incurred from refill operations.
    """

    def __init__(
        self,
        user_ids: List[int],
        channel_capacity: int = LEGACY_CHANNEL_CAPACITY,
        initial_split: float = LEGACY_INITIAL_SPLIT,
    ) -> None:
        """
        Initialize channels for all users with refill tracking.

        Args:
            user_ids: List of user IDs to create channels for.
            channel_capacity: Total capacity per channel in sats.
            initial_split: Fraction of capacity on LSP side (0.0 to 1.0).
        """
        super().__init__(user_ids, channel_capacity, initial_split)

        # Operational metrics tracking
        self._total_fees_paid: int = 0  # sats
        self._total_latency_seconds: int = 0
        self._refill_count: int = 0
        self._total_tx_count: int = 0

    def process_transaction(self, tx: Transaction) -> bool:
        """
        Process a transaction, refilling LSP liquidity if needed.

        For inbound transactions or the receiver leg of internal transactions,
        if LSP liquidity is insufficient, performs a JIT refill before processing.

        Args:
            tx: The Transaction to process.

        Returns:
            True if successful, False if insufficient user balance.
        """
        self._total_tx_count += 1

        # Step 1: Analyze liquidity and potentially refill
        if tx.tx_type == TransactionType.EXTERNAL_INBOUND:
            self._maybe_refill_for_receiver(tx.receiver_id, tx.amount_sats)
        elif tx.tx_type == TransactionType.INTERNAL:
            # Check sender has funds first - don't refill if sender can't pay
            sender_channel = self._channels.get(tx.sender_id)
            if sender_channel is not None and sender_channel["remote"] >= tx.amount_sats:
                # Sender can pay, so check if we need to refill receiver's channel
                self._maybe_refill_for_receiver(tx.receiver_id, tx.amount_sats)

        # Step 2: Execute the transaction via parent implementation
        return super().process_transaction(tx)

    def _maybe_refill_for_receiver(self, receiver_id: int, amount: int) -> None:
        """
        Refill receiver's channel if LSP lacks liquidity.

        Calculates the amount needed to reach REFILL_TARGET_PCT of capacity,
        ensuring it covers the current transaction amount. Models JIT channel
        open or splice-in by increasing LSP's local balance.

        Args:
            receiver_id: The user ID receiving funds.
            amount: The transaction amount in sats.
        """
        channel = self._channels.get(receiver_id)
        if channel is None:
            return

        current_local = channel["local"]

        # Check if LSP has enough liquidity for this transaction
        if current_local >= amount:
            return  # No refill needed

        # Calculate target local balance (50% of capacity by default)
        target_local = int(self._channel_capacity * REFILL_TARGET_PCT)

        # Ensure we have enough for this transaction
        target_local = max(target_local, amount)

        # Calculate amount to add
        amount_to_add = target_local - current_local

        if amount_to_add <= 0:
            return

        # Perform the refill: increase local balance
        # Models JIT channel open or splice-in where LSP injects external funds
        channel["local"] += amount_to_add

        # Track operational costs
        self._total_fees_paid += REBALANCE_COST_SATS
        self._total_latency_seconds += REBALANCE_LATENCY_SECONDS
        self._refill_count += 1

    def get_operational_stats(self) -> Dict[str, float]:
        """
        Get operational statistics for refill operations.

        Returns:
            Dictionary with:
                - refill_count: Number of refill operations performed
                - total_fees_btc: Total fees paid in BTC
                - avg_latency_seconds: Average latency per transaction
        """
        avg_latency = (
            self._total_latency_seconds / self._total_tx_count
            if self._total_tx_count > 0
            else 0.0
        )

        return {
            "refill_count": float(self._refill_count),
            "total_fees_btc": self._total_fees_paid / SATS_PER_BTC,
            "avg_latency_seconds": avg_latency,
        }

    def get_name(self) -> str:
        """Returns the engine identifier."""
        return "LegacyRefill"

