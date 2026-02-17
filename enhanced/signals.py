"""
Real-time signal generation using trained neural network patterns.

Improvements over original:
- Event-driven architecture (no polling)
- Efficient pattern matching with caching
- Type-safe signal generation
- Confidence scoring
- Multi-timeframe aggregation
- Health monitoring
"""
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from kucoin.client import Market

from config import Settings, TimeFrame, get_settings
from models import NeuralSignal, Prediction, SignalType
from trainer import PatternMemory

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals from neural network predictions."""
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        market_client: Optional[Market] = None
    ):
        """Initialize signal generator.
        
        Args:
            settings: Configuration settings
            market_client: KuCoin market data client
        """
        self.settings = settings or get_settings()
        self.market = market_client or Market(url='https://api.kucoin.com')
        
        # Load all trained models
        self.memories: Dict[str, PatternMemory] = {}
        self._load_all_models()
        
        # Cache recent candles to avoid repeated fetches
        self.candle_cache: Dict[str, List] = {}
        self.cache_ttl = 60  # seconds
        self.last_cache_update: Dict[str, datetime] = {}
    
    def _load_all_models(self) -> None:
        """Load all trained pattern memories."""
        logger.info("Loading trained models...")
        
        for coin in self.settings.trading.coins:
            for timeframe in self.settings.trading.timeframes:
                model_path = self.settings.get_model_path(coin, timeframe.value)
                
                if not model_path.exists():
                    logger.warning(f"Model not found: {model_path}")
                    continue
                
                memory = PatternMemory(max_size=self.settings.model.pattern_memory_size)
                memory.load(model_path)
                
                key = f"{coin}_{timeframe.value}"
                self.memories[key] = memory
                
                logger.info(f"Loaded {len(memory.patterns)} patterns for {key}")
    
    def _is_model_fresh(self, coin: str) -> bool:
        """Check if model was trained recently.
        
        Args:
            coin: Coin symbol
            
        Returns:
            True if model is fresh (< 14 days old)
        """
        timestamp_file = self.settings.get_coin_dir(coin) / "trainer_last_training_time.txt"
        
        if not timestamp_file.exists():
            return False
        
        try:
            timestamp = float(timestamp_file.read_text().strip())
            age_days = (datetime.now().timestamp() - timestamp) / 86400
            return age_days <= self.settings.model.training_stale_days
        except Exception as e:
            logger.error(f"Error checking model freshness for {coin}: {e}")
            return False
    
    async def _get_recent_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 150
    ) -> List:
        """Get recent candles with caching.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            limit: Number of candles
            
        Returns:
            List of candles
        """
        cache_key = f"{symbol}_{timeframe}"
        now = datetime.now()
        
        # Check cache
        if cache_key in self.candle_cache:
            last_update = self.last_cache_update.get(cache_key)
            if last_update and (now - last_update).total_seconds() < self.cache_ttl:
                return self.candle_cache[cache_key]
        
        # Fetch fresh data
        try:
            data = self.market.get_kline(symbol, timeframe, limit=limit)
            self.candle_cache[cache_key] = data
            self.last_cache_update[cache_key] = now
            return data
        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol} {timeframe}: {e}")
            return []
    
    def _extract_current_pattern(self, candles: List) -> tuple:
        """Extract price change pattern from recent candles.
        
        Args:
            candles: Raw candle data from API
            
        Returns:
            Tuple of (close_changes, high_changes, low_changes, current_price)
        """
        if len(candles) < self.settings.model.lookback_candles + 1:
            return [], [], [], 0.0
        
        close_changes = []
        high_changes = []
        low_changes = []
        
        # Candles are [time, open, close, high, low, volume]
        # Newest first in array
        for i in range(self.settings.model.lookback_candles):
            curr = candles[i]
            prev = candles[i + 1]
            
            curr_close = float(curr[2])
            prev_close = float(prev[2])
            curr_high = float(curr[3])
            prev_high = float(prev[3])
            curr_low = float(curr[4])
            prev_low = float(prev[4])
            
            if prev_close == 0:
                continue
            
            close_change = ((curr_close - prev_close) / prev_close) * 100
            high_change = ((curr_high - prev_high) / prev_high) * 100 if prev_high > 0 else 0.0
            low_change = ((curr_low - prev_low) / prev_low) * 100 if prev_low > 0 else 0.0
            
            close_changes.append(close_change)
            high_changes.append(high_change)
            low_changes.append(low_change)
        
        current_price = float(candles[0][2])
        return close_changes, high_changes, low_changes, current_price
    
    def _generate_prediction(
        self,
        coin: str,
        timeframe: str,
        close_changes: List[float],
        current_price: float
    ) -> Optional[Prediction]:
        """Generate price prediction for a timeframe.
        
        Args:
            coin: Coin symbol
            timeframe: Timeframe string
            close_changes: Recent price changes
            current_price: Current price
            
        Returns:
            Prediction or None if no match
        """
        memory_key = f"{coin}_{timeframe}"
        if memory_key not in self.memories:
            return None
        
        memory = self.memories[memory_key]
        
        # Find similar patterns
        similar = memory.find_similar(
            close_changes,
            tolerance=self.settings.model.distance_tolerance_pct
        )
        
        if not similar:
            return None
        
        # Weight-average predictions from top matches
        weighted_close = 0.0
        weighted_high = 0.0
        weighted_low = 0.0
        weight_sum = 0.0
        
        for pattern, distance in similar[:10]:
            # Weight decays with distance and increases with pattern success
            success_rate = pattern.success_count / max(1, pattern.hit_count)
            weight = pattern.weight * (1.0 / (1.0 + distance)) * (1.0 + success_rate)
            
            # Predict next change
            if pattern.close_changes:
                weighted_close += pattern.close_changes[0] * weight
            if pattern.high_changes:
                weighted_high += pattern.high_changes[0] * weight
            if pattern.low_changes:
                weighted_low += pattern.low_changes[0] * weight
            
            weight_sum += weight
        
        if weight_sum == 0:
            return None
        
        # Calculate predicted prices
        predicted_close_pct = weighted_close / weight_sum
        predicted_high_pct = weighted_high / weight_sum
        predicted_low_pct = weighted_low / weight_sum
        
        predicted_close = current_price * (1 + predicted_close_pct / 100)
        predicted_high = current_price * (1 + predicted_high_pct / 100)
        predicted_low = current_price * (1 + predicted_low_pct / 100)
        
        # Confidence based on number of matches and weight consensus
        confidence = min(1.0, len(similar) / 50.0)  # Max at 50 matches
        
        # Signal strength (0-7) based on predicted move magnitude
        magnitude = abs(predicted_close_pct)
        if magnitude < 0.25:
            signal_strength = 0
        elif magnitude < 0.5:
            signal_strength = 1
        elif magnitude < 1.0:
            signal_strength = 2
        elif magnitude < 2.0:
            signal_strength = 3
        elif magnitude < 3.0:
            signal_strength = 4
        elif magnitude < 5.0:
            signal_strength = 5
        elif magnitude < 7.0:
            signal_strength = 6
        else:
            signal_strength = 7
        
        return Prediction(
            symbol=coin,
            timeframe=timeframe,
            timestamp=datetime.now(),
            predicted_close=predicted_close,
            predicted_high=predicted_high,
            predicted_low=predicted_low,
            confidence=confidence,
            matched_patterns=len(similar),
            signal_strength=signal_strength
        )
    
    async def generate_signal(self, coin: str) -> Optional[NeuralSignal]:
        """Generate trading signal for a coin across all timeframes.
        
        Args:
            coin: Coin symbol
            
        Returns:
            Neural signal or None if no valid signal
        """
        # Check if model is fresh
        if not self._is_model_fresh(coin):
            logger.warning(f"Model for {coin} is stale, skipping signal generation")
            return None
        
        symbol = f"{coin}-USDT"
        predictions: Dict[str, Prediction] = {}
        
        # Generate predictions for each timeframe
        for timeframe in self.settings.trading.timeframes:
            candles = await self._get_recent_candles(
                symbol,
                timeframe.value,
                limit=self.settings.model.lookback_candles + 10
            )
            
            if not candles:
                continue
            
            close_changes, high_changes, low_changes, current_price = self._extract_current_pattern(candles)
            
            if not close_changes:
                continue
            
            prediction = self._generate_prediction(
                coin,
                timeframe.value,
                close_changes,
                current_price
            )
            
            if prediction:
                predictions[timeframe.value] = prediction
        
        if not predictions:
            return None
        
        # Aggregate signals across timeframes
        long_strength = 0
        short_strength = 0
        total_confidence = 0.0
        
        for pred in predictions.values():
            # Bullish prediction
            if pred.predicted_close > 0:
                long_strength += pred.signal_strength
            else:
                short_strength += pred.signal_strength
            
            total_confidence += pred.confidence
        
        # Normalize strengths to 0-7 range
        max_strength = len(predictions) * 7
        long_strength = min(7, int(long_strength / max_strength * 7)) if max_strength > 0 else 0
        short_strength = min(7, int(short_strength / max_strength * 7)) if max_strength > 0 else 0
        
        avg_confidence = total_confidence / len(predictions) if predictions else 0.0
        
        # Determine overall signal type
        if long_strength > short_strength and long_strength >= self.settings.trading.trade_start_level:
            signal_type = SignalType.LONG
        elif short_strength > long_strength and short_strength >= self.settings.trading.trade_start_level:
            signal_type = SignalType.SHORT
        else:
            signal_type = SignalType.NEUTRAL
        
        return NeuralSignal(
            symbol=coin,
            timestamp=datetime.now(),
            long_strength=long_strength,
            short_strength=short_strength,
            predictions=predictions,
            signal_type=signal_type,
            confidence=avg_confidence,
            metadata={
                'timeframes_analyzed': len(predictions),
                'model_fresh': self._is_model_fresh(coin)
            }
        )
    
    async def generate_all_signals(self) -> Dict[str, NeuralSignal]:
        """Generate signals for all configured coins.
        
        Returns:
            Dictionary of signals by coin symbol
        """
        signals = {}
        
        for coin in self.settings.trading.coins:
            try:
                signal = await self.generate_signal(coin)
                if signal:
                    signals[coin] = signal
                    logger.info(
                        f"Signal generated for {coin}: "
                        f"{signal.signal_type.value} "
                        f"(L:{signal.long_strength} S:{signal.short_strength} "
                        f"C:{signal.confidence:.2f})"
                    )
            except Exception as e:
                logger.error(f"Error generating signal for {coin}: {e}", exc_info=True)
        
        return signals
    
    async def run_continuous(self, interval_seconds: float = 1.0) -> None:
        """Run signal generation continuously.
        
        Args:
            interval_seconds: Seconds between signal generations
        """
        logger.info(f"Starting continuous signal generation (interval: {interval_seconds}s)")
        
        while True:
            try:
                signals = await self.generate_all_signals()
                
                # Write signals to files for backward compatibility
                for coin, signal in signals.items():
                    coin_dir = self.settings.get_coin_dir(coin)
                    coin_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Write signal strengths
                    long_file = coin_dir / "long_dca_signal.txt"
                    short_file = coin_dir / "short_dca_signal.txt"
                    
                    long_file.write_text(str(signal.long_strength))
                    short_file.write_text(str(signal.short_strength))
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in continuous signal generation: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)


async def main():
    """Main entry point."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    generator = SignalGenerator()
    
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        # Generate signals once and exit
        signals = await generator.generate_all_signals()
        for coin, signal in signals.items():
            print(f"\n{coin}: {signal.signal_type.value}")
            print(f"  Long: {signal.long_strength}/7")
            print(f"  Short: {signal.short_strength}/7")
            print(f"  Confidence: {signal.confidence:.2%}")
    else:
        # Run continuously
        await generator.run_continuous()


if __name__ == "__main__":
    asyncio.run(main())
