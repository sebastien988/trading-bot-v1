"""
Unit tests for the momentum strategy.
"""
import unittest
from strategies.momentum import MomentumStrategy
from strategies.base_strategy import Signal


class TestMomentumStrategy(unittest.TestCase):

    def setUp(self):
        self.strategy = MomentumStrategy(
            lookback_period=5,
            entry_threshold=0.02,
            exit_threshold=0.01
        )

    def test_name(self):
        """Test strategy name."""
        self.assertEqual(self.strategy.name(), "momentum")

    def test_calculate_momentum_positive(self):
        """Test momentum calculation with positive momentum."""
        prices = [100, 102, 104, 106, 108, 110]  # 10% increase over 5 periods
        momentum = self.strategy.calculate_momentum(prices)
        self.assertAlmostEqual(momentum, 0.10, places=2)

    def test_calculate_momentum_negative(self):
        """Test momentum calculation with negative momentum."""
        prices = [100, 98, 96, 94, 92, 90]  # 10% decrease over 5 periods
        momentum = self.strategy.calculate_momentum(prices)
        self.assertAlmostEqual(momentum, -0.10, places=2)

    def test_calculate_momentum_insufficient_data(self):
        """Test momentum with insufficient data."""
        prices = [100, 102, 104]  # Less than lookback period
        momentum = self.strategy.calculate_momentum(prices)
        self.assertEqual(momentum, 0.0)

    def test_generate_signal_buy(self):
        """Test buy signal generation."""
        # Create prices with strong upward momentum (> 2%)
        prices = [100, 101, 102, 103, 104, 105]
        market_data = {"prices": prices}
        
        signal = self.strategy.generate_signal("AAPL", market_data)
        
        self.assertIsNotNone(signal)
        self.assertEqual(signal.symbol, "AAPL")
        self.assertEqual(signal.action, "BUY")
        self.assertGreater(signal.strength, 0)
        self.assertLessEqual(signal.strength, 1.0)

    def test_generate_signal_sell(self):
        """Test sell signal generation."""
        # Create prices with downward momentum (< -1%)
        prices = [100, 99, 98, 97, 96, 95]
        market_data = {"prices": prices}
        
        signal = self.strategy.generate_signal("MSFT", market_data)
        
        self.assertIsNotNone(signal)
        self.assertEqual(signal.symbol, "MSFT")
        self.assertEqual(signal.action, "SELL")
        self.assertGreater(signal.strength, 0)
        self.assertLessEqual(signal.strength, 1.0)

    def test_generate_signal_hold(self):
        """Test no signal when momentum is within thresholds."""
        # Create prices with minimal momentum (between -1% and 2%)
        prices = [100, 100.5, 100.3, 100.6, 100.4, 100.8]
        market_data = {"prices": prices}
        
        signal = self.strategy.generate_signal("GOOGL", market_data)
        
        self.assertIsNone(signal)

    def test_generate_signal_insufficient_data(self):
        """Test no signal with insufficient data."""
        market_data = {"prices": [100, 102]}  # Too few data points
        
        signal = self.strategy.generate_signal("AAPL", market_data)
        
        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
