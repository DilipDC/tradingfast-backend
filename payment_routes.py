from flask import request, jsonify, g
from datetime import datetime, timedelta
from db import db
from auth import auth_required, admin_required
from middlewares import error_handler
from models import DepositRequest, WithdrawRequest
import logging

logger = logging.getLogger(__name__)

def register_payment_routes(app):
    
    # ========== USER ROUTES ==========
    
    @app.route('/api/payment/balance', methods=['GET'])
    @auth_required
    @error_handler
    def get_balance():
        """Get current user balance"""
        profile = db.fetch_one('user_profiles', {'user_id': g.user_id})
        if not profile:
            return jsonify({'success': False, 'message': 'Profile not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {'balance': float(profile['balance'])}
        }), 200
    
    @app.route('/api/payment/deposit/request', methods=['POST'])
    @auth_required
    @error_handler
    def request_deposit():
        """User requests a deposit"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        try:
            deposit_req = DepositRequest(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Check if deposit is enabled by admin
        deposit_enabled = db.fetch_one('admin_settings', {'key': 'deposit_enabled'})
        if deposit_enabled and deposit_enabled.get('value') != 'true':
            return jsonify({'success': False, 'message': 'Deposits are currently disabled by admin'}), 403
        
        # Check time window
        if not _is_within_time_window('deposit'):
            return jsonify({
                'success': False, 
                'message': 'Deposits are only allowed between 9:00 AM and 6:00 PM IST'
            }), 403
        
        # Check daily limit (1 deposit per day)
        today = datetime.utcnow().date().isoformat()
        existing_deposits = db._client.table('transactions')\
            .select('*')\
            .eq('user_id', g.user_id)\
            .eq('type', 'deposit')\
            .gte('requested_at', f"{today}T00:00:00")\
            .execute()
        
        if existing_deposits.data:
            return jsonify({
                'success': False, 
                'message': 'You can only make 1 deposit per day'
            }), 403
        
        # Create deposit request
        deposit_data = {
            'user_id': g.user_id,
            'amount': deposit_req.amount,
            'status': 'pending',
            'requested_at': datetime.utcnow().isoformat()
        }
        
        transaction = db.insert('transactions', deposit_data)
        if not transaction:
            return jsonify({'success': False, 'message': 'Failed to create deposit request'}), 500
        
        # Also create deposit_request record for QR flow
        deposit_request_data = {
            'user_id': g.user_id,
            'amount': deposit_req.amount,
            'status': 'pending',
            'requested_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        }
        db.insert('deposit_requests', deposit_request_data)
        
        logger.info(f"Deposit request #{transaction['id']} created for user {g.user_id}: ₹{deposit_req.amount}")
        
        return jsonify({
            'success': True,
            'message': 'Deposit request sent to admin. Please wait for QR code.',
            'data': {'transaction_id': transaction['id']}
        }), 201
    
    @app.route('/api/payment/withdraw/request', methods=['POST'])
    @auth_required
    @error_handler
    def request_withdraw():
        """User requests a withdrawal"""
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        try:
            withdraw_req = WithdrawRequest(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Check if withdraw is enabled by admin
        withdraw_enabled = db.fetch_one('admin_settings', {'key': 'withdraw_enabled'})
        if withdraw_enabled and withdraw_enabled.get('value') != 'true':
            return jsonify({'success': False, 'message': 'Withdrawals are currently disabled by admin'}), 403
        
        # Check time window
        if not _is_within_time_window('withdraw'):
            return jsonify({
                'success': False, 
                'message': 'Withdrawals are only allowed between 9:00 AM and 6:00 PM IST'
            }), 403
        
        # Check daily limit (1 withdrawal per day)
        today = datetime.utcnow().date().isoformat()
        existing_withdrawals = db._client.table('transactions')\
            .select('*')\
            .eq('user_id', g.user_id)\
            .eq('type', 'withdraw')\
            .gte('requested_at', f"{today}T00:00:00")\
            .execute()
        
        if existing_withdrawals.data:
            return jsonify({
                'success': False, 
                'message': 'You can only make 1 withdrawal per day'
            }), 403
        
        # Check balance
        profile = db.fetch_one('user_profiles', {'user_id': g.user_id})
        if not profile or float(profile['balance']) < withdraw_req.amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        # Create withdrawal transaction (pending)
        withdraw_data = {
            'user_id': g.user_id,
            'type': 'withdraw',
            'amount': withdraw_req.amount,
            'status': 'pending',
            'upi_id': withdraw_req.upi_id,
            'upi_name': withdraw_req.upi_name,
            'requested_at': datetime.utcnow().isoformat()
        }
        
        transaction = db.insert('transactions', withdraw_data)
        if not transaction:
            return jsonify({'success': False, 'message': 'Failed to create withdrawal request'}), 500
        
        # Create withdraw request record
        withdraw_request_data = {
            'user_id': g.user_id,
            'amount': withdraw_req.amount,
            'upi_id': withdraw_req.upi_id,
            'upi_name': withdraw_req.upi_name,
            'status': 'pending',
            'requested_at': datetime.utcnow().isoformat()
        }
        db.insert('withdraw_requests', withdraw_request_data)
        
        logger.info(f"Withdrawal request #{transaction['id']} created for user {g.user_id}: ₹{withdraw_req.amount}")
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal request submitted for admin approval',
            'data': {'transaction_id': transaction['id']}
        }), 201
    
    @app.route('/api/payment/transactions', methods=['GET'])
    @auth_required
    @error_handler
    def get_transactions():
        """Get user's transaction history"""
        limit = request.args.get('limit', 20, type=int)
        
        transactions = db._client.table('transactions')\
            .select('*')\
            .eq('user_id', g.user_id)\
            .order('requested_at', desc=True)\
            .limit(limit)\
            .execute()
        
        result = []
        for tx in transactions.data:
            result.append({
                'id': tx['id'],
                'type': tx['type'],
                'amount': float(tx['amount']),
                'status': tx['status'],
                'upi_id': tx.get('upi_id'),
                'upi_name': tx.get('upi_name'),
                'requested_at': tx['requested_at'],
                'approved_at': tx.get('approved_at')
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    # ========== ADMIN ROUTES ==========
    
    @app.route('/api/admin/payment/deposits/pending', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_pending_deposits():
        """Admin: Get all pending deposit requests"""
        deposits = db._client.table('deposit_requests')\
            .select('*, users(username, email)')\
            .eq('status', 'pending')\
            .order('requested_at', asc=True)\
            .execute()
        
        result = []
        for d in deposits.data:
            result.append({
                'id': d['id'],
                'user_id': d['user_id'],
                'username': d['users']['username'] if d.get('users') else 'Unknown',
                'email': d['users']['email'] if d.get('users') else 'Unknown',
                'amount': float(d['amount']),
                'requested_at': d['requested_at']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/admin/payment/deposits/<int:deposit_id>/approve', methods=['POST'])
    @admin_required
    @error_handler
    def admin_approve_deposit(deposit_id):
        """Admin: Approve deposit after QR confirmation"""
        data = request.get_json() or {}
        
        # Get deposit request
        deposit_req = db.fetch_one('deposit_requests', {'id': deposit_id})
        if not deposit_req:
            return jsonify({'success': False, 'message': 'Deposit request not found'}), 404
        
        if deposit_req['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Deposit already {deposit_req["status"]}'}), 400
        
        user_id = deposit_req['user_id']
        amount = float(deposit_req['amount'])
        
        # Update user balance
        profile = db.fetch_one('user_profiles', {'user_id': user_id})
        if profile:
            new_balance = float(profile['balance']) + amount
            db.update('user_profiles', {'balance': new_balance}, {'user_id': user_id})
        
        # Update deposit request status
        db.update('deposit_requests', {
            'status': 'approved',
            'completed_at': datetime.utcnow().isoformat()
        }, {'id': deposit_id})
        
        # Update transaction record
        transaction = db.fetch_one('transactions', {
            'user_id': user_id,
            'type': 'deposit',
            'amount': amount,
            'status': 'pending'
        })
        if transaction:
            db.update('transactions', {
                'status': 'approved',
                'approved_at': datetime.utcnow().isoformat()
            }, {'id': transaction['id']})
        
        logger.info(f"Admin approved deposit #{deposit_id}: ₹{amount} for user {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'Deposit of ₹{amount} approved. User balance updated.'
        }), 200
    
    @app.route('/api/admin/payment/withdrawals/pending', methods=['GET'])
    @admin_required
    @error_handler
    def admin_get_pending_withdrawals():
        """Admin: Get all pending withdrawal requests"""
        withdrawals = db._client.table('withdraw_requests')\
            .select('*, users(username, email)')\
            .eq('status', 'pending')\
            .order('requested_at', asc=True)\
            .execute()
        
        result = []
        for w in withdrawals.data:
            result.append({
                'id': w['id'],
                'user_id': w['user_id'],
                'username': w['users']['username'] if w.get('users') else 'Unknown',
                'email': w['users']['email'] if w.get('users') else 'Unknown',
                'amount': float(w['amount']),
                'upi_id': w['upi_id'],
                'upi_name': w['upi_name'],
                'requested_at': w['requested_at']
            })
        
        return jsonify({
            'success': True,
            'data': result
        }), 200
    
    @app.route('/api/admin/payment/withdrawals/<int:withdraw_id>/approve', methods=['POST'])
    @admin_required
    @error_handler
    def admin_approve_withdrawal(withdraw_id):
        """Admin: Approve withdrawal and deduct from user balance"""
        withdraw_req = db.fetch_one('withdraw_requests', {'id': withdraw_id})
        if not withdraw_req:
            return jsonify({'success': False, 'message': 'Withdrawal request not found'}), 404
        
        if withdraw_req['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Withdrawal already {withdraw_req["status"]}'}), 400
        
        user_id = withdraw_req['user_id']
        amount = float(withdraw_req['amount'])
        
        # Check and deduct balance
        profile = db.fetch_one('user_profiles', {'user_id': user_id})
        if not profile or float(profile['balance']) < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        new_balance = float(profile['balance']) - amount
        db.update('user_profiles', {'balance': new_balance}, {'user_id': user_id})
        
        # Update withdrawal request status
        db.update('withdraw_requests', {
            'status': 'approved',
            'processed_at': datetime.utcnow().isoformat()
        }, {'id': withdraw_id})
        
        # Update transaction record
        transaction = db.fetch_one('transactions', {
            'user_id': user_id,
            'type': 'withdraw',
            'amount': amount,
            'status': 'pending'
        })
        if transaction:
            db.update('transactions', {
                'status': 'approved',
                'approved_at': datetime.utcnow().isoformat()
            }, {'id': transaction['id']})
        
        logger.info(f"Admin approved withdrawal #{withdraw_id}: ₹{amount} from user {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'Withdrawal of ₹{amount} approved. User balance updated.'
        }), 200
    
    @app.route('/api/admin/payment/withdrawals/<int:withdraw_id>/reject', methods=['POST'])
    @admin_required
    @error_handler
    def admin_reject_withdrawal(withdraw_id):
        """Admin: Reject withdrawal request"""
        withdraw_req = db.fetch_one('withdraw_requests', {'id': withdraw_id})
        if not withdraw_req:
            return jsonify({'success': False, 'message': 'Withdrawal request not found'}), 404
        
        if withdraw_req['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Withdrawal already {withdraw_req["status"]}'}), 400
        
        db.update('withdraw_requests', {
            'status': 'rejected',
            'processed_at': datetime.utcnow().isoformat()
        }, {'id': withdraw_id})
        
        transaction = db.fetch_one('transactions', {
            'user_id': withdraw_req['user_id'],
            'type': 'withdraw',
            'amount': float(withdraw_req['amount']),
            'status': 'pending'
        })
        if transaction:
            db.update('transactions', {'status': 'rejected'}, {'id': transaction['id']})
        
        return jsonify({
            'success': True,
            'message': 'Withdrawal request rejected'
        }), 200
    
    @app.route('/api/admin/payment/qr/<int:deposit_id>', methods=['POST'])
    @admin_required
    @error_handler
    def admin_upload_qr(deposit_id):
        """Admin: Upload QR code image URL for deposit"""
        data = request.get_json()
        if not data or 'qr_url' not in data:
            return jsonify({'success': False, 'message': 'QR URL is required'}), 400
        
        deposit_req = db.fetch_one('deposit_requests', {'id': deposit_id})
        if not deposit_req:
            return jsonify({'success': False, 'message': 'Deposit request not found'}), 404
        
        db.update('deposit_requests', {'qr_code_url': data['qr_url']}, {'id': deposit_id})
        
        return jsonify({
            'success': True,
            'message': 'QR code uploaded successfully'
        }), 200


# Helper functions
def _is_within_time_window(payment_type: str) -> bool:
    """Check if current time is within allowed window for deposit/withdraw"""
    # Get settings
    start_key = f'{payment_type}_start_time'
    end_key = f'{payment_type}_end_time'
    
    start_setting = db.fetch_one('admin_settings', {'key': start_key})
    end_setting = db.fetch_one('admin_settings', {'key': end_key})
    
    start_time = start_setting['value'] if start_setting else '09:00'
    end_time = end_setting['value'] if end_setting else '18:00'
    
    # Parse current time (using UTC but treat as IST for demo simplicity)
    now = datetime.utcnow()
    current_minutes = now.hour * 60 + now.minute
    
    start_hour, start_min = map(int, start_time.split(':'))
    end_hour, end_min = map(int, end_time.split(':'))
    
    start_minutes = start_hour * 60 + start_min
    end_minutes = end_hour * 60 + end_min
    
    return start_minutes <= current_minutes <= end_minutes