"""Authentication routes: register, login, logout, session check."""
import logging

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import create_auth_token, get_token_identity, login_required
from app.extensions import db_manager

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

# ============= AUTH ROUTES =============
@bp.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()

        # Validation
        if not username or not password:
            return jsonify({'error': 'Username və password tələb olunur'}), 400

        if len(username) < 3:
            return jsonify({'error': 'Username ən azı 3 simvol olmalıdır'}), 400

        if len(password) < 6:
            return jsonify({'error': 'Password ən azı 6 simvol olmalıdır'}), 400

        # Check if user exists
        existing_user = db_manager.get_user_by_username(username)
        if existing_user:
            return jsonify({'error': 'Bu username artıq mövcuddur'}), 400

        # Create user
        password_hash = generate_password_hash(password)
        user_id = db_manager.create_user(username, password_hash, email)

        # Set session
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = 'user'
        session.permanent = True

        # Create JWT token for stateless auth (Vercel)
        access_token = create_auth_token(user_id, username, 'user')

        return jsonify({
            'message': 'Qeydiyyat uğurlu',
            'access_token': access_token,
            'user': {
                'id': user_id,
                'username': username,
                'role': 'user',
                'email': email
            }
        }), 201

    except Exception as e:
        return jsonify({'error': f'Qeydiyyat xətası: {str(e)}'}), 500

@bp.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': 'Username və password tələb olunur'}), 400

        # Get user
        user = db_manager.get_user_by_username(username)
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Yanlış username və ya password'}), 401

        # Set session
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session.permanent = True

        # Create JWT token for stateless auth (Vercel)
        access_token = create_auth_token(user['id'], user['username'], user['role'])

        return jsonify({
            'message': 'Giriş uğurlu',
            'access_token': access_token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'email': user.get('email')
            }
        })

    except Exception as e:
        return jsonify({'error': f'Login xətası: {str(e)}'}), 500

@bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.clear()
    return jsonify({'message': 'Çıxış edildi'})

@bp.route('/api/auth/check', methods=['GET'])
def check_auth():
    """Check authentication status - supports both JWT and session"""
    # Try JWT token first (for serverless/Vercel)
    identity = get_token_identity()
    if identity:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': identity['user_id'],
                'username': identity['username'],
                'role': identity.get('role', 'user')
            }
        })

    # Fall back to session (local development)
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': session['user_id'],
                'username': session['username'],
                'role': session.get('role', 'user')
            }
        })

    return jsonify({'authenticated': False})

@bp.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user info"""
    user_id = session['user_id']
    user = db_manager.get_user_by_id(user_id)

    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'email': user.get('email'),
            'created_at': user.get('created_at')
        }
    })
