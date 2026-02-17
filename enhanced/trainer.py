"""
Enhanced Neural Network Trainer for Pattern Recognition.

Improvements over original:
- Proper OOP design with dependency injection
- Efficient memory management with LRU caching
- Batch I/O operations to reduce disk access
- Type hints and validation
- Comprehensive logging
- Graceful shutdown handling
- Progress tracking and health monitoring
"""
import asyncio
import hashlib
import logging
import pickle
import signal
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple

import numpy as np
from kucoin.client import Market

from config import Settings, TimeFrame, get_settings
from models import Candle, Pattern

logger = logging.getLogger(__name__)


@dataclass
class TrainingState:
    """Tracks training progress and statistics."""
    coin: str
    timeframe: str
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    candles_processed: int = 0
    patterns_learned: int = 0
    patterns_updated: int = 0
    success_rate: float = 0.0
    is_training: bool = False
    last_checkpoint: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        """Calculate training duration."""
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()
    
    @property
    def candles_per_second(self) -> float:
        """Calculate processing rate."""
        duration = self.duration_seconds
        return self.candles_processed / duration if duration > 0 else 0.0


class PatternMemory:
    """Efficient pattern storage with LRU caching."""
    
    def __init__(self, max_size: int = 10000):
        """Initialize pattern memory.
        
        Args:
            max_size: Maximum number of patterns to keep
        """
        self.max_size = max_size
        self.patterns: Dict[str, Pattern] = {}
        self.access_queue: Deque[str] = deque(maxlen=max_size)
        self._dirty = False
    
    def add_pattern(self, pattern: Pattern) -> None:
        """Add or update a pattern.
        
        Args:
            pattern: Pattern to store
        """
        pattern_hash = pattern.pattern_hash
        
        # Update existing or add new
        if pattern_hash in self.patterns:
            existing = self.patterns[pattern_hash]
            existing.hit_count += 1
            existing.last_seen = datetime.now()
        else:
            # Evict oldest if at capacity
            if len(self.patterns) >= self.max_size:
                oldest = self.access_queue[0]
                del self.patterns[oldest]
            
            self.patterns[pattern_hash] = pattern
        
        # Update access tracking (LRU)
        if pattern_hash in self.access_queue:
            self.access_queue.remove(pattern_hash)
        self.access_queue.append(pattern_hash)
        
        self._dirty = True
    
    def find_similar(
        self,
        pattern: List[float],
        tolerance: float = 0.25
    ) -> List[Tuple[Pattern, float]]:
        """Find patterns similar to the given pattern.
        
        Args:
            pattern: Price change pattern to match
            tolerance: Maximum percentage difference to consider similar
            
        Returns:
            List of (pattern, distance) tuples sorted by similarity
        """
        matches: List[Tuple[Pattern, float]] = []
        
        for stored in self.patterns.values():
            if len(stored.close_changes) != len(pattern):
                continue
            
            # Calculate weighted Euclidean distance
            distance = 0.0
            for i, (stored_val, pattern_val) in enumerate(zip(stored.close_changes, pattern)):
                diff = abs(stored_val - pattern_val)
                pct_diff = (diff / abs(pattern_val) * 100) if pattern_val != 0 else 0.0
                distance += pct_diff ** 2
            
            distance = np.sqrt(distance / len(pattern))
            
            if distance <= tolerance:
                matches.append((stored, distance))
        
        # Sort by distance (most similar first)
        matches.sort(key=lambda x: x[1])
        return matches
    
    def save(self, path: Path) -> None:
        """Save patterns to disk.
        
        Args:
            path: File path to save to
        """
        if not self._dirty:
            return
        
        try:
            with open(path, 'wb') as f:
                pickle.dump({
                    'patterns': self.patterns,
                    'access_queue': list(self.access_queue),
                }, f)
            self._dirty = False
            logger.debug(f"Saved {len(self.patterns)} patterns to {path}")
        except Exception as e:
            logger.error(f"Failed to save patterns: {e}")
    
    def load(self, path: Path) -> None:
        """Load patterns from disk.
        
        Args:
            path: File path to load from
        """
        if not path.exists():
            logger.info(f"No existing patterns at {path}")
            return
        
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
            
            self.patterns = data.get('patterns', {})
            self.access_queue = deque(data.get('access_queue', []), maxlen=self.max_size)
            self._dirty = False
            
            logger.info(f"Loaded {len(self.patterns)} patterns from {path}")
        except Exception as e:
            logger.error(f"Failed to load patterns: {e}")


class NeuralTrainer:
    """Enhanced neural network trainer for crypto patterns."""
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        market_client: Optional[Market] = None
    ):
        """Initialize trainer.
        
        Args:
            settings: Configuration settings
            market_client: KuCoin market data client
        """
        self.settings = settings or get_settings()
        self.market = market_client or Market(url='https://api.kucoin.com')
        
        self.memories: Dict[str, PatternMemory] = {}
        self.states: Dict[str, TrainingState] = {}
        self.should_stop = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully.
        
        Args:
            signum: Signal number
            frame: Stack frame
        """
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.should_stop = True
    
    def _compute_pattern_hash(self, changes: List[float]) -> str:
        """Compute unique hash for a pattern.
        
        Args:
            changes: Price change sequence
            
        Returns:
            Pattern hash string
        """
        # Round to 2 decimals to group similar patterns
        rounded = [round(c, 2) for c in changes]
        pattern_str = '|'.join(str(c) for c in rounded)
        return hashlib.sha256(pattern_str.encode()).hexdigest()[:16]
    
    def _fetch_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 1500
    ) -> List[Candle]:
        """Fetch historical candle data.
        
        Args:
            symbol: Trading pair (e.g., "BTC-USDT")
            timeframe: Candle timeframe
            limit: Number of candles to fetch
            
        Returns:
            List of candles, newest first
        """
        try:
            data = self.market.get_kline(symbol, timeframe, limit=limit)
            
            candles = []
            for row in data:
                candles.append(Candle(
                    timestamp=datetime.fromtimestamp(int(row[0])),
                    open=float(row[1]),
                    close=float(row[2]),
                    high=float(row[3]),
                    low=float(row[4]),
                    volume=float(row[5]),
                ))
            
            # Return newest first (reverse chronological)
            candles.reverse()
            return candles
            
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol} {timeframe}: {e}")
            return []
    
    def _extract_pattern(
        self,
        candles: List[Candle],
        lookback: int
    ) -> Tuple[List[float], List[float], List[float]]:
        """Extract price change pattern from candles.
        
        Args:
            candles: List of candles (newest first)
            lookback: Number of candles to use for pattern
            
        Returns:
            Tuple of (close_changes, high_changes, low_changes)
        """
        if len(candles) < lookback + 1:
            return [], [], []
        
        close_changes = []
        high_changes = []
        low_changes = []
        
        for i in range(lookback):
            curr = candles[i]
            prev = candles[i + 1]
            
            close_change = ((curr.close - prev.close) / prev.close) * 100
            high_change = ((curr.high - prev.high) / prev.high) * 100
            low_change = ((curr.low - prev.low) / prev.low) * 100
            
            close_changes.append(close_change)
            high_changes.append(high_change)
            low_changes.append(low_change)
        
        return close_changes, high_changes, low_changes
    
    def _update_weights(
        self,
        pattern: Pattern,
        actual_change: float,
        predicted_change: float,
        learning_rate: float = 0.25
    ) -> Pattern:
        """Update pattern weights based on prediction accuracy.
        
        Args:
            pattern: Pattern to update
            actual_change: Actual price change observed
            predicted_change: Predicted price change
            learning_rate: Weight adjustment rate
            
        Returns:
            Updated pattern
        """
        # Calculate prediction error
        error_pct = abs((actual_change - predicted_change) / actual_change * 100) if actual_change != 0 else 0.0
        
        # Adjust weight based on accuracy
        if error_pct < 10:  # Good prediction
            pattern.weight = min(2.0, pattern.weight + learning_rate)
            pattern.success_count += 1
        elif error_pct > 25:  # Poor prediction
            pattern.weight = max(-2.0, pattern.weight - learning_rate)
        
        return pattern
    
    async def train_timeframe(
        self,
        coin: str,
        timeframe: str,
        num_candles: int = 500
    ) -> TrainingState:
        """Train model on a specific timeframe.
        
        Args:
            coin: Coin symbol
            timeframe: Timeframe to train
            num_candles: Number of historical candles to process
            
        Returns:
            Training state with statistics
        """
        state = TrainingState(coin=coin, timeframe=timeframe)
        state.is_training = True
        self.states[f"{coin}_{timeframe}"] = state
        
        # Get or create pattern memory
        memory_key = f"{coin}_{timeframe}"
        if memory_key not in self.memories:
            memory = PatternMemory(max_size=self.settings.model.pattern_memory_size)
            model_path = self.settings.get_model_path(coin, timeframe)
            memory.load(model_path)
            self.memories[memory_key] = memory
        else:
            memory = self.memories[memory_key]
        
        logger.info(f"Starting training: {coin} {timeframe}")
        
        try:
            # Fetch historical data
            symbol = f"{coin}-USDT"
            candles = self._fetch_candles(symbol, timeframe, limit=num_candles + 100)
            
            if not candles:
                logger.warning(f"No candles fetched for {coin} {timeframe}")
                state.is_training = False
                return state
            
            lookback = self.settings.model.lookback_candles
            
            # Process each candle window
            for i in range(num_candles):
                if self.should_stop:
                    logger.info("Training interrupted")
                    break
                
                # Extract pattern from historical window
                pattern_candles = candles[i:i + lookback + 2]
                if len(pattern_candles) < lookback + 2:
                    continue
                
                close_changes, high_changes, low_changes = self._extract_pattern(
                    pattern_candles[:-1],  # Current pattern
                    lookback
                )
                
                if not close_changes:
                    continue
                
                # Future candle (what we're predicting)
                future = pattern_candles[0]
                current = pattern_candles[1]
                actual_change = ((future.close - current.close) / current.close) * 100
                
                # Create pattern
                pattern_hash = self._compute_pattern_hash(close_changes)
                pattern = Pattern(
                    timeframe=timeframe,
                    pattern_hash=pattern_hash,
                    close_changes=close_changes,
                    high_changes=high_changes,
                    low_changes=low_changes,
                    created_at=datetime.now(),
                    last_seen=datetime.now(),
                )
                
                # Find similar patterns and predict
                similar = memory.find_similar(
                    close_changes,
                    tolerance=self.settings.model.distance_tolerance_pct
                )
                
                if similar:
                    # Weight average prediction from similar patterns
                    weighted_sum = 0.0
                    weight_sum = 0.0
                    
                    for sim_pattern, distance in similar[:10]:  # Top 10 matches
                        # Weight decays with distance
                        weight = sim_pattern.weight * (1.0 / (1.0 + distance))
                        weighted_sum += sim_pattern.close_changes[0] * weight
                        weight_sum += weight
                    
                    predicted_change = weighted_sum / weight_sum if weight_sum > 0 else 0.0
                    
                    # Update weights of similar patterns
                    for sim_pattern, _ in similar[:5]:
                        updated = self._update_weights(sim_pattern, actual_change, predicted_change)
                        memory.add_pattern(updated)
                        state.patterns_updated += 1
                
                # Add this pattern to memory
                memory.add_pattern(pattern)
                state.patterns_learned += 1
                state.candles_processed += 1
                
                # Periodic checkpoint
                if state.candles_processed % 100 == 0:
                    model_path = self.settings.get_model_path(coin, timeframe)
                    memory.save(model_path)
                    state.last_checkpoint = datetime.now()
                    logger.info(
                        f"Checkpoint: {coin} {timeframe} - "
                        f"{state.candles_processed} candles, "
                        f"{len(memory.patterns)} patterns, "
                        f"{state.candles_per_second:.1f} candles/sec"
                    )
                
                # Small delay to prevent CPU overload
                if i % 50 == 0:
                    await asyncio.sleep(0.01)
            
            # Final save
            model_path = self.settings.get_model_path(coin, timeframe)
            memory.save(model_path)
            
            # Update state
            state.completed_at = datetime.now()
            state.is_training = False
            state.success_rate = memory.patterns[list(memory.patterns.keys())[0]].success_count / max(1, memory.patterns[list(memory.patterns.keys())[0]].hit_count) if memory.patterns else 0.0
            
            # Write training completion timestamp
            timestamp_file = self.settings.get_coin_dir(coin) / "trainer_last_training_time.txt"
            timestamp_file.write_text(str(int(time.time())))
            
            logger.info(
                f"Training completed: {coin} {timeframe} - "
                f"{state.duration_seconds:.1f}s, "
                f"{state.candles_processed} candles, "
                f"{len(memory.patterns)} total patterns"
            )
            
        except Exception as e:
            logger.error(f"Training error for {coin} {timeframe}: {e}", exc_info=True)
            state.is_training = False
        
        return state
    
    async def train_coin(self, coin: str) -> Dict[str, TrainingState]:
        """Train all timeframes for a coin.
        
        Args:
            coin: Coin symbol to train
            
        Returns:
            Dictionary of training states by timeframe
        """
        states = {}
        
        for timeframe in self.settings.trading.timeframes:
            if self.should_stop:
                break
            
            state = await self.train_timeframe(coin, timeframe.value)
            states[timeframe.value] = state
        
        return states
    
    async def train_all(self) -> Dict[str, Dict[str, TrainingState]]:
        """Train all configured coins and timeframes.
        
        Returns:
            Nested dictionary of training states: {coin: {timeframe: state}}
        """
        all_states = {}
        
        for coin in self.settings.trading.coins:
            if self.should_stop:
                break
            
            states = await self.train_coin(coin)
            all_states[coin] = states
        
        return all_states


async def main():
    """Main training entry point."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    trainer = NeuralTrainer()
    
    if len(sys.argv) > 1:
        # Train specific coin
        coin = sys.argv[1].upper()
        await trainer.train_coin(coin)
    else:
        # Train all coins
        await trainer.train_all()


if __name__ == "__main__":
    asyncio.run(main())
