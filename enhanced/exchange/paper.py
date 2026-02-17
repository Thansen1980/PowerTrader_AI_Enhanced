"""
Paper Trading Exchange - Simulates trading without real money.

Perfect for testing strategies safely.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from config import Settings
from models import Order, OrderSide, OrderStatus, Position

logger = logging.getLogger(__name__)


class PaperExchange:
    """Simulated exchange for paper trading."""
    
    def __init__(self, settings: Settings):
        """Initialize paper exchange.
        
        Args:
            settings: Configuration settings
        """
        self.settings = settings
        
        # Simulated account
        self.cash = 10000.0  # Starting cash
        self.positions: Dict[str, Dict] = {}
        self.orders: List[Order] = []
        
        logger.info(f"Paper exchange initialized with ${self.cash:.2f}")
    
    async def get_account(self) -> Dict:
        """Get simulated account balance."""
        positions_value = sum(
            pos['quantity'] * pos['current_price']
            for pos in self.positions.values()
        )
        
        total_value = self.cash + positions_value
        
        return {
            'total_value': total_value,
            'buying_power': self.cash,
            'positions_value': positions_value
        }
    
    async def get_positions(self) -> Dict[str, Position]:
        """Get all simulated positions."""
        positions = {}
        
        for symbol, pos_data in self.positions.items():
            # Get current price (simulated)
            current_price = await self._get_simulated_price(symbol)
            
            market_value = pos_data['quantity'] * current_price
            unrealized_pnl = market_value - (pos_data['quantity'] * pos_data['avg_cost'])
            unrealized_pnl_pct = (unrealized_pnl / (pos_data['quantity'] * pos_data['avg_cost'])) * 100
            
            positions[symbol] = Position(
                symbol=symbol,
                quantity=pos_data['quantity'],
                avg_cost_basis=pos_data['avg_cost'],
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                realized_pnl=pos_data.get('realized_pnl', 0.0),
                dca_count=pos_data.get('dca_count', 0),
                entry_time=pos_data['entry_time'],
                last_update=datetime.now()
            )
        
        return positions
    
    async def get_quote(self, symbol: str) -> Dict:
        """Get simulated quote."""
        price = await self._get_simulated_price(symbol)
        
        # Simulate spread (0.1%)
        spread = price * 0.001
        
        return {
            'bid': price - spread / 2,
            'ask': price + spread / 2,
            'timestamp': datetime.now()
        }
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        notional: float
    ) -> Order:
        """Simulate placing a market order.
        
        Args:
            symbol: Trading symbol
            side: Buy or sell
            notional: Dollar amount
            
        Returns:
            Simulated order
        """
        # Get current price
        quote = await self.get_quote(symbol)
        price = quote['ask'] if side == OrderSide.BUY else quote['bid']
        
        # Calculate quantity
        quantity = notional / price
        
        # Create order
        order = Order(
            order_id=str(uuid.uuid4()),
            client_order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            type="market",
            quantity=quantity,
            notional=notional,
            price=price,
            status=OrderStatus.FILLED,  # Instant fill in paper trading
            filled_quantity=quantity,
            average_fill_price=price,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Execute order
        if side == OrderSide.BUY:
            self._execute_buy(symbol, quantity, price)
        else:
            self._execute_sell(symbol, quantity, price)
        
        self.orders.append(order)
        
        logger.info(
            f"PAPER: {side.value} {quantity:.6f} {symbol} @ ${price:.2f} "
            f"(${notional:.2f})"
        )
        
        return order
    
    def _execute_buy(self, symbol: str, quantity: float, price: float):
        """Execute simulated buy."""
        cost = quantity * price
        
        if cost > self.cash:
            raise ValueError(f"Insufficient funds: ${cost:.2f} > ${self.cash:.2f}")
        
        self.cash -= cost
        
        if symbol in self.positions:
            # Add to existing position
            pos = self.positions[symbol]
            total_cost = (pos['quantity'] * pos['avg_cost']) + cost
            total_quantity = pos['quantity'] + quantity
            pos['avg_cost'] = total_cost / total_quantity
            pos['quantity'] = total_quantity
            pos['dca_count'] = pos.get('dca_count', 0) + 1
        else:
            # New position
            self.positions[symbol] = {
                'quantity': quantity,
                'avg_cost': price,
                'current_price': price,
                'entry_time': datetime.now(),
                'dca_count': 0,
                'realized_pnl': 0.0
            }
    
    def _execute_sell(self, symbol: str, quantity: float, price: float):
        """Execute simulated sell."""
        if symbol not in self.positions:
            raise ValueError(f"No position in {symbol}")
        
        pos = self.positions[symbol]
        
        if quantity > pos['quantity']:
            raise ValueError(
                f"Insufficient quantity: {quantity} > {pos['quantity']}"
            )
        
        # Calculate P&L
        proceeds = quantity * price
        cost_basis = quantity * pos['avg_cost']
        realized_pnl = proceeds - cost_basis
        
        self.cash += proceeds
        pos['realized_pnl'] = pos.get('realized_pnl', 0.0) + realized_pnl
        
        # Update or close position
        if quantity >= pos['quantity']:
            logger.info(f"PAPER: Closed position in {symbol}, P&L: ${realized_pnl:.2f}")
            del self.positions[symbol]
        else:
            pos['quantity'] -= quantity
    
    async def _get_simulated_price(self, symbol: str) -> float:
        """Get simulated price from real market data.
        
        For paper trading realism, we fetch real prices.
        """
        try:
            from kucoin.client import Market
            market = Market(url='https://api.kucoin.com')
            
            # Convert BTC-USD to BTC-USDT for KuCoin
            coin = symbol.replace("-USD", "")
            kucoin_symbol = f"{coin}-USDT"
            
            ticker = market.get_ticker(kucoin_symbol)
            return float(ticker['price'])
            
        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            # Return last known price or default
            if symbol in self.positions:
                return self.positions[symbol].get('current_price', 50000.0)
            return 50000.0  # Fallback
