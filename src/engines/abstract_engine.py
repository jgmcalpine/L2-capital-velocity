"""Abstract base class for LSP (Lightning Service Provider) engines."""

from abc import ABC, abstractmethod

from src.models import Transaction


class AbstractLSPEngine(ABC):
    """
    Abstract base class defining the interface for LSP engines.

    All engine implementations must provide transaction processing,
    TVL (Total Value Locked) tracking, and identification.
    """

    @abstractmethod
    def process_transaction(self, tx: Transaction) -> bool:
        """
        Process a single transaction through the engine.

        Args:
            tx: The Transaction to process.

        Returns:
            True if the transaction was processed successfully, False otherwise.
        """

    @abstractmethod
    def get_current_tvl(self) -> float:
        """
        Get the current Total Value Locked in the LSP.

        Returns:
            The total BTC currently locked in the LSP.
        """

    @abstractmethod
    def get_name(self) -> str:
        """
        Get the engine's identifying name.

        Returns:
            A string identifier for the engine (e.g. "Legacy", "Ark").
        """

