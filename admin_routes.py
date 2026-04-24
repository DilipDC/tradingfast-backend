from flask import request, jsonify, g
from datetime import datetime, timedelta
from db import db
from auth import admin_required
from middlewares import error_handler
from models import AdminSettingsUpdate, DashboardStats
from trading_engine import trading_engine
from price_simulator import price_simulator
from ai_engine import ai_engine
import logging

logger = logging.getLogger(__name__)

def register_admin_routes(app):
    
    @app.route('/api/admin/login', methods=['POST'])
    @error_handler
    def admin_login():
        """Admin login (separate from user auth)"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        username = data.get('username')
        password = data.get('password')
        
        from config import Config
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            # Generate admin JWT token (using same auth system)
            from auth import create_access_token
            token = create_access_token('admin_id', username, 'admin')
            return jsonify({
                'success': True,
                'message': 'Admin login successful',
                'data': {'access_token': token}
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Invalid admin credentials'}), 401
    
    @app.route('/api/admin/dashboard/stats', methods=['GET'])
    @admin_required
    @error_handler
    def admin_dashboard_stats():
        """Get comprehensive dashboard statistics"""
        # Total users
        users = db.fetch_all('users', {'role': 'user'})
        total_users = len(users)
        
        # Total balance across all users
        profiles = db.fetch_all('user_profiles')
        total_balance = sum(float(p['balance']) for p in profiles)
        
        # Total trades (completed)
        trades = db.fetch_all('trades')
        total_trades = len(trades)
        
        # Pending deposits
        pending_deposits = db.fetch_all('deposit_requests', {'status': 'pending'})
        pending_deposits_count = len(pending_deposits)
        pending_deposits_amount = sum(float(d['amount']) for d in pending_deposits)
        
        # Pending withdrawals
        pending_withdrawals = db.fetch_all('withdraw_requests', {'status': 'pending'})
        pending_withdrawals_count = len(pending_withdrawals)
        pending_withdrawals_amount = sum(float(w['amount']) for w in pending_withdrawals)
        
        # Active trades count
        active_trades_count = trading_engine.get_active_trades_count()
        
        # UP/DOWN distribution
        up_down_dist = trading_engine.get_up_down_distribution()
        
        # Recent trades (last 10)
        recent_trades = db._client.table('trades')\
            .select('*, users(username), stocks(name, symbol)')\
            .order('placed_at', desc=True)\
            .limit(10)\
            .execute()
        
        recent_trades_list = []
        for t in recent_trades.data:
            recent_trades_list.append({
                'id': t['id'],
                'username': t['users']['username'] if t.get('users') else 'Unknown',
                'stock_name': t['stocks']['name'] if t.get('stocks') else 'Unknown',
                'amount': float(t['amount']),
                'direction': t['direction'],
                'result': t['result'],
                'profit': float(t['profit']) if t['profit'] else 0,
                'placed_at': t['placed_at']
            })
        
        # AI market insights
        ai_insights = ai_engine.get_market_insights()
        
        return jsonify({
            'success': True,
            'data': {
                'total_users': total_users,
                'total_balance': round(total_balance, 2),
                'total_trades': total_trades,
                'pending_deposits': {
                    'count': pending_deposits_count,
                    'total_amount': round(pending_deposits_amount, 2)
                },
                'pending_withdrawals': {
                    'count': pending_withdrawals_count,
                    'total_amount': round(pending_withdrawals_amount, 2)
                },
                'active_trades': active_trades_count,
                'up_down_distribution': up_down_dist,
                'recent_trades': recent_trades_list,
                'ai_insights': ai_insights
            }
        }), 200
    
    @app.route('/api/admin/users', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_users():
        """Get all users with their profiles"""
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search', '')
        
        query = db._client.table('users')\
            .select('*, user_profiles(*)')\
            .eq('role', 'user')
        
        if search:
            query = query.or_(f'username.ilike.%{search}%,email.ilike.%{search}%')
        
        users = query.range(offset, offset + limit - 1).execute()
        
        result = []
        for user in users.data:
            profile = user.get('user_profiles', {})
            result.append({
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'balance': float(profile.get('balance', 0)) if profile else 0,
                'avatar': profile.get('avatar', 'av1.png'),
                'location': profile.get('location', ''),
                'total_trades': profile.get('total_trades', 0),
                'wins': profile.get('wins', 0),
                'losses': profile.get('losses', 0),
                'created_at': user['created_at']
            })
        
        # Get total count
        count_query = db._client.table('users').select('*', count='exact').eq('role', 'user')
        if search:
            count_query = count_query.or_(f'username.ilike.%{search}%,email.ilike.%{search}%')
        count_result = count_query.execute()
        total = count_result.count
        
        return jsonify({
            'success': True,
            'data': {
                'users': result,
                'total': total,
                'limit': limit,
                'offset': offset
            }
        }), 200
    
    @app.route('/api/admin/users/<user_id>', methods=['PUT'])
    @admin_required
    @error_handler
    def admin_update_user(user_id):
        """Admin: Update user balance, profile, etc."""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        # Update balance if provided
        if 'balance' in data:
            new_balance = float(data['balance'])
            db.update('user_profiles', {'balance': new_balance}, {'user_id': user_id})
        
        # Update profile fields
        profile_updates = {}
        for field in ['avatar', 'location', 'bio', 'phone']:
            if field in data:
                profile_updates[field] = data[field]
        
        if profile_updates:
            db.update('user_profiles', profile_updates, {'user_id': user_id})
        
        # Update username/email if provided (in users table)
        user_updates = {}
        if 'username' in data:
            user_updates['username'] = data['username']
        if 'email' in data:
            user_updates['email'] = data['email']
        
        if user_updates:
            db.update('users', user_updates, {'id': user_id})
        
        return jsonify({
            'success': True,
            'message': 'User updated successfully'
        }), 200
    
    @app.route('/api/admin/users/<user_id>', methods=['DELETE'])
    @admin_required
    @error_handler
    def admin_delete_user(user_id):
        """Admin: Delete a user (cascade deletes profile, trades, etc.)"""
        # Check if user exists
        user = db.fetch_one('users', {'id': user_id})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Delete user (cascade should handle related tables if foreign keys set)
        db.delete('users', {'id': user_id})
        
        logger.info(f"Admin deleted user {user_id}")
        
        return jsonify({
            'success': True,
            'message': 'User deleted successfully'
        }), 200
    
    @app.route('/api/admin/settings', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_settings():
        """Get all admin settings"""
        settings = db.fetch_all('admin_settings')
        settings_dict = {s['key']: s['value'] for s in settings}
        
        return jsonify({
            'success': True,
            'data': settings_dict
        }), 200
    
    @app.route('/api/admin/settings', methods=['PUT'])
    @admin_required
    @error_handler
    def admin_update_settings():
        """Update admin settings"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        try:
            settings_update = AdminSettingsUpdate(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Convert to dict and update each setting
        update_dict = settings_update.dict(exclude_none=True)
        
        for key, value in update_dict.items():
            # Convert boolean to string for storage
            if isinstance(value, bool):
                value = 'true' if value else 'false'
            else:
                value = str(value)
            
            db.update('admin_settings', {'value': value, 'updated_at': datetime.utcnow().isoformat()}, {'key': key})
        
        logger.info(f"Admin settings updated: {update_dict}")
        
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully'
        }), 200
    
    @app.route('/api/admin/trades', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_all_trades():
        """Get all trades (for admin overview)"""
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        trades = db._client.table('trades')\
            .select('*, users(username), stocks(name, symbol)')\
            .order('placed_at', desc=True)\
            .range(offset, offset + limit - 1)\
            .execute()
        
        result = []
        for t in trades.data:
            result.append({
                'id': t['id'],
                'username': t['users']['username'] if t.get('users') else 'Unknown',
                'stock_name': t['stocks']['name'] if t.get('stocks') else 'Unknown',
                'stock_symbol': t['stocks']['symbol'] if t.get('stocks') else '?',
                'direction': t['direction'],
                'amount': float(t['amount']),
                'entry_price': float(t['entry_price']),
                'exit_price': float(t['exit_price']) if t['exit_price'] else None,
                'profit': float(t['profit']) if t['profit'] else None,
                'result': t['result'],
                'status': t['status'],
                'placed_at': t['placed_at'],
                'expires_at': t['expires_at']
            })
        
        # Get total count
        count_result = db._client.table('trades').select('*', count='exact').execute()
        total = count_result.count
        
        return jsonify({
            'success': True,
            'data': {
                'trades': result,
                'total': total
            }
        }), 200
    
    @app.route('/api/admin/force/resolve/<int:trade_id>', methods=['POST'])
    @admin_required
    @error_handler
    def admin_force_resolve_trade(trade_id):
        """Admin: Manually resolve a pending trade"""
        trade = db.fetch_one('trades', {'id': trade_id})
        if not trade:
            return jsonify({'success': False, 'message': 'Trade not found'}), 404
        
        if trade['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Trade already resolved'}), 400
        
        # Force resolve using trading engine's internal method
        from trading_engine import trading_engine as te
        # Manually trigger resolution
        te._resolve_trade({
            'trade_id': trade_id,
            'user_id': trade['user_id'],
            'stock_id': trade['stock_id'],
            'direction': trade['direction'],
            'amount': float(trade['amount']),
            'entry_price': float(trade['entry_price']),
            'expires_at': datetime.fromisoformat(trade['expires_at'].replace('Z', '+00:00'))
        })
        
        return jsonify({
            'success': True,
            'message': 'Trade resolved successfully'
        }), 200
    
    @app.route('/api/admin/toggle/trading', methods=['POST'])
    @admin_required
    @error_handler
    def admin_toggle_trading():
        """Enable/disable trading globally"""
        data = request.get_json()
        enabled = data.get('enabled', False)
        
        db.update('admin_settings', {'value': 'true' if enabled else 'false'}, {'key': 'trading_enabled'})
        
        status = 'enabled' if enabled else 'disabled'
        logger.info(f"Admin {status} trading globally")
        
        return jsonify({
            'success': True,
            'message': f'Trading {status}'
        }), 200