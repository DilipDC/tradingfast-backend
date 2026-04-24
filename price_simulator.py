import threading
import time
import random
import math
import logging
from typing import Dict, Optional
from db import db
from config import Config
from ai_engine import ai_engine

logger = logging.getLogger(__name__)

class PriceSimulator:
    """
    Real-time price simulator for all stocks.
    Updates every 0.5 seconds with smooth movement.
    """
    
    _instance = None
    _prices: Dict[int, float] = {}
    _target_prices: Dict[int, float] = {}
    _trend_strength: Dict[int, float] = {}
    _thread = None
    _running = False
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def start(self):
        """Start the price simulation thread"""
        if self._running:
            return
        
        # Load initial prices from database
        self._load_prices_from_db()
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Price simulator started")
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Price simulator stopped")
    
    def _load_prices_from_db(self):
        """Load current prices from stocks table"""
        stocks = db.fetch_all('stocks', {'is_active': True})
        with self._lock:
            for stock in stocks:
                stock_id = stock['id']
                price = float(stock['price'])
                self._prices[stock_id] = price
                self._target_prices[stock_id] = price
                self._trend_strength[stock_id] = 0.0
    
    def _run_loop(self):
        """Main price update loop"""
        interval_sec = Config.PRICE_UPDATE_INTERVAL_MS / 1000.0
        
        while self._running:
            try:
                self._update_all_prices()
                time.sleep(interval_sec)
            except Exception as e:
                logger.error(f"Error in price simulator: {str(e)}")
                time.sleep(1)
    
    def _update_all_prices(self):
        """Update prices for all active stocks"""
        stocks = db.fetch_all('stocks', {'is_active': True})
        
        for stock in stocks:
            stock_id = stock['id']
            min_price = float(stock['min_price'])
            max_price = float(stock['max_price'])
            
            with self._lock:
                current = self._prices.get(stock_id, float(stock['price']))
            
            # Get AI direction bias for this stock
            ai_bias = ai_engine.get_price_bias(stock_id)
            
            # Random walk with AI bias and smoothness
            # Max change per tick: 0.2% of current price, scaled to 0.5% for volatility
            max_change_pct = 0.002  # 0.2% per tick
            volatility = random.uniform(0.5, 1.5)
            change_pct = random.uniform(-max_change_pct, max_change_pct) * volatility
            
            # Apply AI bias (force trend in a direction)
            if ai_bias != 0:
                bias_strength = min(0.003, abs(ai_bias) * 0.001)
                change_pct += bias_strength * (1 if ai_bias > 0 else -1)
            
            new_price = current * (1 + change_pct)
            
            # Apply trend strength smoothing (avoid spikes)
            with self._lock:
                trend = self._trend_strength.get(stock_id, 0)
                # Trend persistence: if change is same direction as previous trend, strengthen
                if (change_pct > 0 and trend > 0) or (change_pct < 0 and trend < 0):
                    trend = min(trend + change_pct * 10, 0.01)
                else:
                    trend = change_pct * 5
                self._trend_strength[stock_id] = max(-0.01, min(0.01, trend))
                # Blend with trend for smoothness
                new_price = current * (1 + trend)
            
            # Clamp to min/max
            new_price = max(min_price, min(max_price, new_price))
            
            # Update price in memory and database
            with self._lock:
                self._prices[stock_id] = new_price
            
            # Update database (every ~0.5s, but avoid too many writes)
            self._update_price_db(stock_id, new_price)
    
    def _update_price_db(self, stock_id: int, price: float):
        """Update stock price in database with throttling"""
        # Write to DB every 5 seconds to avoid overload
        current_time = time.time()
        if not hasattr(self, '_last_db_update'):
            self._last_db_update = {}
        
        last = self._last_db_update.get(stock_id, 0)
        if current_time - last >= 5.0:
            db.update('stocks', {'price': price}, {'id': stock_id})
            self._last_db_update[stock_id] = current_time
            logger.debug(f"Stock {stock_id} price updated to {price:.2f}")
    
    def get_price(self, stock_id: int) -> Optional[float]:
        """Get current price for a stock"""
        with self._lock:
            return self._prices.get(stock_id)
    
    def get_all_prices(self) -> Dict[int, float]:
        """Get all current prices"""
        with self._lock:
            return self._prices.copy()
    
    def force_update_price(self, stock_id: int, new_price: float):
        """Manually set price (admin override)"""
        stock = db.fetch_one('stocks', {'id': stock_id})
        if stock:
            min_price = float(stock['min_price'])
            max_price = float(stock['max_price'])
            new_price = max(min_price, min(max_price, new_price))
            with self._lock:
                self._prices[stock_id] = new_price
            self._update_price_db(stock_id, new_price)
            logger.info(f"Admin forced price update for stock {stock_id} to {new_price}")

# Singleton instance
price_simulator = PriceSimulator()