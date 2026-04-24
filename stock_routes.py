from flask import request, jsonify, g
from db import db
from auth import auth_required, admin_required
from middlewares import error_handler
from price_simulator import price_simulator
import logging

logger = logging.getLogger(__name__)

def register_stock_routes(app):
    
    @app.route('/api/stocks', methods=['GET'])
    @error_handler
    def get_stocks():
        """Get all active stocks with real-time prices"""
        stocks = db.fetch_all('stocks', {'is_active': True})
        
        result = []
        for stock in stocks:
            # Get current price from simulator (real-time)
            current_price = price_simulator.get_price(stock['id'])
            if current_price is None:
                current_price = float(stock['price'])
            
            result.append({
                'id': stock['id'],
                'name': stock['name'],
                'symbol': stock['symbol'],
                'price': round(current_price, 4),
                'min_price': float(stock['min_price']),
                'max_price': float(stock['max_price']),
                'is_active': stock['is_active'],
                'updated_at': stock['updated_at']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/stocks/<int:stock_id>', methods=['GET'])
    @error_handler
    def get_stock(stock_id):
        """Get single stock details"""
        stock = db.fetch_one('stocks', {'id': stock_id})
        if not stock:
            return jsonify({'success': False, 'message': 'Stock not found'}), 404
        
        current_price = price_simulator.get_price(stock['id'])
        if current_price is None:
            current_price = float(stock['price'])
        
        return jsonify({
            'success': True,
            'data': {
                'id': stock['id'],
                'name': stock['name'],
                'symbol': stock['symbol'],
                'price': round(current_price, 4),
                'min_price': float(stock['min_price']),
                'max_price': float(stock['max_price'])
            }
        }), 200
    
    # Admin routes for stock management
    @app.route('/api/admin/stocks', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_all_stocks():
        """Admin: Get all stocks (including inactive)"""
        stocks = db.fetch_all('stocks')
        
        result = []
        for stock in stocks:
            current_price = price_simulator.get_price(stock['id'])
            if current_price is None:
                current_price = float(stock['price'])
            
            result.append({
                'id': stock['id'],
                'name': stock['name'],
                'symbol': stock['symbol'],
                'price': round(current_price, 4),
                'min_price': float(stock['min_price']),
                'max_price': float(stock['max_price']),
                'is_active': stock['is_active']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/admin/stocks/<int:stock_id>', methods=['PUT'])
    @admin_required
    @error_handler
    def admin_update_stock(stock_id):
        """Admin: Update stock (name, symbol, min/max price, active status)"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        stock = db.fetch_one('stocks', {'id': stock_id})
        if not stock:
            return jsonify({'success': False, 'message': 'Stock not found'}), 404
        
        update_fields = {}
        
        if 'name' in data:
            update_fields['name'] = data['name']
        if 'symbol' in data:
            update_fields['symbol'] = data['symbol']
        if 'min_price' in data:
            update_fields['min_price'] = data['min_price']
        if 'max_price' in data:
            update_fields['max_price'] = data['max_price']
        if 'is_active' in data:
            update_fields['is_active'] = data['is_active']
        
        if update_fields:
            update_fields['updated_at'] = 'now()'
            db.update('stocks', update_fields, {'id': stock_id})
            
            # If min/max changed, ensure current price is within new bounds
            if 'min_price' in update_fields or 'max_price' in update_fields:
                current_price = price_simulator.get_price(stock_id)
                if current_price:
                    new_min = update_fields.get('min_price', float(stock['min_price']))
                    new_max = update_fields.get('max_price', float(stock['max_price']))
                    if current_price < new_min or current_price > new_max:
                        clamped = max(new_min, min(new_max, current_price))
                        price_simulator.force_update_price(stock_id, clamped)
        
        return jsonify({
            'success': True,
            'message': 'Stock updated successfully'
        }), 200
    
    @app.route('/api/admin/stocks/<int:stock_id>/price', methods=['POST'])
    @admin_required
    @error_handler
    def admin_force_price(stock_id):
        """Admin: Manually set stock price"""
        data = request.get_json()
        if not data or 'price' not in data:
            return jsonify({'success': False, 'message': 'Price is required'}), 400
        
        new_price = float(data['price'])
        stock = db.fetch_one('stocks', {'id': stock_id})
        if not stock:
            return jsonify({'success': False, 'message': 'Stock not found'}), 404
        
        min_price = float(stock['min_price'])
        max_price = float(stock['max_price'])
        
        if new_price < min_price or new_price > max_price:
            return jsonify({
                'success': False, 
                'message': f'Price must be between {min_price} and {max_price}'
            }), 400
        
        price_simulator.force_update_price(stock_id, new_price)
        
        return jsonify({
            'success': True,
            'message': f'Stock price updated to {new_price}'
        }), 200