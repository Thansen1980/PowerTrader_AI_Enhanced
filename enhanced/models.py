"""
Data models for PowerTrader Enhanced.

All data structures with validation, serialization, and type safety.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TradeTag(str, Enum):
    """Trade classification tags."""
    ENTRY = "ENTRY"
    DCA = "DCA"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    REBALANCE = "REBALANCE"


class SignalType(str, Enum):
    """Neural network signal type."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


# ===== Market Data Models =====

class Candle(BaseModel):
    """OHLCV candle data."""
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    
    @validator('high')
    def high_is_highest(cls, v: float, values: Dict) -> float:
        """Validate high is the highest price."""
        if 'low' in values and v < values['low']:
            raise ValueError("High must be >= low")
        if 'open' in values and v < values['open']:
            raise ValueError("High must be >= open")
        if 'close' in values and v < values['close']:
            raise ValueError("High must be >= close")
        return v
    
    @validator('low')
    def low_is_lowest(cls, v: float, values: Dict) -> float:
        """Validate low is the lowest price."""
        if 'high' in values and v > values['high']:
            raise ValueError("Low must be <= high")
        if 'open' in values and v > values['open']:
            raise ValueError("Low must be <= open")
        if 'close' in values and v > values['close']:
            raise ValueError("Low must be <= close")
        return v


class Quote(BaseModel):
    """Current bid/ask quote."""
    symbol: str
    timestamp: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    bid_size: float = Field(ge=0)
    ask_size: float = Field(ge=0)
    
    @validator('ask')
    def ask_gte_bid(cls, v: float, values: Dict) -> float:
        """Validate ask >= bid."""
        if 'bid' in values and v < values['bid']:
            raise ValueError("Ask must be >= bid")
        return v


# ===== Trading Models =====

class Order(BaseModel):
    """Trading order."""
    order_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Optional[float] = Field(None, gt=0)
    notional: Optional[float] = Field(None, gt=0)  # Dollar amount
    price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0)
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = Field(default=0.0, ge=0)
    average_fill_price: Optional[float] = Field(None, ge=0)
    created_at: datetime
    updated_at: datetime
    tag: Optional[TradeTag] = None
    metadata: Dict = Field(default_factory=dict)


class Position(BaseModel):
    """Current position in a symbol."""
    symbol: str
    quantity: float
    avg_cost_basis: float = Field(gt=0)
    current_price: float = Field(gt=0)
    market_value: float = Field(gt=0)
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float = 0.0
    dca_count: int = Field(default=0, ge=0)
    entry_time: datetime
    last_update: datetime
    
    @property
    def total_pnl(self) -> float:
        """Total profit/loss."""
        return self.realized_pnl + self.unrealized_pnl
    
    @property
    def total_pnl_pct(self) -> float:
        """Total profit/loss percentage."""
        cost = self.avg_cost_basis * self.quantity
        return (self.total_pnl / cost * 100) if cost > 0 else 0.0


class Trade(BaseModel):
    """Completed trade (filled order)."""
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    notional: float = Field(gt=0)
    fee: float = Field(default=0.0, ge=0)
    timestamp: datetime
    tag: Optional[TradeTag] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None


# ===== Neural Network Models =====

class Pattern(BaseModel):
    """Price pattern for neural network."""
    timeframe: str
    pattern_hash: str
    close_changes: List[float]
    high_changes: List[float]
    low_changes: List[float]
    weight: float = 1.0
    high_weight: float = 1.0
    low_weight: float = 1.0
    created_at: datetime
    last_seen: datetime
    hit_count: int = 0
    success_count: int = 0


class Prediction(BaseModel):
    """Neural network prediction."""
    symbol: str
    timeframe: str
    timestamp: datetime
    predicted_close: float
    predicted_high: float
    predicted_low: float
    confidence: float = Field(ge=0.0, le=1.0)
    matched_patterns: int
    signal_strength: int = Field(ge=0, le=7)


class NeuralSignal(BaseModel):
    """Trading signal from neural network."""
    symbol: str
    timestamp: datetime
    long_strength: int = Field(ge=0, le=7)
    short_strength: int = Field(ge=0, le=7)
    predictions: Dict[str, Prediction] = Field(default_factory=dict)
    signal_type: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Dict = Field(default_factory=dict)
    
    @validator('signal_type', always=True)
    def determine_signal_type(cls, v: Optional[SignalType], values: Dict) -> SignalType:
        """Determine signal type from strengths."""
        if v is not None:
            return v
        
        long = values.get('long_strength', 0)
        short = values.get('short_strength', 0)
        
        if long > short and long >= 3:
            return SignalType.LONG
        elif short > long and short >= 3:
            return SignalType.SHORT
        else:
            return SignalType.NEUTRAL


# ===== Risk Management Models =====

class RiskMetrics(BaseModel):
    """Risk metrics for portfolio."""
    total_value: float = Field(gt=0)
    buying_power: float = Field(ge=0)
    positions_value: float = Field(ge=0)
    positions_pct: float = Field(ge=0.0, le=100.0)
    unrealized_pnl: float
    realized_pnl: float
    daily_pnl: float
    daily_pnl_pct: float
    max_drawdown_pct: float = Field(ge=0.0)
    sharpe_ratio: Optional[float] = None
    win_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    profit_factor: Optional[float] = Field(None, ge=0.0)


class DCALevel(BaseModel):
    """Dollar-cost averaging level."""
    level: int = Field(ge=0)
    trigger_pct: float  # Negative for losses
    triggered: bool = False
    trigger_price: Optional[float] = Field(None, gt=0)
    trigger_time: Optional[datetime] = None
    position_size_multiplier: float = Field(gt=0)


# ===== System Status Models =====

class ComponentStatus(str, Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthCheck(BaseModel):
    """Health check result."""
    component: str
    status: ComponentStatus
    timestamp: datetime
    latency_ms: Optional[float] = Field(None, ge=0)
    message: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)


class SystemStatus(BaseModel):
    """Overall system status."""
    timestamp: datetime
    trading_mode: str
    is_trading: bool
    components: Dict[str, HealthCheck]
    uptime_seconds: float = Field(ge=0)
    
    @property
    def overall_status(self) -> ComponentStatus:
        """Determine overall system status."""
        statuses = [c.status for c in self.components.values()]
        if not statuses:
            return ComponentStatus.UNKNOWN
        if any(s == ComponentStatus.UNHEALTHY for s in statuses):
            return ComponentStatus.UNHEALTHY
        if any(s == ComponentStatus.DEGRADED for s in statuses):
            return ComponentStatus.DEGRADED
        return ComponentStatus.HEALTHY


# ===== Event Models =====

class EventType(str, Enum):
    """System event types."""
    TRADE_EXECUTED = "trade_executed"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    SIGNAL_GENERATED = "signal_generated"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    DCA_TRIGGERED = "dca_triggered"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    TRAINING_STARTED = "training_started"
    TRAINING_COMPLETED = "training_completed"
    ERROR_OCCURRED = "error_occurred"


class Event(BaseModel):
    """System event."""
    event_id: str
    event_type: EventType
    timestamp: datetime
    component: str
    data: Dict
    severity: str = "info"  # info, warning, error, critical
