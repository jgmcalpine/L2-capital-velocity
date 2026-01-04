from enum import Enum

from pydantic import BaseModel, ConfigDict


class UserType(str, Enum):
    """Classification of user behavior archetypes."""

    MERCHANT = "MERCHANT"
    CONSUMER = "CONSUMER"
    HODLER = "HODLER"


class TransactionType(str, Enum):
    """Classification of transaction flow direction."""

    INTERNAL = "INTERNAL"
    EXTERNAL_INBOUND = "EXTERNAL_INBOUND"
    EXTERNAL_OUTBOUND = "EXTERNAL_OUTBOUND"


class User(BaseModel):
    """Represents a single actor in the simulation."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    user_type: UserType


class Transaction(BaseModel):
    """Represents a single transaction in the simulation."""

    model_config = ConfigDict(frozen=True)

    tx_id: str
    timestamp: float
    sender_id: int
    receiver_id: int
    amount_sats: int
    tx_type: TransactionType
