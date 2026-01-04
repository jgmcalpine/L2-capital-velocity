"""Tests for traffic generation functionality."""

from collections import Counter

import pytest

from src.config import SimulationConfig
from src.models import TransactionType, UserType
from src.traffic.traffic_generator import TrafficGenerator
from src.traffic.user_generator import generate_users


@pytest.fixture
def config() -> SimulationConfig:
    """Provide default simulation config for tests."""
    return SimulationConfig()


@pytest.fixture
def users(config: SimulationConfig):
    """Generate user population for tests."""
    return generate_users(config)


@pytest.fixture
def transactions(config: SimulationConfig, users):
    """Generate transactions for tests."""
    generator = TrafficGenerator(config)
    return generator.generate_month_of_traffic(users)


class TestTrafficVolume:
    """Tests for traffic volume and count."""

    def test_traffic_volume_within_tolerance(
        self, config: SimulationConfig, transactions
    ) -> None:
        """Assert we generated roughly 10k events (+/- 10%)."""
        expected = config.TARGET_TRANSACTIONS
        tolerance = 0.10

        lower_bound = expected * (1 - tolerance)
        upper_bound = expected * (1 + tolerance)

        assert lower_bound <= len(transactions) <= upper_bound, (
            f"Expected {expected} transactions (+/- {tolerance*100}%), "
            f"got {len(transactions)}"
        )

    def test_transactions_sorted_by_timestamp(self, transactions) -> None:
        """Assert transactions are in chronological order."""
        timestamps = [tx.timestamp for tx in transactions]
        assert timestamps == sorted(timestamps), "Transactions not sorted by timestamp"

    def test_all_timestamps_within_simulation_period(
        self, config: SimulationConfig, transactions
    ) -> None:
        """Assert all timestamps fall within the simulation duration."""
        max_time = config.SIMULATION_DAYS * 86400  # seconds

        for tx in transactions:
            assert 0 <= tx.timestamp <= max_time, (
                f"Transaction timestamp {tx.timestamp} outside simulation period"
            )


class TestTransactionIntegrity:
    """Tests for transaction data integrity."""

    def test_no_self_payments(self, transactions) -> None:
        """Assert sender_id != receiver_id for all transactions."""
        for tx in transactions:
            assert tx.sender_id != tx.receiver_id, (
                f"Self-payment detected: tx_id={tx.tx_id}, "
                f"sender_id={tx.sender_id}, receiver_id={tx.receiver_id}"
            )

    def test_unique_transaction_ids(self, transactions) -> None:
        """Assert all transaction IDs are unique."""
        tx_ids = [tx.tx_id for tx in transactions]
        assert len(tx_ids) == len(set(tx_ids)), "Duplicate transaction IDs found"

    def test_positive_amounts(self, transactions) -> None:
        """Assert all transaction amounts are positive."""
        for tx in transactions:
            assert tx.amount_sats > 0, f"Non-positive amount: {tx.amount_sats}"

    def test_external_entity_id_correct(self, transactions) -> None:
        """Assert external transactions use -1 for external entity."""
        for tx in transactions:
            if tx.tx_type == TransactionType.EXTERNAL_INBOUND:
                assert tx.sender_id == -1, (
                    f"EXTERNAL_INBOUND should have sender_id=-1, got {tx.sender_id}"
                )
            elif tx.tx_type == TransactionType.EXTERNAL_OUTBOUND:
                assert tx.receiver_id == -1, (
                    f"EXTERNAL_OUTBOUND should have receiver_id=-1, got {tx.receiver_id}"
                )
            else:  # INTERNAL
                assert tx.sender_id != -1 and tx.receiver_id != -1, (
                    "INTERNAL transactions should not involve external entity"
                )


class TestUserTypeDistribution:
    """Tests for user type behavior in transactions."""

    def test_merchant_inflow(self, config: SimulationConfig, users, transactions) -> None:
        """Verify that Merchants appear as receivers more often than Consumers in internal txs."""
        # Build user_id -> user_type mapping
        user_type_map = {user.user_id: user.user_type for user in users}

        # Count receiver occurrences by type for internal transactions
        receiver_counts: Counter = Counter()
        internal_txs = [
            tx for tx in transactions if tx.tx_type == TransactionType.INTERNAL
        ]

        for tx in internal_txs:
            receiver_type = user_type_map.get(tx.receiver_id)
            if receiver_type:
                receiver_counts[receiver_type] += 1

        # Get counts for merchants and consumers
        user_counts = Counter(user.user_type for user in users)
        merchant_count = user_counts[UserType.MERCHANT]
        consumer_count = user_counts[UserType.CONSUMER]

        merchant_receives = receiver_counts.get(UserType.MERCHANT, 0)
        consumer_receives = receiver_counts.get(UserType.CONSUMER, 0)

        # Calculate per-capita receive rate
        merchant_rate = merchant_receives / merchant_count if merchant_count > 0 else 0
        consumer_rate = consumer_receives / consumer_count if consumer_count > 0 else 0

        assert merchant_rate > consumer_rate, (
            f"Merchants should receive more per-capita than Consumers. "
            f"Merchant rate: {merchant_rate:.2f}, Consumer rate: {consumer_rate:.2f}"
        )

    def test_consumer_outflow(self, config: SimulationConfig, users, transactions) -> None:
        """Verify that Consumers appear as senders more often than Merchants in internal txs."""
        user_type_map = {user.user_id: user.user_type for user in users}

        sender_counts: Counter = Counter()
        internal_txs = [
            tx for tx in transactions if tx.tx_type == TransactionType.INTERNAL
        ]

        for tx in internal_txs:
            sender_type = user_type_map.get(tx.sender_id)
            if sender_type:
                sender_counts[sender_type] += 1

        user_counts = Counter(user.user_type for user in users)
        merchant_count = user_counts[UserType.MERCHANT]
        consumer_count = user_counts[UserType.CONSUMER]

        merchant_sends = sender_counts.get(UserType.MERCHANT, 0)
        consumer_sends = sender_counts.get(UserType.CONSUMER, 0)

        # Calculate per-capita send rate
        merchant_rate = merchant_sends / merchant_count if merchant_count > 0 else 0
        consumer_rate = consumer_sends / consumer_count if consumer_count > 0 else 0

        assert consumer_rate > merchant_rate, (
            f"Consumers should send more per-capita than Merchants. "
            f"Consumer rate: {consumer_rate:.2f}, Merchant rate: {merchant_rate:.2f}"
        )


class TestTransactionTypeDistribution:
    """Tests for transaction type ratios."""

    def test_internal_external_ratio(
        self, config: SimulationConfig, transactions
    ) -> None:
        """Assert internal/external split is approximately as configured."""
        type_counts = Counter(tx.tx_type for tx in transactions)

        internal_count = type_counts[TransactionType.INTERNAL]
        total_count = len(transactions)

        actual_ratio = internal_count / total_count
        expected_ratio = config.INTERNAL_TX_RATIO
        tolerance = 0.05  # Allow 5% deviation

        assert abs(actual_ratio - expected_ratio) < tolerance, (
            f"Internal ratio {actual_ratio:.2%} differs from expected "
            f"{expected_ratio:.2%} by more than {tolerance:.2%}"
        )


class TestDeterminism:
    """Tests for reproducibility."""

    def test_deterministic_generation(self, config: SimulationConfig, users) -> None:
        """Assert that generator produces identical results across runs."""
        generator1 = TrafficGenerator(config)
        generator2 = TrafficGenerator(config)

        txs1 = generator1.generate_month_of_traffic(users)
        txs2 = generator2.generate_month_of_traffic(users)

        assert len(txs1) == len(txs2), "Transaction counts differ between runs"

        for t1, t2 in zip(txs1, txs2):
            assert t1.timestamp == t2.timestamp, "Timestamps differ"
            assert t1.sender_id == t2.sender_id, "Sender IDs differ"
            assert t1.receiver_id == t2.receiver_id, "Receiver IDs differ"
            assert t1.amount_sats == t2.amount_sats, "Amounts differ"
            assert t1.tx_type == t2.tx_type, "Transaction types differ"

