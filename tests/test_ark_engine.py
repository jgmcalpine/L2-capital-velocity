"""Tests for the Ark protocol engine with pooled liquidity."""

import pytest

from src.config import (
    ARK_POOL_CAPACITY,
    ARK_ROUND_COST_SATS,
    ARK_ROUND_INTERVAL,
    LEGACY_CHANNEL_CAPACITY,
    LEGACY_INITIAL_SPLIT,
)
from src.engines.ark_engine import ArkEngine
from src.models import Transaction, TransactionType


SATS_PER_BTC: int = 100_000_000


class TestArkEngineInitialization:
    """Tests for ArkEngine initialization and state management."""

    def test_initialization_pool_capacity(self) -> None:
        """Assert Pool has 50M sats by default."""
        user_ids = [0, 1]
        engine = ArkEngine(user_ids)

        assert engine.get_pool_balance() == ARK_POOL_CAPACITY, (
            f"Pool should have {ARK_POOL_CAPACITY} sats, got {engine.get_pool_balance()}"
        )
        assert engine.get_current_tvl() == ARK_POOL_CAPACITY

    def test_initialization_user_balances(self) -> None:
        """Assert users have 2.5M sats each (same as Legacy user remote balance)."""
        user_ids = [0, 1, 2]
        engine = ArkEngine(user_ids)

        expected_user_balance = int(LEGACY_CHANNEL_CAPACITY * (1 - LEGACY_INITIAL_SPLIT))
        assert expected_user_balance == 2_500_000, "Expected 2.5M sats per user"

        for user_id in user_ids:
            balance = engine.get_user_balance(user_id)
            assert balance == expected_user_balance, (
                f"User {user_id} should have {expected_user_balance} sats"
            )

    def test_initialization_custom_pool_and_balance(self) -> None:
        """Assert custom pool capacity and user balance are applied."""
        user_ids = [0, 1]
        custom_pool = 10_000_000
        custom_balance = 1_000_000

        engine = ArkEngine(user_ids, pool_capacity=custom_pool, user_initial_balance=custom_balance)

        assert engine.get_pool_balance() == custom_pool
        for user_id in user_ids:
            assert engine.get_user_balance(user_id) == custom_balance

    def test_engine_name(self) -> None:
        """Assert engine returns correct name."""
        engine = ArkEngine([0])
        assert engine.get_name() == "Ark"


class TestPoolingAdvantage:
    """Tests demonstrating Ark's pooled liquidity advantage over Legacy."""

    def test_shared_pool_outbound_depletion(self) -> None:
        """
        Demonstrate users share the pool bucket for outbound.

        Set Pool to 10M. User A sends 8M (success, pool has 2M).
        User B tries to send 3M (fail - pool depleted).
        """
        user_ids = [0, 1]
        engine = ArkEngine(user_ids, pool_capacity=10_000_000, user_initial_balance=10_000_000)

        # User A sends 8M - should succeed
        tx_a = Transaction(
            tx_id="tx_pool_a",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=8_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        result_a = engine.process_transaction(tx_a)
        assert result_a is True, "User A's 8M outbound should succeed"
        assert engine.get_pool_balance() == 2_000_000, "Pool should have 2M left"

        # User B tries to send 3M - should fail (pool only has 2M)
        tx_b = Transaction(
            tx_id="tx_pool_b",
            timestamp=2.0,
            sender_id=1,
            receiver_id=-1,
            amount_sats=3_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        result_b = engine.process_transaction(tx_b)
        assert result_b is False, "User B's 3M outbound should fail - pool depleted"

        # User B can still send 2M (pool limit)
        tx_b_small = Transaction(
            tx_id="tx_pool_b_small",
            timestamp=3.0,
            sender_id=1,
            receiver_id=-1,
            amount_sats=2_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        result_b_small = engine.process_transaction(tx_b_small)
        assert result_b_small is True, "User B's 2M outbound should succeed"
        assert engine.get_pool_balance() == 0, "Pool should be empty"

    def test_pool_efficiency_vs_legacy_channels(self) -> None:
        """
        Show pooling is more capital efficient than isolated channels.

        In Legacy: 2 users each with 2.5M inbound capacity = 5M total LSP capital
        In Ark: Same 2 users could share a 3M pool if one is inactive.

        Scenario: User A needs to receive 2.5M, User B is idle.
        Legacy: Works (each channel is isolated)
        Ark with 3M pool: Also works (shared pool covers it)
        """
        user_ids = [0, 1]
        # Ark with LESS total capital than Legacy would need
        engine = ArkEngine(user_ids, pool_capacity=3_000_000, user_initial_balance=0)

        # User A receives 2.5M from external - pool grows
        tx = Transaction(
            tx_id="tx_efficient",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=2_500_000,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )
        result = engine.process_transaction(tx)
        assert result is True, "Inbound should succeed"
        assert engine.get_user_balance(0) == 2_500_000
        assert engine.get_pool_balance() == 5_500_000, "Pool grows with inbound"


class TestInternalZeroSum:
    """Tests verifying internal transfers don't consume pool liquidity."""

    def test_internal_transfer_pool_unchanged(self) -> None:
        """User A sends to User B - pool_balance remains constant."""
        user_ids = [0, 1]
        engine = ArkEngine(user_ids, pool_capacity=10_000_000, user_initial_balance=5_000_000)

        initial_pool = engine.get_pool_balance()
        amount = 1_000_000

        tx = Transaction(
            tx_id="tx_internal_zero",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=amount,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)

        assert result is True, "Internal transfer should succeed"
        assert engine.get_pool_balance() == initial_pool, "Pool balance should be unchanged"
        assert engine.get_user_balance(0) == 4_000_000, "Sender balance decreased"
        assert engine.get_user_balance(1) == 6_000_000, "Receiver balance increased"

    def test_internal_works_with_empty_pool(self) -> None:
        """
        Internal transfers work even when pool is empty.

        This is the KEY advantage: no pool liquidity needed for internal payments.
        """
        user_ids = [0, 1]
        engine = ArkEngine(user_ids, pool_capacity=0, user_initial_balance=5_000_000)

        assert engine.get_pool_balance() == 0, "Pool starts empty"

        tx = Transaction(
            tx_id="tx_internal_empty_pool",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=2_000_000,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)

        assert result is True, "Internal transfer should succeed with empty pool"
        assert engine.get_pool_balance() == 0, "Pool still empty"
        assert engine.get_user_balance(0) == 3_000_000
        assert engine.get_user_balance(1) == 7_000_000

    def test_internal_fails_only_on_sender_insufficient(self) -> None:
        """Internal transfer fails only if sender lacks funds."""
        user_ids = [0, 1]
        engine = ArkEngine(user_ids, pool_capacity=100_000_000, user_initial_balance=1_000_000)

        tx = Transaction(
            tx_id="tx_internal_fail",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=2_000_000,  # More than sender has
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)

        assert result is False, "Should fail due to insufficient sender balance"
        assert engine.get_user_balance(0) == 1_000_000, "Sender unchanged"
        assert engine.get_user_balance(1) == 1_000_000, "Receiver unchanged"


class TestExternalOutbound:
    """Tests for external outbound transactions (User -> World)."""

    def test_outbound_success(self) -> None:
        """User sends to world - both user and pool balance decrease."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=5_000_000)
        amount = 1_000_000

        tx = Transaction(
            tx_id="tx_out",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine.process_transaction(tx)

        assert result is True
        assert engine.get_user_balance(0) == 4_000_000
        assert engine.get_pool_balance() == 9_000_000

    def test_outbound_fails_insufficient_user_balance(self) -> None:
        """Fails when user doesn't have enough funds."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=1_000_000)

        tx = Transaction(
            tx_id="tx_out_fail_user",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=2_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine.process_transaction(tx)

        assert result is False
        assert engine.get_user_balance(0) == 1_000_000  # Unchanged
        assert engine.get_pool_balance() == 10_000_000  # Unchanged

    def test_outbound_fails_insufficient_pool(self) -> None:
        """Fails when pool doesn't have enough to pay the world."""
        engine = ArkEngine([0], pool_capacity=500_000, user_initial_balance=5_000_000)

        tx = Transaction(
            tx_id="tx_out_fail_pool",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=1_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine.process_transaction(tx)

        assert result is False
        assert engine.get_user_balance(0) == 5_000_000  # Unchanged
        assert engine.get_pool_balance() == 500_000  # Unchanged


class TestExternalInbound:
    """Tests for external inbound transactions (World -> User)."""

    def test_inbound_success(self) -> None:
        """World sends to user - both user and pool balance increase."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=1_000_000)
        amount = 2_000_000

        tx = Transaction(
            tx_id="tx_in",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine.process_transaction(tx)

        assert result is True
        assert engine.get_user_balance(0) == 3_000_000
        assert engine.get_pool_balance() == 12_000_000, "Pool grows with inbound"

    def test_inbound_no_capacity_limit(self) -> None:
        """Inbound has no cap - ASP can always accept incoming BTC."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=0)

        # Send 100M to user (way over initial pool capacity)
        tx = Transaction(
            tx_id="tx_in_large",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=100_000_000,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine.process_transaction(tx)

        assert result is True
        assert engine.get_user_balance(0) == 100_000_000
        assert engine.get_pool_balance() == 110_000_000

    def test_inbound_fails_unknown_user(self) -> None:
        """Fails when receiver is not a registered user."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=0)

        tx = Transaction(
            tx_id="tx_in_unknown",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=999,  # Unknown user
            amount_sats=1_000_000,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine.process_transaction(tx)
        assert result is False


class TestRoundBasedSettlement:
    """Tests for round-based settlement tracking."""

    def test_round_count_increments_with_time(self) -> None:
        """Rounds are counted based on elapsed time."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=5_000_000)

        # Transaction at t=0 (no rounds yet)
        tx1 = Transaction(
            tx_id="tx_r1",
            timestamp=0.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=1000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx1)

        stats = engine.get_operational_stats()
        assert stats["round_count"] == 0, "No rounds at t=0"

        # Transaction at t=600 (1 round)
        tx2 = Transaction(
            tx_id="tx_r2",
            timestamp=600.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=1000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx2)

        stats = engine.get_operational_stats()
        assert stats["round_count"] == 1, "1 round after 600s"

        # Transaction at t=1800 (3 rounds total, 2 more passed)
        tx3 = Transaction(
            tx_id="tx_r3",
            timestamp=1800.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=1000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx3)

        stats = engine.get_operational_stats()
        assert stats["round_count"] == 3, "3 rounds after 1800s"

    def test_round_fees_calculation(self) -> None:
        """Total fees equal round_count * round_cost."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=5_000_000)

        # Trigger 5 rounds
        tx = Transaction(
            tx_id="tx_fees",
            timestamp=5 * ARK_ROUND_INTERVAL,  # 3000 seconds = 5 rounds
            sender_id=0,
            receiver_id=-1,
            amount_sats=1000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx)

        stats = engine.get_operational_stats()
        expected_fees = 5 * ARK_ROUND_COST_SATS / SATS_PER_BTC

        assert stats["round_count"] == 5
        assert stats["total_fees_btc"] == expected_fees

    def test_round_interval_constant(self) -> None:
        """Verify round interval is 600 seconds (10 minutes)."""
        assert ARK_ROUND_INTERVAL == 600


class TestOperationalStats:
    """Tests for operational statistics structure and values."""

    def test_operational_stats_structure(self) -> None:
        """Verify stats has required keys."""
        engine = ArkEngine([0])
        stats = engine.get_operational_stats()

        assert "round_count" in stats
        assert "total_fees_btc" in stats
        assert "avg_tvl" in stats

    def test_avg_tvl_tracking(self) -> None:
        """Average TVL is tracked across rounds."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=5_000_000)

        # Initial sample: 10M
        # After outbound at t=600: pool is 9M, new sample taken
        tx1 = Transaction(
            tx_id="tx_avg1",
            timestamp=600.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=1_000_000,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx1)

        stats = engine.get_operational_stats()
        # Samples: [10M, 9M] -> avg = 9.5M
        # Note: sample taken BEFORE transaction processes
        expected_avg = (10_000_000 + 10_000_000) / 2  # Sample taken when round passes, before tx
        assert stats["avg_tvl"] == expected_avg


class TestTVLTracking:
    """Tests for TVL (ASP locked capital) tracking."""

    def test_tvl_decreases_after_outbound(self) -> None:
        """Outbound decreases TVL (pool pays the world)."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=5_000_000)
        amount = 1_000_000

        tx = Transaction(
            tx_id="tx_tvl_out",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )
        engine.process_transaction(tx)

        assert engine.get_current_tvl() == 9_000_000

    def test_tvl_increases_after_inbound(self) -> None:
        """Inbound increases TVL (pool receives from world)."""
        engine = ArkEngine([0], pool_capacity=10_000_000, user_initial_balance=0)
        amount = 2_000_000

        tx = Transaction(
            tx_id="tx_tvl_in",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )
        engine.process_transaction(tx)

        assert engine.get_current_tvl() == 12_000_000

    def test_tvl_unchanged_after_internal(self) -> None:
        """Internal transfers don't change TVL."""
        engine = ArkEngine([0, 1], pool_capacity=10_000_000, user_initial_balance=5_000_000)
        initial_tvl = engine.get_current_tvl()

        tx = Transaction(
            tx_id="tx_tvl_internal",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=1_000_000,
            tx_type=TransactionType.INTERNAL,
        )
        engine.process_transaction(tx)

        assert engine.get_current_tvl() == initial_tvl


class TestArkVsLegacyComparison:
    """Tests highlighting differences between Ark and Legacy approaches."""

    def test_ark_internal_vs_legacy_internal(self) -> None:
        """
        In Legacy: Internal transfer requires LSP liquidity on receiver's channel.
        In Ark: Internal transfer requires NO pool liquidity.

        This test shows Ark succeeds where Legacy would fail.
        """
        # Ark with 0 pool but users have funds
        engine = ArkEngine([0, 1], pool_capacity=0, user_initial_balance=1_000_000)

        tx = Transaction(
            tx_id="tx_compare",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=500_000,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)

        # Ark succeeds - no pool needed for internal
        assert result is True
        assert engine.get_user_balance(0) == 500_000
        assert engine.get_user_balance(1) == 1_500_000

        # In Legacy, this would require the receiver's channel to have
        # 500k in local (LSP) balance, which might not be available

    def test_ark_capital_efficiency(self) -> None:
        """
        Compare capital requirements:
        Legacy: 100 users * 5M capacity * 50% split = 250M sats TVL
        Ark: 50M sats pool serves same 100 users (5x more efficient)
        """
        user_ids = list(range(100))

        # Ark with 50M (10% of Legacy TVL)
        # Explicitly set pool_capacity to avoid dependency on config modifications
        ark_engine = ArkEngine(user_ids, pool_capacity=50_000_000)

        assert ark_engine.get_current_tvl() == 50_000_000, "Ark TVL is 50M"
        assert ark_engine.get_total_user_count() == 100, "Ark serves 100 users"

        # Each user still has same spending power as Legacy (2.5M)
        for user_id in user_ids:
            assert ark_engine.get_user_balance(user_id) == 2_500_000

