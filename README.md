# Trading Bot v1

A momentum-based trading bot for Interactive Brokers.

## Features

- **Momentum Strategy**: Generates buy/sell signals based on price momentum
- **Interactive Brokers Integration**: Connects to TWS or IB Gateway for live trading
- **Configurable Parameters**: Customize trading parameters via configuration file
- **Logging**: Comprehensive logging to file and console
- **Risk Management**: Configurable position sizing, stop-loss, and take-profit levels

## Project Structure

```
trading-bot-v1/
├── main.py                 # Entry point
├── config/
│   └── settings.ini        # Configuration file
├── src/
│   ├── config_loader.py    # Configuration management
│   ├── logger.py           # Logging setup
│   ├── ib_client.py        # Interactive Brokers client
│   └── trading_bot.py      # Main trading bot logic
├── strategies/
│   ├── base_strategy.py    # Base strategy interface
│   └── momentum.py         # Momentum strategy implementation
├── tests/
│   └── test_momentum_strategy.py  # Unit tests
└── logs/                   # Log files directory
```

## Installation

1. Install required dependencies:
```bash
pip install ibapi
```

2. Configure the bot by editing `config/settings.ini`:
```ini
[DEFAULT]
ib_port = 7497
ib_host = 127.0.0.1
client_id = 1

[TRADING]
symbols = AAPL,MSFT,GOOGL
max_position_size = 100
stop_loss_pct = 0.02
take_profit_pct = 0.05

[STRATEGY]
name = momentum
lookback_period = 20
entry_threshold = 0.02
exit_threshold = 0.01
```

## Usage

### Run the Trading Bot

```bash
python main.py --config config/settings.ini --interval 60
```

Options:
- `--config`: Path to configuration file (default: config/settings.ini)
- `--interval`: Time between trading iterations in seconds (default: 60)

### Run Tests

```bash
python -m unittest discover -s tests -v
```

## How It Works

1. **Configuration**: The bot loads settings from `config/settings.ini`
2. **Connection**: Connects to Interactive Brokers TWS or Gateway
3. **Market Data**: Fetches real-time market data for configured symbols
4. **Signal Generation**: The momentum strategy analyzes price data and generates signals
5. **Order Execution**: Executes buy/sell orders based on signals
6. **Risk Management**: Applies position sizing and risk limits

## Momentum Strategy

The momentum strategy works as follows:

- **Buy Signal**: Generated when price momentum exceeds the entry threshold (default: 2%)
- **Sell Signal**: Generated when price momentum drops below the exit threshold (default: -1%)
- **Momentum Calculation**: Percentage change over the lookback period (default: 20 periods)

## Requirements

- Python 3.8+
- Interactive Brokers TWS or IB Gateway running
- ibapi library (comes with TWS/Gateway installation)

## Disclaimer

This trading bot is for educational purposes only. Trading involves substantial risk of loss. 
Always test thoroughly in a paper trading environment before using real money.
