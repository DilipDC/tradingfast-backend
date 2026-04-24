import random
import logging
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime
from db import db
from trading_engine import trading_engine

logger = logging.getLogger(__name__)

class AIEngine:
    """
    AI Engine that influences price movement based on:
    - Number of users per stock
    - Total amount on UP vs DOWN
    - Trade durations
    - Goal: maximize platform profit by creating realistic counter-trends
    """
    
    _instance = None
    _sentiment: Dict[int, float] = {}  # stock_id -> bias (-1 to 1, negative means DOWN bias)
    _last_update: Dict[int, datetime] = {}
    _update_interval_seconds = 10  # Update AI every 10 seconds
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def update_market_sentiment(self):
        """Update AI bias for all stocks based on current active trades"""
        try:
            # Get active trades grouped by stock
            stock_trades = trading_engine.get_active_trades_by_stock()
            
            for stock_id, data in stock_trades.items():
                up_count = data['UP']
                down_count = data['DOWN']
                up_amount = data['total_amount_up']
                down_amount = data['total_amount_down']
                total_trades = up_count + down_count
                
                if total_trades == 0:
                    # No active trades: natural random walk (neutral bias)
                    bias = 0.0
                else:
                    # Core AI logic: majority direction → AI opposes it (to maximize platform profit)
                    # If more users choose UP, AI pushes price DOWN (so they lose)
                    # If more users choose DOWN, AI pushes price UP
                    # The strength depends on the imbalance ratio and total amount
                    
                    # Direction: -1 means push DOWN, +1 means push UP
                    if up_count > down_count:
                        # Majority UP → AI pushes DOWN
                        direction = -1
                        majority_ratio = up_count / total_trades
                    elif down_count > up_count:
                        # Majority DOWN → AI pushes UP
                        direction = 1
                        majority_ratio = down_count / total_trades
                    else:
                        # Balanced: random but slight anti-trend
                        direction = random.choice([-0.5, 0.5])
                        majority_ratio = 0.5
                    
                    # Amount weight: higher total amount = stronger AI reaction
                    total_amount = up_amount + down_amount
                    max_amount = 100000  # normalize cap
                    amount_weight = min(1.0, total_amount / max_amount)
                    
                    # Duration factor: longer duration trades get stronger AI influence (more time to move)
                    # We need average duration from active trades - simplified: use default weight 0.7
                    duration_weight = 0.7
                    
                    # Calculate bias strength: between 0 and 0.6 (max push per update cycle)
                    # Too strong would cause unrealistic spikes
                    strength = majority_ratio * amount_weight * duration_weight * 0.4
                    
                    bias = direction * strength
                    
                    # Add small random noise to simulate market unpredictability
                    noise = random.uniform(-0.1, 0.1)
                    bias = max(-0.6, min(0.6, bias + noise))
                
                self._sentiment[stock_id] = bias
                self._last_update[stock_id] = datetime.now()
                
                if total_trades > 0:
                    logger.debug(f"AI bias for stock {stock_id}: {bias:.3f} (UP:{up_count}, DOWN:{down_count}, amt_up:{up_amount}, amt_down:{down_amount})")
            
        except Exception as e:
            logger.error(f"Error updating market sentiment: {str(e)}")
    
    def get_price_bias(self, stock_id: int) -> float:
        """
        Get current price bias for a stock.
        Returns float between -0.6 and 0.6.
        Positive means push price UP, negative means push DOWN.
        """
        # If no active trades, return slight random drift
        if stock_id not in self._sentiment:
            # Small random walk when idle
            return random.uniform(-0.1, 0.1)
        
        bias = self._sentiment.get(stock_id, 0.0)
        
        # Decay bias over time if no new trades
        last = self._last_update.get(stock_id)
        if last:
            seconds_since = (datetime.now() - last).total_seconds()
            if seconds_since > 30:
                # Decay bias to zero
                decay = max(0, 1 - (seconds_since - 30) / 60)
                bias *= decay
        
        return max(-0.6, min(0.6, bias))
    
    def get_market_insights(self) -> Dict:
        """Get AI market insights for admin dashboard"""
        insights = {}
        for stock_id, bias in self._sentiment.items():
            stock = db.fetch_one('stocks', {'id': stock_id})
            if stock:
                direction = "BULLISH" if bias > 0.2 else "BEARISH" if bias < -0.2 else "NEUTRAL"
                insights[stock['symbol']] = {
                    'bias': round(bias, 3),
                    'direction': direction,
                    'strength': abs(round(bias, 2))
                }
        return insights
    
    def simulate_whale_trade(self, stock_id: int, amount: float, direction: str):
        """
        Simulate a large "whale" trade to influence AI behavior.
        This can be used by admin to manipulate market.
        """
        # Add artificial weight to the stock's sentiment
        current_bias = self._sentiment.get(stock_id, 0.0)
        # Whale pushing opposite direction to current majority
        whale_effect = 0.3 if direction == 'UP' else -0.3
        # Scale by amount
        effect_strength = min(0.4, amount / 50000) * 0.3
        new_bias = current_bias + (whale_effect * effect_strength)
        self._sentiment[stock_id] = max(-0.6, min(0.6, new_bias))
        self._last_update[stock_id] = datetime.now()
        logger.info(f"Whale trade simulated on stock {stock_id}: {direction} ₹{amount}, AI bias adjusted to {self._sentiment[stock_id]:.3f}")

# Singleton instance
ai_engine = AIEngine()