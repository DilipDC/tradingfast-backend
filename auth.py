import bcrypt
import jwt
from datetime import datetime, timedelta
from flask import request, jsonify, g
from functools import wraps
from config import Config
from db import db
from models import UserRegister, UserLogin, UserResponse, AuthResponse

# JWT helper functions
def create_access_token(user_id: str, username: str, role: str) -> str:
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'exp': datetime.utcnow() + Config.JWT_ACCESS_TOKEN_EXPIRES,
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm='HS256')

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Authentication middleware
def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'Missing authorization header'}), 401
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'success': False, 'message': 'Invalid authorization format'}), 401
        
        token = parts[1]
        payload = decode_token(token)
        if not payload:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        
        # Attach user info to request context
        g.user_id = payload['user_id']
        g.username = payload['username']
        g.role = payload['role']
        
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @auth_required
    def decorated(*args, **kwargs):
        if g.role != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# Auth routes (to be registered in app.py)
def register_auth_routes(app):
    
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        # Validate input
        try:
            reg_data = UserRegister(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Check if user exists
        existing = db.fetch_one('users', {'email': reg_data.email})
        if existing:
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
        existing_username = db.fetch_one('users', {'username': reg_data.username})
        if existing_username:
            return jsonify({'success': False, 'message': 'Username already taken'}), 400
        
        # Create user
        password_hash = hash_password(reg_data.password)
        user_data = {
            'username': reg_data.username,
            'email': reg_data.email,
            'password_hash': password_hash,
            'role': 'user'
        }
        
        user = db.insert('users', user_data)
        if not user:
            return jsonify({'success': False, 'message': 'Failed to create user'}), 500
        
        # Create user profile with default balance
        profile_data = {
            'user_id': user['id'],
            'balance': Config.DEFAULT_BALANCE,
            'avatar': 'av1.png'
        }
        db.insert('user_profiles', profile_data)
        
        # Generate token
        token = create_access_token(user['id'], user['username'], user['role'])
        
        response_user = UserResponse(
            id=user['id'],
            username=user['username'],
            email=user['email'],
            role=user['role'],
            created_at=datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) if user.get('created_at') else datetime.utcnow()
        )
        
        return jsonify({
            'success': True,
            'message': 'Registration successful',
            'data': {
                'access_token': token,
                'user': response_user.dict()
            }
        }), 201
    
    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request'}), 400
        
        try:
            login_data = UserLogin(**data)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400
        
        # Find user by email
        user = db.fetch_one('users', {'email': login_data.email})
        if not user:
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
        
        # Verify password
        if not verify_password(login_data.password, user['password_hash']):
            return jsonify({'success': False, 'message': 'Invalid email or password'}), 401
        
        # Generate token
        token = create_access_token(user['id'], user['username'], user['role'])
        
        response_user = UserResponse(
            id=user['id'],
            username=user['username'],
            email=user['email'],
            role=user['role'],
            created_at=datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) if user.get('created_at') else datetime.utcnow()
        )
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'data': {
                'access_token': token,
                'user': response_user.dict()
            }
        }), 200
    
    @app.route('/api/auth/me', methods=['GET'])
    @auth_required
    def get_current_user():
        user = db.fetch_one('users', {'id': g.user_id})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        profile = db.fetch_one('user_profiles', {'user_id': g.user_id})
        
        response_user = UserResponse(
            id=user['id'],
            username=user['username'],
            email=user['email'],
            role=user['role'],
            created_at=datetime.fromisoformat(user['created_at'].replace('Z', '+00:00')) if user.get('created_at') else datetime.utcnow()
        )
        
        return jsonify({
            'success': True,
            'data': {
                'user': response_user.dict(),
                'profile': profile
            }
        }), 200