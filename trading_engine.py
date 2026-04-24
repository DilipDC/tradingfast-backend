import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
from db import db
from config import Config
from price_simulator import price_simulator
from ai_engine import ai_engine

logger = logging.getLogger(__name__)

class TradingEngine:
    """Core trading engine that manages trade windows and resolves trades"""
    
    _instance = None
    _trade_window_open = False
    _next_window_time = None
    _active_trades = {}  # trade_id -> trade_info
    _lock = threading.Lock()
    _thread = None
    _running = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def start(cls):
        """Start the trading engine background thread"""
        if cls._running:
            return
        cls._running = True
        cls._thread = threading.Thread(target=cls._run_loop, daemon=True)
        cls._thread.start()
        logger.info("Trading engine started")
    
    @classmethod
    def stop(cls):
        cls._running = False
        if cls._thread:
            cls._thread.join(timeout=2)
        logger.info("Trading engine stopped")
    
    @classmethod
    def _run_loop(cls):
        """Main loop: controls trade windows and resolves trades"""
        while cls._running:
            try:
                # Check and update trade window
                cls._update_trade_window()
                
                # Check for expired trades
                cls._check_and_resolve_trades()
                
                # Update AI decisions
                ai_engine.update_market_sentiment()
                
                time.sleep(0.5)  # Check every 0.5 seconds
            except Exception as e:
                logger.error(f"Error in trading engine loop: {str(e)}")
                time.sleep(1)
    
    @classmethod
    def _update_trade_window(cls):
        """Opens trading window for 3 seconds every 60 seconds"""
        now = time.time()
        
        if cls._next_window_time is None:
            # Initialize: next window at next multiple of interval
            interval = Config.TRADE_WINDOW_INTERVAL_SECONDS
            cls._next_window_time = ((now // interval) + 1) * interval
        
        # Check if we should open the window
        if not cls._trade_window_open and now >= cls._next_window_time:
            with cls._lock:
                cls._trade_window_open = True
                # Close after duration
                close_time = cls._next_window_time + Config.TRADE_WINDOW_DURATION_SECONDS
                threading.Timer(close_time - now, cls._close_window).start()
                logger.info(f"Trade window OPEN until {datetime.fromtimestamp(close_time)}")
        
        # Update next window time after current window closes
        if cls._trade_window_open and now >= cls._next_window_time + Config.TRADE_WINDOW_DURATION_SECONDS:
            with cls._lock:
                cls._trade_window_open = False
                cls._next_window_time += Config.TRADE_WINDOW_INTERVAL_SECONDS
                logger.info("Trade window CLOSED")
    
    @classmethod
    def _close_window(cls):
        """Force close the trade window"""
        with cls._lock:
            cls._trade_window_open = False
    
    @classmethod
    def is_trade_window_open(cls) -> bool:
        """Check if users can place trades"""
        # Also check admin trading_enabled setting
        setting = db.fetch_one('admin_settings', {'key': 'trading_enabled'})
        if setting and setting.get('value') != 'true':
            return False
        return cls._trade_window_open
    
    @classmethod
    def register_trade(cls, trade_id: int, user_id: str, stock_id: int, 
                       direction: str, amount: float, entry_price: float,
                       expires_at: datetime):
        """Register a new active trade"""
        with cls._lock:
            cls._active_trades[trade_id] = {
                'trade_id': trade_id,
                'user_id': user_id,
                'stock_id': stock_id,
                'direction': direction,
                'amount': amount,
                'entry_price': entry_price,
                'expires_at': expires_at
            }
        logger.info(f"Trade {trade_id} registered, expires at {expires_at}")
    
    @classmethod
    def _check_and_resolve_trades(cls):
        """Check for expired trades and resolve them"""
        now = datetime.utcnow()
        expired_trades = []
        
        with cls._lock:
            for trade_id, trade in list(cls._active_trades.items()):
                if trade['expires_at'] <= now:
                    expired_trades.append(trade)
                    del cls._active_trades[trade_id]
        
        for trade in expired_trades:
            cls._resolve_trade(trade)
    
    @classmethod
    def _resolve_trade(cls, trade: dict):
        """Resolve a single trade: calculate profit/loss and update balance"""
        try:
            # Get current stock price from price_simulator
            stock = db.fetch_one('stocks', {'id': trade['stock_id']})
            if not stock:
                logger.error(f"Stock {trade['stock_id']} not found for trade {trade['trade_id']}")
                return
            
            current_price = price_simulator.get_price(trade['stock_id'])
            if current_price is None:
                current_price = float(stock['price'])
            
            entry = trade['entry_price']
            direction = trade['direction']
            amount = trade['amount']
            
            # Determine win/loss
            if direction == 'UP':
                win = current_price > entry
            else:
                win = current_price < entry
            
            # Get profit percentage from admin settings
            profit_setting = db.fetch_one('admin_settings', {'key': 'profit_percentage'})
            profit_percent = int(profit_setting.get('value', 80)) if profit_setting else 80
            
            if win:
                profit = amount * (profit_percent / 100)
                result = 'win'
                balance_change = profit
                message = f"WIN: +₹{profit:.2f}"
            else:
                profit = -amount
                result = 'loss'
                balance_change = -amount
                message = f"LOSS: -₹{amount:.2f}"
            
            # Update user balance
            profile = db.fetch_one('user_profiles', {'user_id': trade['user_id']})
            if profile:
                new_balance = float(profile['balance']) + balance_change
                db.update('user_profiles', {'balance': new_balance}, {'user_id': trade['user_id']})
                
                # Update user stats
                new_total = (profile.get('total_trades', 0) or 0) + 1
                new_wins = (profile.get('wins', 0) or 0) + (1 if win else 0)
                new_losses = (profile.get('losses', 0) or 0) + (0 if win else 1)
                db.update('user_profiles', {
                    'total_trades': new_total,
                    'wins': new_wins,
                    'losses': new_losses
                }, {'user_id': trade['user_id']})
            
            # Update trade record
            db.update('trades', {
                'exit_price': current_price,
                'profit': profit,
                'result': result,
                'status': 'completed',
                'resolved_at': datetime.utcnow().isoformat()
            }, {'id': trade['trade_id']})
            
            logger.info(f"Trade {trade['trade_id']} resolved: {message} | Entry: {entry}, Exit: {current_price}")
            
        except Exception as e:
            logger.error(f"Error resolving trade {trade['trade_id']}: {str(e)}")
    
    @classmethod
    def get_up_down_distribution(cls) -> Dict[str, int]:
        """Get current distribution of UP vs DOWN trades for AI engine"""
        with cls._lock:
            up_count = sum(1 for t in cls._active_trades.values() if t['direction'] == 'UP')
            down_count = len(cls._active_trades) - up_count
        return {'UP': up_count, 'DOWN': down_count}
    
    @classmethod
    def get_active_trades_by_stock(cls) -> Dict[int, Dict[str, int]]:
        """Get active trades grouped by stock for AI decisions"""
        result = defaultdict(lambda: {'UP': 0, 'DOWN': 0, 'total_amount_up': 0, 'total_amount_down': 0})
        with cls._lock:
            for trade in cls._active_trades.values():
                stock_id = trade['stock_id']
                direction = trade['direction']
                amount = trade['amount']
                if direction == 'UP':
                    result[stock_id]['UP'] += 1
                    result[stock_id]['total_amount_up'] += amount
                else:
                    result[stock_id]['DOWN'] += 1
                    result[stock_id]['total_amount_down'] += amount
        return dict(result)
    
    @classmethod
    def get_active_trades_count(cls) -> int:
        with cls._lock:
            return len(cls._active_trades)

# Initialize singleton
trading_engine = TradingEngine()