"""
Momentum trading strategy implementation.
"""
from typing import Optional, List
from strategies.base_strategy import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    """
    Momentum strategy that generates signals based on price momentum.

    Buys when momentum exceeds entry threshold, sells when it drops below exit threshold.
    """

    def __init__(self, lookback_period: int = 20, entry_threshold: float = 0.02,
                 exit_threshold: float = 0.01):
        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold

    def name(self) -> str:
        return "momentum"

    def calculate_momentum(self, prices: List[float]) -> float:
        """Calculate momentum as percentage change over lookback period."""
        if len(prices) < self.lookback_period + 1:
            return 0.0

        current_price = prices[-1]
        past_price = prices[-(self.lookback_period + 1)]

        if past_price == 0:
            return 0.0

        return (current_price - past_price) / past_price

    def generate_signal(self, symbol: str, market_data: dict) -> Optional[Signal]:
        """
        Generate a trading signal based on momentum.

        Args:
            symbol: The stock symbol to analyze
            market_data: Dictionary containing 'prices' list with historical prices

        Returns:
            Signal object or None if no signal
        """
        prices = market_data.get("prices", [])

        if len(prices) < self.lookback_period + 1:
            return None

        momentum = self.calculate_momentum(prices)

        # Check for buy signal
        if momentum > self.entry_threshold:
            strength = min(1.0, momentum / (self.entry_threshold * 2))
            return Signal(symbol, "BUY", strength)

        # Check for sell signal
        elif momentum < -self.exit_threshold:
            strength = min(1.0, abs(momentum) / (self.exit_threshold * 2))
            return Signal(symbol, "SELL", strength)

        return None
