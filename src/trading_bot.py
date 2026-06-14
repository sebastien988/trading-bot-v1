"""
Main trading bot that orchestrates strategy, market data, and order execution.
"""
import time
from typing import Dict, Optional
from src.config_loader import Config
from src.logger import setup_logger
from src.ib_client import IBClient
from strategies.base_strategy import BaseStrategy, Signal


class TradingBot:
    """
    Main trading bot class that coordinates all components.
    """

    def __init__(self, config: Config, strategy: BaseStrategy):
        self.config = config
        self.strategy = strategy
        self.logger = setup_logger(config.log_file, config.log_level)
        self.ib_client = IBClient()
        self.positions: Dict[str, int] = {}
        self.running = False

    def connect(self):
        """Connect to Interactive Brokers."""
        self.logger.info("Connecting to Interactive Brokers...")
        self.ib_client.connect_ib(
            self.config.ib_host,
            self.config.ib_port,
            self.config.client_id
        )
        self.logger.info("Connected successfully")

    def disconnect(self):
        """Disconnect from Interactive Brokers."""
        self.logger.info("Disconnecting from Interactive Brokers...")
        self.ib_client.disconnect()
        self.logger.info("Disconnected")

    def get_market_data(self, symbol: str) -> dict:
        """
        Get market data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with market data
        """
        price = self.ib_client.get_market_data(symbol)
        return {"price": price, "prices": self._get_historical_prices(symbol)}

    def _get_historical_prices(self, symbol: str) -> list:
        """
        Get historical prices for a symbol.

        In production, this would fetch from IB or a data provider.
        For now, returns simulated data.
        """
        # Placeholder - in production would fetch real historical data
        return []

    def execute_signal(self, signal: Signal):
        """
        Execute a trading signal.

        Args:
            signal: Signal object with action and quantity
        """
        if signal.action == "BUY":
            quantity = self.config.max_position_size
            self.logger.info(f"Executing BUY order for {signal.symbol}: {quantity} shares")
            self.ib_client.place_order(signal.symbol, "BUY", quantity)
            self.positions[signal.symbol] = self.positions.get(signal.symbol, 0) + quantity

        elif signal.action == "SELL":
            quantity = self.positions.get(signal.symbol, 0)
            if quantity > 0:
                self.logger.info(f"Executing SELL order for {signal.symbol}: {quantity} shares")
                self.ib_client.place_order(signal.symbol, "SELL", quantity)
                self.positions[signal.symbol] = 0

    def run(self, interval: int = 60):
        """
        Run the trading bot loop.

        Args:
            interval: Time between iterations in seconds
        """
        self.running = True
        self.logger.info(f"Starting trading bot with {self.strategy.name()} strategy")
        self.logger.info(f"Monitoring symbols: {', '.join(self.config.symbols)}")

        try:
            while self.running:
                for symbol in self.config.symbols:
                    try:
                        market_data = self.get_market_data(symbol)
                        signal = self.strategy.generate_signal(symbol, market_data)

                        if signal:
                            self.logger.info(f"Signal generated: {signal}")
                            self.execute_signal(signal)

                    except Exception as e:
                        self.logger.error(f"Error processing {symbol}: {str(e)}")

                time.sleep(interval)

        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, stopping...")
        finally:
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        self.running = False
        self.disconnect()
        self.logger.info("Trading bot stopped")
