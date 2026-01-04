from collections import Counter

from src.config import SimulationConfig
from src.models import UserType
from src.traffic.user_generator import generate_users


def print_user_summary(users: list) -> None:
    """Print a formatted summary table of user type distribution."""
    counts = Counter(user.user_type for user in users)

    print("\n" + "=" * 40)
    print("L2 Capital Velocity - User Population")
    print("=" * 40)
    print(f"{'User Type':<15} {'Count':>10} {'Percentage':>12}")
    print("-" * 40)

    total = len(users)
    for user_type in UserType:
        count = counts.get(user_type, 0)
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"{user_type.value:<15} {count:>10} {percentage:>11.1f}%")

    print("-" * 40)
    print(f"{'TOTAL':<15} {total:>10}")
    print("=" * 40 + "\n")


def main() -> None:
    """Initialize simulation and display user population summary."""
    config = SimulationConfig()
    users = generate_users(config)
    print_user_summary(users)


if __name__ == "__main__":
    main()

