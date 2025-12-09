from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class OrderRequest:
    symbol: str
    qty: int
    buy_price: float
    sell_price: float
    algo_id: str  # To track strategy specific orders

class GenericBroker(ABC):
    """
    Abstract Base Class ensuring any broker implementation 
    follows the same rules.
    """
    
    @abstractmethod
    def connect(self):
        """Connect to the brokerage API."""
        pass

    @abstractmethod
    def get_cash_balance(self) -> float:
        """Return available settled cash."""
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get snapshot price."""
        pass

    @abstractmethod
    def place_bracket_order(self, order: OrderRequest) -> int:
        """
        Place a Buy Limit order with an attached Sell Limit order (Profit Taker).
        Returns the Order ID.
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: str) -> List[dict]:
        """Return list of open orders."""
        pass
