from flask import request, jsonify, g
from datetime import datetime, timedelta
from models import PlaceTradeRequest, TradeResponse
from db import db
from auth import auth_required
from middlewares import error_handler, check_trading_window
from trading_engine import TradingEngine
import logging

logger = logging.getLogger(__name__)

def register_trade_routes(app):
    
    @app.route('/api/trade/place', methods=['POST'])
    @auth_required
    @error_handler
    @check_trading_window
    def place_trade():
        """Place a new trade during open window"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        try:
            trade_req = PlaceTradeRequest(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Get user profile
        profile = db.fetch_one('user_profiles', {'user_id': g.user_id})
        if not profile:
            return jsonify({'success': False, 'message': 'User profile not found'}), 404
        
        # Check balance
        if profile['balance'] < trade_req.amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        # Get stock
        stock = db.fetch_one('stocks', {'id': trade_req.stock_id, 'is_active': True})
        if not stock:
            return jsonify({'success': False, 'message': 'Stock not found or inactive'}), 404
        
        # Check if trading is enabled globally
        trading_enabled = db.fetch_one('admin_settings', {'key': 'trading_enabled'})
        if trading_enabled and trading_enabled.get('value') != 'true':
            return jsonify({'success': False, 'message': 'Trading is currently disabled by admin'}), 403
        
        # Calculate expiry time
        expires_at = datetime.utcnow() + timedelta(minutes=trade_req.duration_minutes)
        
        # Create trade record
        trade_data = {
            'user_id': g.user_id,
            'stock_id': trade_req.stock_id,
            'direction': trade_req.direction.value,
            'amount': trade_req.amount,
            'duration_minutes': trade_req.duration_minutes,
            'entry_price': stock['price'],
            'result': 'pending',
            'status': 'pending',
            'expires_at': expires_at.isoformat()
        }
        
        trade = db.insert('trades', trade_data)
        if not trade:
            return jsonify({'success': False, 'message': 'Failed to place trade'}), 500
        
        # Deduct balance immediately
        new_balance = profile['balance'] - trade_req.amount
        db.update('user_profiles', {'balance': new_balance}, {'user_id': g.user_id})
        
        # Register active trade in trading engine
        TradingEngine.register_trade(trade['id'], g.user_id, trade_req.stock_id, 
                                      trade_req.direction.value, trade_req.amount, 
                                      stock['price'], expires_at)
        
        return jsonify({
            'success': True,
            'message': 'Trade placed successfully',
            'data': {
                'trade_id': trade['id'],
                'entry_price': stock['price']
            }
        }), 201
    
    @app.route('/api/trade/active', methods=['GET'])
    @auth_required
    @error_handler
    def get_active_trades():
        """Get current user's active (pending) trades"""
        trades = db.fetch_all('trades', {
            'user_id': g.user_id,
            'status': 'pending'
        })
        
        result = []
        for trade in trades:
            stock = db.fetch_one('stocks', {'id': trade['stock_id']})
            result.append({
                'id': trade['id'],
                'stock_name': stock['name'] if stock else 'Unknown',
                'stock_symbol': stock['symbol'] if stock else '?',
                'direction': trade['direction'],
                'amount': float(trade['amount']),
                'entry_price': float(trade['entry_price']),
                'expires_at': trade['expires_at']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/trade/history', methods=['GET'])
    @auth_required
    @error_handler
    def get_trade_history():
        """Get user's trade history (completed trades)"""
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        trades = db._client.table('trades')\
            .select('*, stocks(name, symbol)')\
            .eq('user_id', g.user_id)\
            .neq('status', 'pending')\
            .order('placed_at', desc=True)\
            .limit(limit)\
            .offset(offset)\
            .execute()
        
        result = []
        for trade in trades.data:
            result.append({
                'id': trade['id'],
                'stock_name': trade['stocks']['name'],
                'stock_symbol': trade['stocks']['symbol'],
                'direction': trade['direction'],
                'amount': float(trade['amount']),
                'duration_minutes': trade['duration_minutes'],
                'entry_price': float(trade['entry_price']),
                'exit_price': float(trade['exit_price']) if trade['exit_price'] else None,
                'profit': float(trade['profit']) if trade['profit'] else None,
                'result': trade['result'],
                'placed_at': trade['placed_at']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/trade/stats', methods=['GET'])
    @auth_required
    @error_handler
    def get_trade_stats():
        """Get user's trading statistics"""
        profile = db.fetch_one('user_profiles', {'user_id': g.user_id})
        
        if not profile:
            return jsonify({'success': False, 'message': 'Profile not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'total_trades': profile.get('total_trades', 0),
                'wins': profile.get('wins', 0),
                'losses': profile.get('losses', 0),
                'win_rate': round((profile.get('wins', 0) / max(profile.get('total_trades', 1), 1)) * 100, 1)
            }
        }), 200