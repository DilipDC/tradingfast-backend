import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
from config import Config
from db import db
from auth import register_auth_routes
from trade_routes import register_trade_routes
from payment_routes import register_payment_routes
from admin_routes import register_admin_routes
from stock_routes import register_stock_routes
from trading_engine import trading_engine
from price_simulator import price_simulator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY

CORS(app, origins=Config.CORS_ORIGINS, supports_credentials=True)

socketio = SocketIO(app, cors_allowed_origins=Config.CORS_ORIGINS, async_mode='threading')

register_auth_routes(app)
register_trade_routes(app)
register_payment_routes(app)
register_admin_routes(app)
register_stock_routes(app)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'TradingFast API is running'}), 200

@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Server error: {str(error)}")
    return jsonify({'success': False, 'message': 'Internal server error'}), 500

def start_services():
    logger.info("Starting background services...")
    price_simulator.start()
    trading_engine.start()
    logger.info("Background services started")

@app.before_request
def initialize():
    if not hasattr(app, '_services_started'):
        start_services()
        app._services_started = True

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=Config.DEBUG)
