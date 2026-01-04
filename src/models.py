from enum import Enum

from pydantic import BaseModel, ConfigDict


class UserType(str, Enum):
    """Classification of user behavior archetypes."""

    MERCHANT = "MERCHANT"
    CONSUMER = "CONSUMER"
    HODLER = "HODLER"


class User(BaseModel):
    """Represents a single actor in the simulation."""

    model_config = ConfigDict(frozen=True)

    user_id: int
    user_type: UserType

