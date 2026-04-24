from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO
import logging
import threading
from config import Config
from db import db
from auth import register_auth_routes
from trade_routes import register_trade_routes
from payment_routes import register_payment_routes
from admin_routes import register_admin_routes
from stock_routes import register_stock_routes
from trading_engine import trading_engine
from price_simulator import price_simulator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['CORS_HEADERS'] = 'Content-Type'

# Enable CORS
CORS(app, origins=Config.CORS_ORIGINS, supports_credentials=True)

# Initialize SocketIO for real-time updates (optional, for future websocket)
socketio = SocketIO(app, cors_allowed_origins=Config.CORS_ORIGINS, async_mode='threading')

# Register all blueprints/routes
register_auth_routes(app)
register_trade_routes(app)
register_payment_routes(app)
register_admin_routes(app)
register_stock_routes(app)

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'TradingFast API is running'}), 200

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'success': False, 'message': 'Internal server error'}), 500

# Start background services
def start_services():
    """Start trading engine and price simulator in background"""
    logger.info("Starting background services...")
    price_simulator.start()
    trading_engine.start()
    logger.info("Background services started")

# Initialize on first request (or use before_first_request decorator)
@app.before_request
def initialize():
    if not hasattr(app, '_services_started'):
        start_services()
        app._services_started = True

# Main entry point
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=Config.DEBUG)