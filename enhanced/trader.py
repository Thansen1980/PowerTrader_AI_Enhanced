"""
Enhanced Trader - Order Execution and Position Management.

Improvements over original:
- Type-safe order handling
- Risk management integration
- DCA strategy with limits
- Trailing stop-loss
- Comprehensive logging
- State persistence in database
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import Settings, get_settings
from models import (
    DCALevel, Order, OrderSide, OrderStatus, OrderType,
    Position, Trade, TradeTag
)

logger = logging.getLogger(__name__)


class TradingEngine:
    """Core trading engine for order execution."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize trading engine.
        
        Args:
            settings: Configuration settings
        """
        self.settings = settings or get_settings()
        
        # State tracking
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.dca_history: Dict[str, List[datetime]] = {}
        self.trailing_peaks: Dict[str, float] = {}
        
        # Initialize based on trading mode
        if self.settings.trading_mode.value == "paper":
            logger.info("Running in PAPER TRADING mode (simulated)")
            from exchange.paper import PaperExchange
            self.exchange = PaperExchange(settings)
        elif self.settings.exchange.value == "robinhood":
            logger.info("Running in LIVE mode with Robinhood")
            from exchange.robinhood import RobinhoodExchange
            self.exchange = RobinhoodExchange(settings)
        else:
            raise ValueError(f"Unsupported exchange: {self.settings.exchange}")
    
    async def get_account_balance(self) -> Dict:
        """Get current account balance and buying power."""
        return await self.exchange.get_account()
    
    async def get_current_positions(self) -> Dict[str, Position]:
        """Get all current positions."""
        return await self.exchange.get_positions()
    
    async def get_quote(self, symbol: str) -> Dict:
        """Get current bid/ask for a symbol."""
        return await self.exchange.get_quote(symbol)
    
    def _should_start_trade(self, coin: str, signals: Dict) -> bool:
        """Determine if we should start a new trade.
        
        Args:
            coin: Coin symbol
            signals: Neural network signals
            
        Returns:
            True if should start trade
        """
        signal = signals.get(coin)
        if not signal:
            return False
        
        # Check signal strength meets threshold
        start_level = self.settings.trading.trade_start_level
        
        if signal.long_strength >= start_level and signal.short_strength == 0:
            logger.info(
                f"{coin}: Start signal detected "
                f"(long={signal.long_strength}, short={signal.short_strength})"
            )
            return True
        
        return False
    
    def _calculate_position_size(
        self,
        account_value: float,
        symbol: str,
        is_dca: bool = False,
        dca_multiplier: float = 1.0
    ) -> float:
        """Calculate position size based on risk management.
        
        Args:
            account_value: Total account value
            symbol: Trading symbol
            is_dca: Whether this is a DCA buy
            dca_multiplier: DCA size multiplier
            
        Returns:
            Dollar amount to invest
        """
        # Base allocation percentage
        base_pct = self.settings.trading.start_allocation_pct / 100.0
        
        # Apply Kelly Criterion if enabled
        if self.settings.risk.use_kelly_criterion:
            # Simplified Kelly: f = (bp - q) / b
            # For now, use conservative fixed fraction
            kelly_fraction = self.settings.risk.kelly_fraction
            base_pct *= kelly_fraction
        
        # Calculate base size
        position_size = account_value * base_pct
        
        # Apply DCA multiplier
        if is_dca:
            position_size *= dca_multiplier
        
        # Apply risk limits
        max_position = account_value * (self.settings.risk.max_position_size_pct / 100.0)
        position_size = min(position_size, max_position)
        
        # Minimum position size
        position_size = max(position_size, 1.0)
        
        return position_size
    
    def _get_dca_levels(self, position: Position) -> List[DCALevel]:
        """Get DCA levels for a position.
        
        Args:
            position: Current position
            
        Returns:
            List of DCA levels with prices
        """
        levels = []
        
        for i, level_pct in enumerate(self.settings.trading.dca_levels):
            trigger_price = position.avg_cost_basis * (1 + level_pct / 100.0)
            
            levels.append(DCALevel(
                level=i,
                trigger_pct=level_pct,
                triggered=False,
                trigger_price=trigger_price,
                position_size_multiplier=self.settings.trading.dca_multiplier ** i
            ))
        
        return levels
    
    def _should_dca(
        self,
        position: Position,
        current_price: float,
        signals: Dict
    ) -> Optional[DCALevel]:
        """Check if DCA should trigger.
        
        Args:
            position: Current position
            current_price: Current market price
            signals: Neural network signals
            
        Returns:
            DCA level to execute, or None
        """
        # Check 24h DCA limit
        symbol = position.symbol
        recent_dcas = self.dca_history.get(symbol, [])
        cutoff = datetime.now() - timedelta(hours=24)
        recent_dcas = [t for t in recent_dcas if t > cutoff]
        
        if len(recent_dcas) >= self.settings.trading.max_dca_buys_per_24h:
            logger.debug(f"{symbol}: DCA limit reached ({len(recent_dcas)} in 24h)")
            return None
        
        # Get DCA levels
        dca_levels = self._get_dca_levels(position)
        
        # Find next untriggered level
        for level in dca_levels:
            if level.triggered:
                continue
            
            # Check if price hit trigger
            if current_price <= level.trigger_price:
                logger.info(
                    f"{symbol}: DCA level {level.level} triggered "
                    f"(price ${current_price:.2f} <= ${level.trigger_price:.2f})"
                )
                return level
        
        return None
    
    def _should_take_profit(
        self,
        position: Position,
        current_price: float
    ) -> bool:
        """Check if should take profit (trailing stop).
        
        Args:
            position: Current position
            current_price: Current market price
            
        Returns:
            True if should sell
        """
        symbol = position.symbol
        
        # Track peak price for trailing
        if symbol not in self.trailing_peaks:
            self.trailing_peaks[symbol] = current_price
        else:
            self.trailing_peaks[symbol] = max(self.trailing_peaks[symbol], current_price)
        
        peak = self.trailing_peaks[symbol]
        
        # Calculate profit percentages
        unrealized_pnl_pct = position.unrealized_pnl_pct
        
        # Determine starting profit margin based on DCA count
        if position.dca_count == 0:
            start_pm = self.settings.trading.pm_start_pct_no_dca
        else:
            start_pm = self.settings.trading.pm_start_pct_with_dca
        
        # Check if we're in profit territory
        if unrealized_pnl_pct < start_pm:
            return False
        
        # Calculate trailing stop price
        trailing_gap_pct = self.settings.trading.trailing_gap_pct
        trailing_stop = peak * (1 - trailing_gap_pct / 100.0)
        
        # Check if price fell below trailing stop
        if current_price <= trailing_stop:
            logger.info(
                f"{symbol}: Trailing stop hit "
                f"(price ${current_price:.2f} <= stop ${trailing_stop:.2f}, "
                f"peak ${peak:.2f}, profit {unrealized_pnl_pct:.2f}%)"
            )
            return True
        
        return False
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        notional: float,
        tag: Optional[TradeTag] = None
    ) -> Optional[Order]:
        """Place a market order.
        
        Args:
            symbol: Trading symbol (e.g., "BTC-USD")
            side: Buy or sell
            notional: Dollar amount
            tag: Classification tag
            
        Returns:
            Order object if successful
        """
        try:
            order = await self.exchange.place_market_order(
                symbol=symbol,
                side=side,
                notional=notional
            )
            
            order.tag = tag
            self.orders[order.order_id] = order
            
            logger.info(
                f"Order placed: {side.value} ${notional:.2f} {symbol} "
                f"(tag: {tag.value if tag else 'none'})"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}", exc_info=True)
            return None
    
    async def manage_trades(self):
        """Main trading loop."""
        logger.info("Starting trading engine...")
        
        while True:
            try:
                # Get account status
                account = await self.get_account_balance()
                total_value = account['total_value']
                buying_power = account['buying_power']
                
                # Get current positions
                positions = await self.get_current_positions()
                self.positions = positions
                
                # Read neural signals
                signals = await self._read_signals()
                
                # Process each configured coin
                for coin in self.settings.trading.coins:
                    symbol = f"{coin}-USD"
                    
                    # Check if we have a position
                    if symbol in positions:
                        position = positions[symbol]
                        
                        # Get current price
                        quote = await self.get_quote(symbol)
                        current_price = quote['ask']
                        
                        # Update position with current price
                        position.current_price = current_price
                        position.market_value = position.quantity * current_price
                        position.unrealized_pnl = position.market_value - (position.quantity * position.avg_cost_basis)
                        position.unrealized_pnl_pct = (position.unrealized_pnl / (position.quantity * position.avg_cost_basis)) * 100
                        
                        # Check for take profit
                        if self._should_take_profit(position, current_price):
                            await self.place_order(
                                symbol=symbol,
                                side=OrderSide.SELL,
                                notional=position.market_value,
                                tag=TradeTag.TRAILING_STOP
                            )
                            
                            # Clear tracking
                            self.trailing_peaks.pop(symbol, None)
                            self.dca_history.pop(coin, None)
                            
                            continue
                        
                        # Check for DCA opportunity
                        dca_level = self._should_dca(position, current_price, signals)
                        if dca_level:
                            dca_size = self._calculate_position_size(
                                account_value=total_value,
                                symbol=symbol,
                                is_dca=True,
                                dca_multiplier=dca_level.position_size_multiplier
                            )
                            
                            if dca_size <= buying_power:
                                await self.place_order(
                                    symbol=symbol,
                                    side=OrderSide.BUY,
                                    notional=dca_size,
                                    tag=TradeTag.DCA
                                )
                                
                                # Record DCA time
                                if coin not in self.dca_history:
                                    self.dca_history[coin] = []
                                self.dca_history[coin].append(datetime.now())
                    
                    else:
                        # No position - check for entry signal
                        if self._should_start_trade(coin, signals):
                            position_size = self._calculate_position_size(
                                account_value=total_value,
                                symbol=symbol,
                                is_dca=False
                            )
                            
                            if position_size <= buying_power:
                                await self.place_order(
                                    symbol=symbol,
                                    side=OrderSide.BUY,
                                    notional=position_size,
                                    tag=TradeTag.ENTRY
                                )
                
                # Log status
                logger.info(
                    f"Status: ${total_value:.2f} total, "
                    f"${buying_power:.2f} available, "
                    f"{len(positions)} positions"
                )
                
                # Sleep before next iteration
                await asyncio.sleep(self.settings.signal_check_seconds)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _read_signals(self) -> Dict:
        """Read neural network signals from files (backward compatible).
        
        Returns:
            Dictionary of signals by coin
        """
        signals = {}
        
        for coin in self.settings.trading.coins:
            try:
                coin_dir = self.settings.get_coin_dir(coin)
                
                long_file = coin_dir / "long_dca_signal.txt"
                short_file = coin_dir / "short_dca_signal.txt"
                
                if long_file.exists() and short_file.exists():
                    long_strength = int(long_file.read_text().strip())
                    short_strength = int(short_file.read_text().strip())
                    
                    from models import NeuralSignal, SignalType
                    
                    signals[coin] = NeuralSignal(
                        symbol=coin,
                        timestamp=datetime.now(),
                        long_strength=long_strength,
                        short_strength=short_strength,
                        predictions={},
                        signal_type=SignalType.LONG if long_strength > short_strength else SignalType.SHORT,
                        confidence=0.5
                    )
            except Exception as e:
                logger.error(f"Error reading signals for {coin}: {e}")
        
        return signals


async def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    engine = TradingEngine()
    await engine.manage_trades()


if __name__ == "__main__":
    asyncio.run(main())
