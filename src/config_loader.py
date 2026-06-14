"""
Configuration loader for the trading bot.
"""
import configparser
from pathlib import Path


class Config:
    """Load and manage trading bot configuration."""

    def __init__(self, config_path: str = "config/settings.ini"):
        self.config = configparser.ConfigParser()
        self.config_path = Path(config_path)
        self.load()

    def load(self):
        """Load configuration from file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        self.config.read(self.config_path)

    @property
    def ib_host(self) -> str:
        return self.config.get("DEFAULT", "ib_host")

    @property
    def ib_port(self) -> int:
        return self.config.getint("DEFAULT", "ib_port")

    @property
    def client_id(self) -> int:
        return self.config.getint("DEFAULT", "client_id")

    @property
    def symbols(self) -> list:
        symbols_str = self.config.get("TRADING", "symbols")
        return [s.strip() for s in symbols_str.split(",")]

    @property
    def max_position_size(self) -> int:
        return self.config.getint("TRADING", "max_position_size")

    @property
    def stop_loss_pct(self) -> float:
        return self.config.getfloat("TRADING", "stop_loss_pct")

    @property
    def take_profit_pct(self) -> float:
        return self.config.getfloat("TRADING", "take_profit_pct")

    @property
    def strategy_name(self) -> str:
        return self.config.get("STRATEGY", "name")

    @property
    def lookback_period(self) -> int:
        return self.config.getint("STRATEGY", "lookback_period")

    @property
    def entry_threshold(self) -> float:
        return self.config.getfloat("STRATEGY", "entry_threshold")

    @property
    def exit_threshold(self) -> float:
        return self.config.getfloat("STRATEGY", "exit_threshold")

    @property
    def log_level(self) -> str:
        return self.config.get("LOGGING", "level")

    @property
    def log_file(self) -> str:
        return self.config.get("LOGGING", "file")
