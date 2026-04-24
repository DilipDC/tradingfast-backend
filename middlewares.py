from flask import request, jsonify
from functools import wraps
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def error_handler(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unhandled error in {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Internal server error'
            }), 500
    return decorated

def validate_json(required_fields=None):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Content-Type must be application/json'
                }), 400
            
            data = request.get_json()
            if required_fields:
                for field in required_fields:
                    if field not in data:
                        return jsonify({
                            'success': False,
                            'message': f'Missing required field: {field}'
                        }), 400
            
            return f(*args, **kwargs)
        return decorated
    return decorator

def log_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        logger.info(f"{request.method} {request.path} - {request.remote_addr}")
        return f(*args, **kwargs)
    return decorated

def rate_limit(limit_per_minute=30):
    """Simple in-memory rate limiter (not for production scale, but works for demo)"""
    from collections import defaultdict
    from time import time
    
    requests = defaultdict(list)
    
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            client_ip = request.remote_addr
            now = time()
            window_start = now - 60
            
            # Clean old requests
            requests[client_ip] = [t for t in requests[client_ip] if t > window_start]
            
            if len(requests[client_ip]) >= limit_per_minute:
                return jsonify({
                    'success': False,
                    'message': f'Rate limit exceeded. Max {limit_per_minute} requests per minute.'
                }), 429
            
            requests[client_ip].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator

def check_trading_window(f):
    """Check if trading is currently allowed (during 3-second window every 60 seconds)"""
    from trading_engine import TradingEngine
    
    @wraps(f)
    def decorated(*args, **kwargs):
        if not TradingEngine.is_trade_window_open():
            return jsonify({
                'success': False,
                'message': 'Trading window is closed. Window opens for 3 seconds every 60 seconds.'
            }), 403
        return f(*args, **kwargs)
    return decorated