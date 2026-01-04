"""Passthrough engine implementation for testing."""

from src.engines.abstract_engine import AbstractLSPEngine
from src.models import Transaction


class PassthroughEngine(AbstractLSPEngine):
    """
    A dummy engine that passes all transactions through successfully.

    Useful for baseline testing and verifying the simulation harness
    works correctly before implementing real LSP logic.
    """

    def process_transaction(self, tx: Transaction) -> bool:
        """Always returns True - all transactions succeed."""
        return True

    def get_current_tvl(self) -> float:
        """Always returns 0.0 - no liquidity tracking."""
        return 0.0

    def get_name(self) -> str:
        """Returns the engine identifier."""
        return "Passthrough"

