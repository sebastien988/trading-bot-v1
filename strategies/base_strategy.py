"""
Base strategy interface for trading strategies.
"""
from abc import ABC, abstractmethod
from typing import Optional


class Signal:
    """Represents a trading signal."""

    def __init__(self, symbol: str, action: str, strength: float = 1.0):
        self.symbol = symbol
        self.action = action  # 'BUY', 'SELL', 'HOLD'
        self.strength = strength  # 0.0 to 1.0

    def __repr__(self):
        return f"Signal({self.symbol}, {self.action}, strength={self.strength})"


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def generate_signal(self, symbol: str, market_data: dict) -> Optional[Signal]:
        """
        Generate a trading signal based on market data.

        Args:
            symbol: The stock symbol to analyze
            market_data: Dictionary containing price data and indicators

        Returns:
            Signal object or None if no signal
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Return the name of the strategy."""
        pass
