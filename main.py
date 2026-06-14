"""
Main entry point for the trading bot.
"""
import argparse
from src.config_loader import Config
from src.trading_bot import TradingBot
from strategies.momentum import MomentumStrategy


def main():
    """Main function to run the trading bot."""
    parser = argparse.ArgumentParser(description="Trading Bot for Interactive Brokers")
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings.ini",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between trading iterations in seconds"
    )
    args = parser.parse_args()

    # Load configuration
    config = Config(args.config)

    # Initialize strategy based on config
    if config.strategy_name == "momentum":
        strategy = MomentumStrategy(
            lookback_period=config.lookback_period,
            entry_threshold=config.entry_threshold,
            exit_threshold=config.exit_threshold
        )
    else:
        raise ValueError(f"Unknown strategy: {config.strategy_name}")

    # Create and run trading bot
    bot = TradingBot(config, strategy)
    
    try:
        bot.connect()
        bot.run(interval=args.interval)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        bot.stop()
    except Exception as e:
        print(f"Error: {e}")
        bot.stop()
        raise


if __name__ == "__main__":
    main()
