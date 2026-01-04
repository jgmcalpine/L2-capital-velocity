"""Simulation runner that processes traffic through an LSP engine."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from src.engines.abstract_engine import AbstractLSPEngine
from src.models import Transaction, TransactionType


@dataclass
class SimulationResult:
    """Results from a simulation run."""

    engine_name: str
    total_volume_processed: int  # in sats
    total_volume_failed: int  # in sats
    tx_success_count: int
    tx_failure_count: int
    tvl_history: List[Tuple[float, float]] = field(default_factory=list)

    @property
    def total_transactions(self) -> int:
        """Total number of transactions processed."""
        return self.tx_success_count + self.tx_failure_count

    @property
    def success_rate(self) -> float:
        """Percentage of successful transactions (0.0 to 1.0)."""
        if self.total_transactions == 0:
            return 0.0
        return self.tx_success_count / self.total_transactions

    @property
    def failure_rate(self) -> float:
        """Percentage of failed transactions (0.0 to 1.0)."""
        return 1.0 - self.success_rate


class SimulationRunner:
    """
    Runs transaction traffic through an LSP engine and collects statistics.

    Loads transactions from a CSV file and processes each through the
    provided engine, tracking success/failure rates and TVL over time.
    """

    def __init__(self, traffic_file_path: str | Path, engine: AbstractLSPEngine) -> None:
        """
        Initialize the simulation runner.

        Args:
            traffic_file_path: Path to the traffic CSV file.
            engine: The LSP engine to process transactions through.
        """
        self.traffic_file_path = Path(traffic_file_path)
        self.engine = engine

    def run(self) -> SimulationResult:
        """
        Execute the simulation and return results.

        Loads the traffic CSV, processes each transaction through the engine,
        and collects statistics on success/failure rates and TVL history.

        Returns:
            SimulationResult containing all collected statistics.
        """
        df = pd.read_csv(self.traffic_file_path)

        total_volume_processed = 0
        total_volume_failed = 0
        tx_success_count = 0
        tx_failure_count = 0
        tvl_history: List[Tuple[float, float]] = []

        for _, row in df.iterrows():
            tx = self._row_to_transaction(row)
            success = self.engine.process_transaction(tx)

            if success:
                total_volume_processed += tx.amount_sats
                tx_success_count += 1
            else:
                total_volume_failed += tx.amount_sats
                tx_failure_count += 1

            # Record TVL at each timestamp
            current_tvl = self.engine.get_current_tvl()
            tvl_history.append((tx.timestamp, current_tvl))

        return SimulationResult(
            engine_name=self.engine.get_name(),
            total_volume_processed=total_volume_processed,
            total_volume_failed=total_volume_failed,
            tx_success_count=tx_success_count,
            tx_failure_count=tx_failure_count,
            tvl_history=tvl_history,
        )

    @staticmethod
    def _row_to_transaction(row: pd.Series) -> Transaction:
        """Convert a DataFrame row back to a Transaction object."""
        return Transaction(
            tx_id=row["tx_id"],
            timestamp=float(row["timestamp"]),
            sender_id=int(row["sender_id"]),
            receiver_id=int(row["receiver_id"]),
            amount_sats=int(row["amount_sats"]),
            tx_type=TransactionType(row["tx_type"]),
        )

