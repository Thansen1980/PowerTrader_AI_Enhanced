"""
Configuration management for PowerTrader Enhanced.

Centralizes all configuration with environment variable support,
validation, and type safety.
"""
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings


class TradingMode(str, Enum):
    """Trading execution modes."""
    PAPER = "paper"  # Simulate trades, no real money
    LIVE = "live"    # Execute real trades
    BACKTEST = "backtest"  # Historical simulation


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ExchangeType(str, Enum):
    """Supported exchanges."""
    ROBINHOOD = "robinhood"
    KUCOIN = "kucoin"
    BINANCE = "binance"
    COINBASE = "coinbase"


class TimeFrame(str, Enum):
    """Trading timeframes."""
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    HOUR_1 = "1hour"
    HOUR_2 = "2hour"
    HOUR_4 = "4hour"
    HOUR_8 = "8hour"
    HOUR_12 = "12hour"
    DAY_1 = "1day"
    WEEK_1 = "1week"


class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_position_size_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    max_portfolio_heat: float = Field(default=20.0, ge=0.0, le=100.0)
    max_daily_loss_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    max_drawdown_pct: float = Field(default=15.0, ge=0.0, le=100.0)
    stop_loss_pct: float = Field(default=2.0, ge=0.0)
    take_profit_pct: float = Field(default=5.0, ge=0.0)
    trailing_stop_pct: float = Field(default=0.5, ge=0.0)
    use_kelly_criterion: bool = True
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)


class TradingConfig(BaseModel):
    """Trading strategy configuration."""
    coins: List[str] = Field(default=["BTC", "ETH", "XRP", "BNB", "DOGE"])
    timeframes: List[TimeFrame] = Field(default=[
        TimeFrame.HOUR_1,
        TimeFrame.HOUR_4,
        TimeFrame.DAY_1,
    ])
    trade_start_level: int = Field(default=3, ge=1, le=7)
    start_allocation_pct: float = Field(default=0.5, ge=0.0, le=100.0)
    dca_multiplier: float = Field(default=2.0, ge=0.0)
    dca_levels: List[float] = Field(default=[-2.5, -5.0, -10.0, -20.0, -30.0])
    max_dca_buys_per_24h: int = Field(default=2, ge=0)
    pm_start_pct_no_dca: float = Field(default=5.0, ge=0.0)
    pm_start_pct_with_dca: float = Field(default=2.5, ge=0.0)
    trailing_gap_pct: float = Field(default=0.5, ge=0.0)
    
    @validator('coins', pre=True)
    def uppercase_coins(cls, v: List[str]) -> List[str]:
        """Ensure coin symbols are uppercase."""
        return [coin.upper().strip() for coin in v if coin.strip()]


class ModelConfig(BaseModel):
    """Neural network model configuration."""
    lookback_candles: int = Field(default=100, ge=10)
    pattern_memory_size: int = Field(default=10000, ge=100)
    weight_decay: float = Field(default=0.9, ge=0.0, le=1.0)
    learning_rate: float = Field(default=0.25, ge=0.0, le=1.0)
    perfect_threshold: float = Field(default=0.25, ge=0.0)
    distance_tolerance_pct: float = Field(default=0.25, ge=0.0)
    training_stale_days: int = Field(default=14, ge=1)


class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(default="sqlite:///powertrader.db")
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    echo: bool = False


class RedisConfig(BaseModel):
    """Redis configuration for message queuing."""
    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    db: int = Field(default=0, ge=0)
    password: Optional[str] = None
    ssl: bool = False


class APIConfig(BaseModel):
    """REST API configuration."""
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1024, le=65535)
    reload: bool = False
    workers: int = Field(default=1, ge=1)


class Settings(BaseSettings):
    """Main application settings."""
    
    # Application
    app_name: str = "PowerTrader Enhanced"
    version: str = "2.0.0"
    trading_mode: TradingMode = TradingMode.PAPER
    exchange: ExchangeType = ExchangeType.ROBINHOOD
    log_level: LogLevel = LogLevel.INFO
    
    # Paths
    base_dir: Path = Field(default_factory=lambda: Path.cwd())
    data_dir: Path = Field(default_factory=lambda: Path.cwd() / "data")
    models_dir: Path = Field(default_factory=lambda: Path.cwd() / "models")
    logs_dir: Path = Field(default_factory=lambda: Path.cwd() / "logs")
    
    # Exchange credentials
    robinhood_api_key: Optional[str] = None
    robinhood_private_key: Optional[str] = None
    kucoin_api_key: Optional[str] = None
    kucoin_api_secret: Optional[str] = None
    kucoin_api_passphrase: Optional[str] = None
    
    # Component configs
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    
    # Intervals
    ui_refresh_seconds: float = Field(default=1.0, ge=0.1)
    chart_refresh_seconds: float = Field(default=2.0, ge=0.1)
    signal_check_seconds: float = Field(default=0.5, ge=0.1)
    health_check_seconds: float = Field(default=10.0, ge=1.0)
    
    class Config:
        """Pydantic config."""
        env_prefix = "PT_"
        env_nested_delimiter = "__"
        case_sensitive = False
    
    def __init__(self, **kwargs: Any):
        """Initialize and create directories."""
        super().__init__(**kwargs)
        self._create_directories()
    
    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for dir_path in [self.data_dir, self.models_dir, self.logs_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def get_coin_dir(self, coin: str) -> Path:
        """Get the data directory for a specific coin.
        
        Args:
            coin: Coin symbol (e.g., "BTC")
            
        Returns:
            Path to coin's data directory
        """
        coin = coin.upper().strip()
        if coin == "BTC":
            return self.data_dir
        return self.data_dir / coin
    
    def get_model_path(self, coin: str, timeframe: str) -> Path:
        """Get the model file path for a coin/timeframe.
        
        Args:
            coin: Coin symbol
            timeframe: Timeframe string
            
        Returns:
            Path to model file
        """
        coin_dir = self.get_coin_dir(coin)
        return coin_dir / f"model_{timeframe}.pkl"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance.
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment.
    
    Returns:
        New settings instance
    """
    global _settings
    _settings = Settings()
    return _settings
