import pytest

from src.config import SimulationConfig
from src.models import UserType
from src.traffic.user_generator import generate_users


@pytest.fixture
def config() -> SimulationConfig:
    """Provide default simulation config for tests."""
    return SimulationConfig()


class TestUserGeneration:
    """Test suite for user generation functionality."""

    def test_user_count(self, config: SimulationConfig) -> None:
        """Assert that generated user count matches config.TOTAL_USERS."""
        users = generate_users(config)
        assert len(users) == config.TOTAL_USERS

    def test_determinism(self, config: SimulationConfig) -> None:
        """Assert that generator produces identical results across runs."""
        users_run_1 = generate_users(config)
        users_run_2 = generate_users(config)

        assert len(users_run_1) == len(users_run_2)

        for u1, u2 in zip(users_run_1, users_run_2):
            assert u1.user_id == u2.user_id
            assert u1.user_type == u2.user_type

    def test_distribution_sanity(self, config: SimulationConfig) -> None:
        """Assert basic sanity: at least 1 MERCHANT and 1 CONSUMER exist."""
        users = generate_users(config)

        user_types = {user.user_type for user in users}

        assert UserType.MERCHANT in user_types, "Expected at least 1 MERCHANT"
        assert UserType.CONSUMER in user_types, "Expected at least 1 CONSUMER"

    def test_user_ids_sequential(self, config: SimulationConfig) -> None:
        """Assert user IDs are sequential starting from 0."""
        users = generate_users(config)

        for i, user in enumerate(users):
            assert user.user_id == i

    def test_all_user_types_valid(self, config: SimulationConfig) -> None:
        """Assert all generated users have valid UserType values."""
        users = generate_users(config)

        for user in users:
            assert isinstance(user.user_type, UserType)

