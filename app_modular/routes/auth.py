"""
Authentication routes (login, register, password reset).
"""
from flask import Blueprint, request, jsonify
import logging
import secrets
from datetime import datetime, timedelta

from ..config.database import db
from ..models.user import User
from ..services.email_service import email_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/', methods=['GET'])
def index():
    """Health check endpoint."""
    return "Saurara Backend API is running"


@auth_bp.route('/users', methods=['GET'])
def get_users():
    """Get all users (basic list)."""
    users = User.query.all()
    return jsonify([{
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "organization_id": user.organization_id,
        "title": user.title.name if user.title else None,
        "title_id": user.title_id
    } for user in users]), 200


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login API endpoint.
    Expects JSON { "username": "<username>", "password": "<password>" }
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    user = User.query.filter_by(username=username).first()
    
    if not user or user.password != password:
        # TODO: Implement proper password hashing verification
        return jsonify({"error": "Invalid username or password"}), 401
    
    return jsonify({
        "message": "Login successful",
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "organization_id": user.organization_id,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "survey_code": user.survey_code,
        "title": user.title.name if user.title else None,
        "title_id": user.title_id
    }), 200


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register a new user.
    Expects JSON { "username": "<username>", "password": "<password>", "email": "<email>" }
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    
    # Check if username already exists
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400
    
    try:
        new_user = User(
            username=username,
            password=password,  # TODO: Hash password
            email=email,
            role='user'
        )
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            "message": "User registered successfully",
            "user_id": new_user.id
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error registering user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@auth_bp.route('/validate-survey', methods=['POST'])
def validate_survey():
    """
    Validate a survey code.
    Expects JSON { "survey_code": "<code>" }.
    Returns 200 + user info if valid.
    """
    data = request.json
    survey_code = data.get('survey_code')
    
    if not survey_code:
        return jsonify({"error": "Survey code is required"}), 400
    
    user = User.query.filter_by(survey_code=survey_code).first()
    
    if not user:
        return jsonify({"error": "Invalid survey code"}), 404
    
    return jsonify({
        "valid": True,
        "user_id": user.id,
        "username": user.username,
        "organization_id": user.organization_id,
        "title": user.title.name if user.title else None,
        "title_id": user.title_id
    }), 200


@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    """
    Request password reset - sends email with reset token.
    Expects JSON { "email": "<email>" }
    """
    data = request.json
    email = data.get('email')
    
    if not email:
        return jsonify({"error": "Email is required"}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user:
        # Don't reveal if email exists for security
        return jsonify({
            "message": "If an account exists with this email, a password reset link will be sent."
        }), 200
    
    try:
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        user.reset_token = reset_token
        user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        
        # Send reset email
        result = email_service.send_password_reset_email(
            to_email=user.email,
            username=user.username,
            reset_token=reset_token,
            firstname=user.firstname
        )
        
        if result.get('success'):
            return jsonify({
                "message": "If an account exists with this email, a password reset link will be sent."
            }), 200
        else:
            logger.error(f"Failed to send password reset email: {result.get('error')}")
            return jsonify({"error": "Failed to send reset email"}), 500
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in forgot password: {str(e)}")
        return jsonify({"error": str(e)}), 500


@auth_bp.route('/verify-reset-token', methods=['POST'])
def verify_reset_token():
    """
    Verify if reset token is valid and not expired.
    Expects JSON { "token": "<token>" }
    """
    data = request.json
    token = data.get('token')
    
    if not token:
        return jsonify({"error": "Token is required"}), 400
    
    user = User.query.filter_by(reset_token=token).first()
    
    if not user:
        return jsonify({"error": "Invalid reset token"}), 400
    
    if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
        return jsonify({"error": "Reset token has expired"}), 400
    
    return jsonify({
        "valid": True,
        "username": user.username,
        "email": user.email
    }), 200


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    Reset password using valid token.
    Expects JSON { "token": "<token>", "new_password": "<password>" }
    """
    data = request.json
    token = data.get('token')
    new_password = data.get('new_password')
    
    if not token or not new_password:
        return jsonify({"error": "Token and new password are required"}), 400
    
    user = User.query.filter_by(reset_token=token).first()
    
    if not user:
        return jsonify({"error": "Invalid reset token"}), 400
    
    if user.reset_token_expires and user.reset_token_expires < datetime.utcnow():
        return jsonify({"error": "Reset token has expired"}), 400
    
    try:
        # Update password and clear reset token
        user.password = new_password  # TODO: Hash password
        user.reset_token = None
        user.reset_token_expires = None
        db.session.commit()
        
        return jsonify({"message": "Password reset successful"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resetting password: {str(e)}")
        return jsonify({"error": str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
def change_password():
    """
    Change password for logged-in user.
    Expects JSON { "user_id": <id>, "current_password": "<pwd>", "new_password": "<pwd>" }
    """
    data = request.json
    user_id = data.get('user_id')
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not all([user_id, current_password, new_password]):
        return jsonify({"error": "All fields are required"}), 400
    
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if user.password != current_password:
        return jsonify({"error": "Current password is incorrect"}), 401
    
    try:
        user.password = new_password  # TODO: Hash password
        db.session.commit()
        
        return jsonify({"message": "Password changed successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error changing password: {str(e)}")
        return jsonify({"error": str(e)}), 500
