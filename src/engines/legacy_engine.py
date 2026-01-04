"""Legacy Lightning Network engine with static channel management."""

from typing import Dict, List, TypedDict

from src.config import LEGACY_CHANNEL_CAPACITY, LEGACY_INITIAL_SPLIT
from src.engines.abstract_engine import AbstractLSPEngine
from src.models import Transaction, TransactionType


class ChannelBalance(TypedDict):
    """Type definition for channel balance state."""

    local: int  # LSP-side balance (sats)
    remote: int  # User-side balance (sats)


class LegacyEngine(AbstractLSPEngine):
    """
    Models static Lightning Network channels between LSP and users.

    Each user has a single channel with fixed capacity. Channels are initialized
    with a configurable split between LSP (local) and user (remote) balances.
    Transactions can fail due to insufficient balance on either side.
    """

    def __init__(
        self,
        user_ids: List[int],
        channel_capacity: int = LEGACY_CHANNEL_CAPACITY,
        initial_split: float = LEGACY_INITIAL_SPLIT,
    ) -> None:
        """
        Initialize channels for all users.

        Args:
            user_ids: List of user IDs to create channels for.
            channel_capacity: Total capacity per channel in sats.
            initial_split: Fraction of capacity on LSP side (0.0 to 1.0).
        """
        self._channel_capacity = channel_capacity
        self._initial_split = initial_split

        local_balance = int(channel_capacity * initial_split)
        remote_balance = channel_capacity - local_balance

        self._channels: Dict[int, ChannelBalance] = {
            user_id: {"local": local_balance, "remote": remote_balance}
            for user_id in user_ids
        }

    def process_transaction(self, tx: Transaction) -> bool:
        """
        Process a transaction through the Lightning Network channels.

        Args:
            tx: The Transaction to process.

        Returns:
            True if successful, False if insufficient balance.
        """
        if tx.tx_type == TransactionType.EXTERNAL_OUTBOUND:
            return self._process_external_outbound(tx.sender_id, tx.amount_sats)
        elif tx.tx_type == TransactionType.EXTERNAL_INBOUND:
            return self._process_external_inbound(tx.receiver_id, tx.amount_sats)
        elif tx.tx_type == TransactionType.INTERNAL:
            return self._process_internal(tx.sender_id, tx.receiver_id, tx.amount_sats)
        return False

    def _process_external_outbound(self, sender_id: int, amount: int) -> bool:
        """
        Process user sending to external world.

        User's remote balance decreases, LSP's local balance increases.
        """
        channel = self._channels.get(sender_id)
        if channel is None or channel["remote"] < amount:
            return False

        channel["remote"] -= amount
        channel["local"] += amount
        return True

    def _process_external_inbound(self, receiver_id: int, amount: int) -> bool:
        """
        Process external world sending to user.

        LSP's local balance decreases, user's remote balance increases.
        """
        channel = self._channels.get(receiver_id)
        if channel is None or channel["local"] < amount:
            return False

        channel["local"] -= amount
        channel["remote"] += amount
        return True

    def _process_internal(self, sender_id: int, receiver_id: int, amount: int) -> bool:
        """
        Process internal transfer between two users via LSP.

        Requires sender to have sufficient remote balance AND
        receiver's channel to have sufficient local (LSP) balance.
        """
        sender_channel = self._channels.get(sender_id)
        receiver_channel = self._channels.get(receiver_id)

        if sender_channel is None or receiver_channel is None:
            return False

        if sender_channel["remote"] < amount or receiver_channel["local"] < amount:
            return False

        # Update sender channel: user pays, LSP receives
        sender_channel["remote"] -= amount
        sender_channel["local"] += amount

        # Update receiver channel: LSP pays, user receives
        receiver_channel["local"] -= amount
        receiver_channel["remote"] += amount

        return True

    def get_current_tvl(self) -> float:
        """
        Get the total LSP-side liquidity across all channels.

        Returns:
            Sum of all local balances (in sats, as float for interface compat).
        """
        return float(sum(channel["local"] for channel in self._channels.values()))

    def get_name(self) -> str:
        """Returns the engine identifier."""
        return "Legacy"

    def get_channel_state(self, user_id: int) -> ChannelBalance | None:
        """
        Get the current channel state for a specific user.

        Args:
            user_id: The user ID to look up.

        Returns:
            ChannelBalance dict or None if user not found.
        """
        return self._channels.get(user_id)

    def get_total_user_count(self) -> int:
        """Get the number of users with channels."""
        return len(self._channels)

