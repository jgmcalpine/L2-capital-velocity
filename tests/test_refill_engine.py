"""Tests for the Legacy Refill Engine with JIT/Splicing capability."""

import pytest

from src.config import (
    LEGACY_CHANNEL_CAPACITY,
    REBALANCE_COST_SATS,
    REBALANCE_LATENCY_SECONDS,
    REFILL_TARGET_PCT,
)
from src.engines.legacy_refill_engine import LegacyRefillEngine
from src.models import Transaction, TransactionType


SATS_PER_BTC: int = 100_000_000


class TestRefillTrigger:
    """Tests for refill triggering on LSP liquidity shortage."""

    def test_refill_trigger_external_inbound(self) -> None:
        """
        Create scenario where LSP has 0 inbound liquidity.
        Send payment. Assert payment succeeds AND fee/latency counters increase.
        """
        user_ids = [0]
        # Start with 0% LSP liquidity (all on user side)
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=0.0)

        # Verify LSP has no liquidity
        channel = engine.get_channel_state(0)
        assert channel["local"] == 0, "LSP should start with 0 local balance"

        # Try to receive external payment
        amount = 100_000
        tx = Transaction(
            tx_id="tx_refill_1",
            timestamp=1.0,
            sender_id=-1,  # External sender
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        # Transaction should succeed due to refill
        result = engine.process_transaction(tx)
        assert result is True, "Transaction should succeed after refill"

        # Verify operational stats
        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 1, "Should have 1 refill operation"
        assert stats["total_fees_btc"] == REBALANCE_COST_SATS / SATS_PER_BTC, (
            "Fees should equal one rebalance cost"
        )

        # Verify latency (avg = total / tx_count = 600 / 1 = 600)
        assert stats["avg_latency_seconds"] == REBALANCE_LATENCY_SECONDS, (
            "Average latency should equal one rebalance latency"
        )

    def test_refill_trigger_internal_receiver(self) -> None:
        """
        Test refill triggers for receiver leg of internal transaction.
        """
        # Alice (0) has funds, Bob (1) has no LSP liquidity
        user_ids = [0, 1]
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=0.0)

        # Give Alice some remote balance to send
        alice_channel = engine.get_channel_state(0)
        alice_channel["remote"] = 500_000  # Alice can send

        amount = 100_000
        tx = Transaction(
            tx_id="tx_internal_refill",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=amount,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)
        assert result is True, "Internal transfer should succeed after refill"

        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 1, "Should have 1 refill for receiver's channel"

    def test_refill_fills_to_target_pct(self) -> None:
        """
        Verify refill brings LSP balance up to REFILL_TARGET_PCT of capacity.
        """
        user_ids = [0]
        capacity = 1_000_000
        engine = LegacyRefillEngine(user_ids, channel_capacity=capacity, initial_split=0.0)

        # Send small inbound payment
        amount = 10_000
        tx = Transaction(
            tx_id="tx_target_pct",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        engine.process_transaction(tx)

        # After refill and payment, local should be target - amount
        channel = engine.get_channel_state(0)
        expected_local_after_refill = int(capacity * REFILL_TARGET_PCT)
        expected_local_after_payment = expected_local_after_refill - amount

        assert channel["local"] == expected_local_after_payment, (
            f"Local balance should be {expected_local_after_payment}, got {channel['local']}"
        )

    def test_refill_covers_large_transaction(self) -> None:
        """
        If transaction amount > target PCT, refill should cover the transaction.
        """
        user_ids = [0]
        capacity = 1_000_000
        target_amount = int(capacity * REFILL_TARGET_PCT)  # 500k

        engine = LegacyRefillEngine(user_ids, channel_capacity=capacity, initial_split=0.0)

        # Request more than target would provide
        amount = target_amount + 100_000  # 600k
        tx = Transaction(
            tx_id="tx_large",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine.process_transaction(tx)
        assert result is True, "Large transaction should succeed"

        # Local should be 0 after the payment (refilled to 600k, then paid out 600k)
        channel = engine.get_channel_state(0)
        assert channel["local"] == 0, "Local balance should be 0 after large payment"


class TestNoRefillForOutbound:
    """Tests verifying LSP doesn't refill for user liquidity shortages."""

    def test_no_refill_for_outbound_user_empty(self) -> None:
        """
        Set User balance to 0. Try to send.
        Assert payment fails and NO refill occurs (LSP won't pay to fix user's empty wallet).
        """
        user_ids = [0]
        # Start with 100% LSP liquidity (user has nothing)
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=1.0)

        channel = engine.get_channel_state(0)
        assert channel["remote"] == 0, "User should start with 0 remote balance"

        # Try to send outbound payment
        amount = 100_000
        tx = Transaction(
            tx_id="tx_no_refill_out",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,  # External receiver
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine.process_transaction(tx)
        assert result is False, "Transaction should fail - user has no funds"

        # Verify NO refill occurred
        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 0, "No refill should occur for outbound"
        assert stats["total_fees_btc"] == 0, "No fees should be paid"

    def test_no_refill_for_internal_sender_empty(self) -> None:
        """
        Test that internal transfer fails without refill when sender has no funds.
        """
        user_ids = [0, 1]
        # Both channels: LSP has all funds, users have nothing
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=1.0)

        amount = 100_000
        tx = Transaction(
            tx_id="tx_no_refill_internal",
            timestamp=1.0,
            sender_id=0,  # Has no remote balance
            receiver_id=1,
            amount_sats=amount,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)
        assert result is False, "Transaction should fail - sender has no funds"

        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 0, (
            "No refill should occur when sender can't pay"
        )


class TestRefillMetricsAccumulation:
    """Tests for proper accumulation of operational metrics."""

    def test_multiple_refills_accumulate_correctly(self) -> None:
        """
        Multiple refill operations should accumulate fees and latency.
        """
        user_ids = [0, 1]
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=0.0)

        # Give users remote balance so they can receive
        for uid in user_ids:
            engine.get_channel_state(uid)["remote"] = 500_000

        # Send two inbound payments to different users
        for i, receiver_id in enumerate(user_ids):
            tx = Transaction(
                tx_id=f"tx_multi_{i}",
                timestamp=float(i),
                sender_id=-1,
                receiver_id=receiver_id,
                amount_sats=100_000,
                tx_type=TransactionType.EXTERNAL_INBOUND,
            )
            engine.process_transaction(tx)

        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 2, "Should have 2 refills"
        assert stats["total_fees_btc"] == (2 * REBALANCE_COST_SATS) / SATS_PER_BTC

        # Avg latency = (2 * 600) / 2 = 600
        expected_avg_latency = REBALANCE_LATENCY_SECONDS
        assert stats["avg_latency_seconds"] == expected_avg_latency

    def test_no_refill_when_sufficient_liquidity(self) -> None:
        """
        No refill should occur when LSP already has enough liquidity.
        """
        user_ids = [0]
        # Start with 50% split - plenty of LSP liquidity
        engine = LegacyRefillEngine(user_ids, channel_capacity=1_000_000, initial_split=0.5)

        amount = 100_000
        tx = Transaction(
            tx_id="tx_no_refill_needed",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine.process_transaction(tx)
        assert result is True, "Transaction should succeed"

        stats = engine.get_operational_stats()
        assert stats["refill_count"] == 0, "No refill needed when liquidity is sufficient"
        assert stats["total_fees_btc"] == 0


class TestEngineInterface:
    """Tests for engine interface compliance."""

    def test_engine_name(self) -> None:
        """Assert engine returns correct name."""
        engine = LegacyRefillEngine([0])
        assert engine.get_name() == "LegacyRefill"

    def test_operational_stats_structure(self) -> None:
        """Verify operational stats has required keys."""
        engine = LegacyRefillEngine([0])
        stats = engine.get_operational_stats()

        assert "refill_count" in stats
        assert "total_fees_btc" in stats
        assert "avg_latency_seconds" in stats

    def test_tvl_includes_refilled_funds(self) -> None:
        """
        TVL should increase after refill since LSP injects external funds.
        """
        user_ids = [0]
        capacity = 1_000_000
        engine = LegacyRefillEngine(user_ids, channel_capacity=capacity, initial_split=0.0)

        initial_tvl = engine.get_current_tvl()
        assert initial_tvl == 0, "Initial TVL should be 0 with 0% split"

        # Trigger refill
        amount = 100_000
        tx = Transaction(
            tx_id="tx_tvl_refill",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        engine.process_transaction(tx)

        # After refill to target (500k) and payment (100k), local is 400k
        # But wait, refill adds to total capacity, so TVL calculation changes
        final_tvl = engine.get_current_tvl()
        expected_tvl = int(capacity * REFILL_TARGET_PCT) - amount  # 500k - 100k = 400k

        assert final_tvl == expected_tvl, f"Expected TVL {expected_tvl}, got {final_tvl}"

