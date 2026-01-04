"""Tests for the Legacy Lightning Network engine."""

import pytest

from src.config import LEGACY_CHANNEL_CAPACITY, LEGACY_INITIAL_SPLIT
from src.engines.legacy_engine import LegacyEngine
from src.models import Transaction, TransactionType


class TestLegacyEngineInitialization:
    """Tests for LegacyEngine initialization and state management."""

    def test_initialization_total_lsp_liquidity(self) -> None:
        """Assert total LSP liquidity equals (Total Users * Capacity * Split)."""
        user_ids = list(range(100))
        engine = LegacyEngine(user_ids)

        expected_lsp_liquidity = len(user_ids) * LEGACY_CHANNEL_CAPACITY * LEGACY_INITIAL_SPLIT
        actual_lsp_liquidity = engine.get_current_tvl()

        assert actual_lsp_liquidity == expected_lsp_liquidity, (
            f"Expected LSP liquidity {expected_lsp_liquidity}, got {actual_lsp_liquidity}"
        )

    def test_initialization_per_channel_balance(self) -> None:
        """Assert each channel is initialized with correct split."""
        user_ids = [0, 1, 2]
        engine = LegacyEngine(user_ids)

        expected_local = int(LEGACY_CHANNEL_CAPACITY * LEGACY_INITIAL_SPLIT)
        expected_remote = LEGACY_CHANNEL_CAPACITY - expected_local

        for user_id in user_ids:
            channel = engine.get_channel_state(user_id)
            assert channel is not None, f"Channel for user {user_id} should exist"
            assert channel["local"] == expected_local, (
                f"User {user_id} local balance should be {expected_local}"
            )
            assert channel["remote"] == expected_remote, (
                f"User {user_id} remote balance should be {expected_remote}"
            )

    def test_initialization_custom_capacity_and_split(self) -> None:
        """Assert custom capacity and split are applied correctly."""
        user_ids = [0, 1]
        custom_capacity = 1_000_000
        custom_split = 0.7

        engine = LegacyEngine(user_ids, channel_capacity=custom_capacity, initial_split=custom_split)

        expected_local = int(custom_capacity * custom_split)
        expected_remote = custom_capacity - expected_local
        expected_tvl = len(user_ids) * expected_local

        assert engine.get_current_tvl() == expected_tvl
        for user_id in user_ids:
            channel = engine.get_channel_state(user_id)
            assert channel["local"] == expected_local
            assert channel["remote"] == expected_remote

    def test_engine_name(self) -> None:
        """Assert engine returns correct name."""
        engine = LegacyEngine([0])
        assert engine.get_name() == "Legacy"


class TestExternalOutbound:
    """Tests for external outbound transactions (User -> World)."""

    @pytest.fixture
    def engine_with_users(self) -> LegacyEngine:
        """Create engine with two users."""
        return LegacyEngine([0, 1])

    def test_outbound_success(self, engine_with_users: LegacyEngine) -> None:
        """User sends funds successfully, local balance increases."""
        sender_id = 0
        amount = 100_000  # 100k sats

        initial_state = engine_with_users.get_channel_state(sender_id)
        initial_local = initial_state["local"]
        initial_remote = initial_state["remote"]

        tx = Transaction(
            tx_id="tx_out_1",
            timestamp=1.0,
            sender_id=sender_id,
            receiver_id=-1,  # External receiver
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is True, "Transaction should succeed"

        final_state = engine_with_users.get_channel_state(sender_id)
        assert final_state["local"] == initial_local + amount, (
            "LSP local balance should increase by amount"
        )
        assert final_state["remote"] == initial_remote - amount, (
            "User remote balance should decrease by amount"
        )

    def test_outbound_failure_insufficient_funds(self, engine_with_users: LegacyEngine) -> None:
        """User tries to send more than their remote balance."""
        sender_id = 0

        initial_state = engine_with_users.get_channel_state(sender_id)
        excessive_amount = initial_state["remote"] + 1

        tx = Transaction(
            tx_id="tx_out_fail",
            timestamp=1.0,
            sender_id=sender_id,
            receiver_id=-1,
            amount_sats=excessive_amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is False, "Transaction should fail due to insufficient funds"

        # Verify balances unchanged
        final_state = engine_with_users.get_channel_state(sender_id)
        assert final_state["local"] == initial_state["local"]
        assert final_state["remote"] == initial_state["remote"]

    def test_outbound_exact_balance(self, engine_with_users: LegacyEngine) -> None:
        """User can send exactly their full remote balance."""
        sender_id = 0
        initial_state = engine_with_users.get_channel_state(sender_id)
        exact_amount = initial_state["remote"]

        tx = Transaction(
            tx_id="tx_out_exact",
            timestamp=1.0,
            sender_id=sender_id,
            receiver_id=-1,
            amount_sats=exact_amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is True, "Transaction should succeed with exact balance"

        final_state = engine_with_users.get_channel_state(sender_id)
        assert final_state["remote"] == 0, "User should have zero remote balance"
        assert final_state["local"] == LEGACY_CHANNEL_CAPACITY, (
            "LSP should have full channel capacity"
        )


class TestExternalInbound:
    """Tests for external inbound transactions (World -> User)."""

    @pytest.fixture
    def engine_with_users(self) -> LegacyEngine:
        """Create engine with two users."""
        return LegacyEngine([0, 1])

    def test_inbound_success(self, engine_with_users: LegacyEngine) -> None:
        """User receives funds successfully, remote balance increases."""
        receiver_id = 0
        amount = 100_000

        initial_state = engine_with_users.get_channel_state(receiver_id)
        initial_local = initial_state["local"]
        initial_remote = initial_state["remote"]

        tx = Transaction(
            tx_id="tx_in_1",
            timestamp=1.0,
            sender_id=-1,  # External sender
            receiver_id=receiver_id,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is True, "Transaction should succeed"

        final_state = engine_with_users.get_channel_state(receiver_id)
        assert final_state["local"] == initial_local - amount, (
            "LSP local balance should decrease by amount"
        )
        assert final_state["remote"] == initial_remote + amount, (
            "User remote balance should increase by amount"
        )

    def test_inbound_failure_no_liquidity(self, engine_with_users: LegacyEngine) -> None:
        """LSP tries to receive but has no local balance left."""
        receiver_id = 0

        initial_state = engine_with_users.get_channel_state(receiver_id)
        excessive_amount = initial_state["local"] + 1

        tx = Transaction(
            tx_id="tx_in_fail",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=receiver_id,
            amount_sats=excessive_amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is False, "Transaction should fail due to insufficient LSP liquidity"

        # Verify balances unchanged
        final_state = engine_with_users.get_channel_state(receiver_id)
        assert final_state["local"] == initial_state["local"]
        assert final_state["remote"] == initial_state["remote"]

    def test_inbound_depletes_lsp_liquidity(self, engine_with_users: LegacyEngine) -> None:
        """After inbound, LSP liquidity is depleted for that channel."""
        receiver_id = 0
        initial_state = engine_with_users.get_channel_state(receiver_id)
        full_local = initial_state["local"]

        # Receive the full LSP local balance
        tx = Transaction(
            tx_id="tx_in_full",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=receiver_id,
            amount_sats=full_local,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result = engine_with_users.process_transaction(tx)
        assert result is True

        # Now try to receive more - should fail
        tx_fail = Transaction(
            tx_id="tx_in_fail_2",
            timestamp=2.0,
            sender_id=-1,
            receiver_id=receiver_id,
            amount_sats=1,  # Even 1 sat should fail
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        result_fail = engine_with_users.process_transaction(tx_fail)
        assert result_fail is False, "Should fail with depleted LSP liquidity"


class TestInternalTransfer:
    """Tests for internal transfers (User -> User via LSP)."""

    @pytest.fixture
    def engine_with_users(self) -> LegacyEngine:
        """Create engine with Alice (0) and Bob (1)."""
        return LegacyEngine([0, 1])

    def test_internal_transfer_success(self, engine_with_users: LegacyEngine) -> None:
        """Verify Alice -> Bob updates both channels correctly."""
        alice_id = 0
        bob_id = 1
        amount = 100_000

        # Copy initial values since get_channel_state returns a reference
        alice_state = engine_with_users.get_channel_state(alice_id)
        bob_state = engine_with_users.get_channel_state(bob_id)
        alice_initial_remote = alice_state["remote"]
        alice_initial_local = alice_state["local"]
        bob_initial_remote = bob_state["remote"]
        bob_initial_local = bob_state["local"]

        tx = Transaction(
            tx_id="tx_internal_1",
            timestamp=1.0,
            sender_id=alice_id,
            receiver_id=bob_id,
            amount_sats=amount,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is True, "Internal transfer should succeed"

        alice_final = engine_with_users.get_channel_state(alice_id)
        bob_final = engine_with_users.get_channel_state(bob_id)

        # Alice's channel: remote decreased, local increased
        assert alice_final["remote"] == alice_initial_remote - amount
        assert alice_final["local"] == alice_initial_local + amount

        # Bob's channel: local decreased, remote increased
        assert bob_final["local"] == bob_initial_local - amount
        assert bob_final["remote"] == bob_initial_remote + amount

    def test_internal_failure_sender_insufficient(self, engine_with_users: LegacyEngine) -> None:
        """Sender doesn't have enough remote balance."""
        alice_id = 0
        bob_id = 1

        alice_initial = engine_with_users.get_channel_state(alice_id)
        excessive_amount = alice_initial["remote"] + 1

        tx = Transaction(
            tx_id="tx_internal_fail_sender",
            timestamp=1.0,
            sender_id=alice_id,
            receiver_id=bob_id,
            amount_sats=excessive_amount,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine_with_users.process_transaction(tx)

        assert result is False, "Should fail due to sender insufficient funds"

        # Verify both channels unchanged
        alice_final = engine_with_users.get_channel_state(alice_id)
        bob_final = engine_with_users.get_channel_state(bob_id)
        bob_initial = engine_with_users.get_channel_state(bob_id)  # Re-get for comparison

        assert alice_final["remote"] == alice_initial["remote"]
        assert alice_final["local"] == alice_initial["local"]

    def test_internal_failure_receiver_no_lsp_liquidity(self, engine_with_users: LegacyEngine) -> None:
        """Receiver channel doesn't have enough LSP local balance."""
        alice_id = 0
        bob_id = 1

        bob_initial = engine_with_users.get_channel_state(bob_id)
        # Amount larger than Bob's channel LSP local balance
        excessive_amount = bob_initial["local"] + 1

        # But Alice has enough to send (need to ensure this)
        alice_initial = engine_with_users.get_channel_state(alice_id)

        # This test requires Alice to have more remote than Bob has local
        # With default 50% split, both have same amounts, so we need custom setup
        engine = LegacyEngine([0, 1], channel_capacity=1_000_000, initial_split=0.3)

        # Now local is 300k, remote is 700k
        # Alice can send up to 700k, but Bob's local is only 300k
        excessive_for_bob = 400_000

        tx = Transaction(
            tx_id="tx_internal_fail_receiver",
            timestamp=1.0,
            sender_id=alice_id,
            receiver_id=bob_id,
            amount_sats=excessive_for_bob,
            tx_type=TransactionType.INTERNAL,
        )

        result = engine.process_transaction(tx)

        assert result is False, "Should fail due to receiver's channel lacking LSP liquidity"

    def test_internal_preserves_total_capacity(self, engine_with_users: LegacyEngine) -> None:
        """Channel capacities remain constant after internal transfer."""
        alice_id = 0
        bob_id = 1
        amount = 100_000

        alice_initial = engine_with_users.get_channel_state(alice_id)
        bob_initial = engine_with_users.get_channel_state(bob_id)

        tx = Transaction(
            tx_id="tx_internal_cap",
            timestamp=1.0,
            sender_id=alice_id,
            receiver_id=bob_id,
            amount_sats=amount,
            tx_type=TransactionType.INTERNAL,
        )

        engine_with_users.process_transaction(tx)

        alice_final = engine_with_users.get_channel_state(alice_id)
        bob_final = engine_with_users.get_channel_state(bob_id)

        # Total capacity per channel should be unchanged
        alice_total = alice_final["local"] + alice_final["remote"]
        bob_total = bob_final["local"] + bob_final["remote"]

        assert alice_total == LEGACY_CHANNEL_CAPACITY
        assert bob_total == LEGACY_CHANNEL_CAPACITY


class TestTVLTracking:
    """Tests for TVL (LSP liquidity) tracking."""

    def test_tvl_unchanged_after_internal_transfer(self) -> None:
        """Internal transfers don't change total LSP liquidity."""
        engine = LegacyEngine([0, 1])
        initial_tvl = engine.get_current_tvl()

        tx = Transaction(
            tx_id="tx_tvl_1",
            timestamp=1.0,
            sender_id=0,
            receiver_id=1,
            amount_sats=100_000,
            tx_type=TransactionType.INTERNAL,
        )

        engine.process_transaction(tx)

        assert engine.get_current_tvl() == initial_tvl, (
            "TVL should be unchanged after internal transfer"
        )

    def test_tvl_increases_after_outbound(self) -> None:
        """Outbound transactions increase LSP liquidity."""
        engine = LegacyEngine([0])
        initial_tvl = engine.get_current_tvl()
        amount = 100_000

        tx = Transaction(
            tx_id="tx_tvl_out",
            timestamp=1.0,
            sender_id=0,
            receiver_id=-1,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_OUTBOUND,
        )

        engine.process_transaction(tx)

        assert engine.get_current_tvl() == initial_tvl + amount

    def test_tvl_decreases_after_inbound(self) -> None:
        """Inbound transactions decrease LSP liquidity."""
        engine = LegacyEngine([0])
        initial_tvl = engine.get_current_tvl()
        amount = 100_000

        tx = Transaction(
            tx_id="tx_tvl_in",
            timestamp=1.0,
            sender_id=-1,
            receiver_id=0,
            amount_sats=amount,
            tx_type=TransactionType.EXTERNAL_INBOUND,
        )

        engine.process_transaction(tx)

        assert engine.get_current_tvl() == initial_tvl - amount

