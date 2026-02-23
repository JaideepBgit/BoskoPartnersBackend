"""
User management routes.
"""
from flask import Blueprint, request, jsonify
import logging
import secrets
import json

from ..config.database import db
from ..models.user import User, UserDetails, Role, UserOrganizationTitle, Title
from ..models.organization import Organization
from ..models.geo_location import GeoLocation
from ..utils.helpers import validate_user_role, generate_survey_code

logger = logging.getLogger(__name__)

users_bp = Blueprint('users', __name__)


@users_bp.route('/users', methods=['GET'])
def get_all_users():
    """Get all users with their details."""
    try:
        # Get filter parameters
        organization_id = request.args.get('organization_id', type=int)
        role = request.args.get('role')
        
        query = User.query
        
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        if role:
            query = query.filter_by(role=role)
        
        users = query.all()
        
        return jsonify([{
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "organization_id": user.organization_id,
            "organization_name": user.organization.name if user.organization else None,
            "survey_code": user.survey_code,
            "geo_location_id": user.geo_location_id,
            "title": user.title.name if user.title else None,
            "title_id": user.title_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None
        } for user in users]), 200
        
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get a specific user by ID."""
    user = User.query.get_or_404(user_id)
    
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "organization_id": user.organization_id,
        "organization_name": user.organization.name if user.organization else None,
        "survey_code": user.survey_code,
        "geo_location_id": user.geo_location_id,
        "title": user.title.name if user.title else None,
        "title_id": user.title_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None
    }), 200


@users_bp.route('/users', methods=['POST'])
def add_user():
    """Create a new user."""
    data = request.json
    
    username = data.get('username')
    password = data.get('password', secrets.token_urlsafe(8))
    email = data.get('email')
    role = validate_user_role(data.get('role'))
    firstname = data.get('firstname')
    lastname = data.get('lastname')
    organization_id = data.get('organization_id')
    survey_code = data.get('survey_code') or generate_survey_code()
    title_id = data.get('title_id')
    
    if not username:
        return jsonify({"error": "Username is required"}), 400
    
    # Check if username already exists
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400
    
    # Check if email already exists
    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400
    
    try:
        new_user = User(
            username=username,
            password=password,  # TODO: Hash password
            email=email,
            role=role,
            firstname=firstname,
            lastname=lastname,
            organization_id=organization_id,
            survey_code=survey_code,
            title_id=title_id
        )
        
        # Handle multiple roles
        roles_list = data.get('roles', [])
        # If 'role' is provided as a string, add it to list if not present
        if role and role not in roles_list:
            roles_list.append(role)
            
        for r_name in roles_list:
            role_obj = Role.query.filter_by(name=r_name).first()
            if not role_obj:
                role_obj = Role(name=r_name, description=f'Role: {r_name}')
                db.session.add(role_obj)
            new_user.roles.append(role_obj)
            
        # Handle multiple titles
        titles_list = data.get('titles', [])
        # If 'title' string provided (via title_id logic is harder, skip if id)
        
        for t_name in titles_list:
            title_obj = Title.query.filter_by(name=t_name).first()
            if not title_obj:
                title_obj = Title(name=t_name)
                db.session.add(title_obj)
            new_user.titles.append(title_obj)
            
        # If title_id was provided, ensure it's in the list
        if title_id:
             title_main = Title.query.get(title_id)
             if title_main and title_main not in new_user.titles:
                 new_user.titles.append(title_main)
        
        # If no explicit title_id but titles list exists, set first as primary
        if not title_id and new_user.titles:
            new_user.title = new_user.titles[0]
            
        
        # Handle geo location if provided
        geo_data = data.get('geo_location')
        if geo_data:
            geo_location = GeoLocation(
                which='user',
                continent=geo_data.get('continent'),
                region=geo_data.get('region'),
                province=geo_data.get('province'),
                city=geo_data.get('city'),
                town=geo_data.get('town'),
                address_line1=geo_data.get('address_line1'),
                address_line2=geo_data.get('address_line2'),
                country=geo_data.get('country'),
                postal_code=geo_data.get('postal_code')
            )
            db.session.add(geo_location)
            db.session.flush()
            new_user.geo_location_id = geo_location.id
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({
            "message": "User created successfully",
            "user_id": new_user.id,
            "username": new_user.username,
            "password": password,  # Return for welcome email
            "survey_code": new_user.survey_code
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update an existing user."""
    data = request.json
    user = User.query.get_or_404(user_id)
    
    try:
        if 'username' in data:
            # Check if new username conflicts with existing user
            existing = User.query.filter_by(username=data['username']).first()
            if existing and existing.id != user_id:
                return jsonify({"error": "Username already exists"}), 400
            user.username = data['username']
        
        if 'email' in data:
            if data['email']:
                existing = User.query.filter_by(email=data['email']).first()
                if existing and existing.id != user_id:
                    return jsonify({"error": "Email already exists"}), 400
            user.email = data['email']
        
        if 'password' in data and data['password']:
            user.password = data['password']  # TODO: Hash password
        
        if 'role' in data:
            user.role = validate_user_role(data['role'])
        
        if 'firstname' in data:
            user.firstname = data['firstname']
        
        if 'lastname' in data:
            user.lastname = data['lastname']
        
        if 'organization_id' in data:
            user.organization_id = data['organization_id']
        
        if 'survey_code' in data:
            user.survey_code = data['survey_code']

        if 'title_id' in data:
            user.title_id = data['title_id']
            
        if 'roles' in data:
            user.roles = []
            for r_name in data['roles']:
                role_obj = Role.query.filter_by(name=r_name).first()
                if not role_obj:
                    role_obj = Role(name=r_name, description=f'Role: {r_name}')
                    db.session.add(role_obj)
                user.roles.append(role_obj)
                
        if 'titles' in data:
            user.titles = []
            for t_name in data['titles']:
                title_obj = Title.query.filter_by(name=t_name).first()
                if not title_obj:
                    title_obj = Title(name=t_name)
                    db.session.add(title_obj)
                user.titles.append(title_obj)
        
        db.session.commit()
        
        return jsonify({
            "message": "User updated successfully",
            "user_id": user.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user and all related records."""
    user = User.query.get_or_404(user_id)
    
    try:
        # Delete related records
        UserDetails.query.filter_by(user_id=user_id).delete()
        UserOrganizationTitle.query.filter_by(user_id=user_id).delete()
        
        # Delete geo location if exists
        if user.geo_location_id:
            GeoLocation.query.filter_by(id=user.geo_location_id).delete()
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({"message": "User deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-details/<int:user_id>', methods=['GET'])
def get_user_details(user_id):
    """Get user details for a specific user."""
    user_details = UserDetails.query.filter_by(user_id=user_id).first()
    
    if not user_details:
        return jsonify({
            "user_id": user_id,
            "form_data": {},
            "status": "not_started"
        }), 200
    
    return jsonify({
        "id": user_details.id,
        "user_id": user_details.user_id,
        "organization_id": user_details.organization_id,
        "form_data": user_details.form_data,
        "status": user_details.status,
        "created_at": user_details.created_at.isoformat() if user_details.created_at else None,
        "updated_at": user_details.updated_at.isoformat() if user_details.updated_at else None
    }), 200


@users_bp.route('/user-details', methods=['POST'])
def save_user_details():
    """Save or update user details (form data)."""
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    try:
        user_details = UserDetails.query.filter_by(user_id=user_id).first()
        
        if user_details:
            user_details.form_data = data.get('form_data', user_details.form_data)
            user_details.status = data.get('status', user_details.status)
            if 'organization_id' in data:
                user_details.organization_id = data['organization_id']
        else:
            user_details = UserDetails(
                user_id=user_id,
                organization_id=data.get('organization_id'),
                form_data=data.get('form_data', {}),
                status=data.get('status', 'draft')
            )
            db.session.add(user_details)
        
        db.session.commit()
        
        return jsonify({
            "message": "User details saved successfully",
            "id": user_details.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving user details: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-details/submit', methods=['POST'])
def submit_user_details():
    """Submit user details (final submission)."""
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID is required"}), 400
    
    try:
        user_details = UserDetails.query.filter_by(user_id=user_id).first()
        
        if not user_details:
            return jsonify({"error": "User details not found"}), 404
        
        user_details.status = 'submitted'
        db.session.commit()
        
        return jsonify({
            "message": "User details submitted successfully",
            "id": user_details.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error submitting user details: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/roles', methods=['GET'])
def get_roles():
    """Get all roles."""
    try:
        roles = Role.query.all()
        return jsonify([{
            "id": role.id,
            "name": role.name,
            "description": role.description
        } for role in roles]), 200
    except Exception as e:
        logger.error(f"Error getting roles: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/roles', methods=['POST'])
def add_role():
    """Add a new role."""
    data = request.json
    name = data.get('name')
    description = data.get('description')
    
    if not name:
        return jsonify({"error": "Role name is required"}), 400
    
    if Role.query.filter_by(name=name).first():
        return jsonify({"error": "Role already exists"}), 400
    
    try:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.commit()
        
        return jsonify({
            "message": "Role created successfully",
            "id": role.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating role: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-organizational-titles/<int:user_id>', methods=['GET'])
def get_user_organizational_titles(user_id):
    """Get all organizational titles for a user."""
    try:
        titles = UserOrganizationTitle.query.filter_by(user_id=user_id).all()
        return jsonify([{
            "id": t.id,
            "user_id": t.user_id,
            "organization_id": t.organization_id,
            "organization_name": t.organization.name if t.organization else None,
            "title_id": t.title_id,
            "title_name": t.title.name if t.title else None
        } for t in titles]), 200
    except Exception as e:
        logger.error(f"Error getting user organizational titles: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-organizational-titles', methods=['POST'])
def add_user_organizational_title():
    """Add a user to an organization with a specific title."""
    data = request.json
    user_id = data.get('user_id')
    organization_id = data.get('organization_id')
    title_id = data.get('title_id')
    
    if not all([user_id, organization_id, title_id]):
        return jsonify({"error": "user_id, organization_id, and title_id are required"}), 400
    
    try:
        # Check if this assignment already exists
        existing = UserOrganizationTitle.query.filter_by(
            user_id=user_id,
            organization_id=organization_id,
            title_id=title_id
        ).first()
        
        if existing:
            return jsonify({"error": "This title assignment already exists"}), 400
        
        title_assignment = UserOrganizationTitle(
            user_id=user_id,
            organization_id=organization_id,
            title_id=title_id
        )
        db.session.add(title_assignment)
        db.session.commit()
        
        return jsonify({
            "message": "User organizational title added successfully",
            "id": title_assignment.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding user organizational title: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-organizational-titles/<int:user_id>', methods=['PUT'])
def update_user_organizational_titles(user_id):
    """Update organizational titles for a user."""
    data = request.json
    # Expect list of {organization_id, title_id}
    titles_data = data.get('titles', []) 
    
    try:
        # Delete existing titles for this user
        UserOrganizationTitle.query.filter_by(user_id=user_id).delete()
        
        # Add new titles
        for title_data in titles_data:
            title_assignment = UserOrganizationTitle(
                user_id=user_id,
                organization_id=title_data.get('organization_id'),
                title_id=title_data.get('title_id')
            )
            db.session.add(title_assignment)
        
        db.session.commit()
        
        return jsonify({
            "message": "User organizational titles updated successfully",
            "user_id": user_id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user organizational titles: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-details', methods=['GET'])
def get_all_user_details():
    """Retrieve all user details from the database."""
    try:
        all_details = UserDetails.query.all()
        return jsonify([{
            "id": ud.id,
            "user_id": ud.user_id,
            "organization_id": ud.organization_id,
            "form_data": ud.form_data,
            "status": ud.status,
            "created_at": ud.created_at.isoformat() if ud.created_at else None,
            "updated_at": ud.updated_at.isoformat() if ud.updated_at else None
        } for ud in all_details]), 200
    except Exception as e:
        logger.error(f"Error getting all user details: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/user-details/<int:user_id>/status', methods=['GET'])
def get_user_details_status(user_id):
    """Get the status of user details for the dashboard."""
    try:
        user = User.query.get_or_404(user_id)
        user_details = UserDetails.query.filter_by(user_id=user_id).first()
        
        return jsonify({
            "user_id": user_id,
            "has_details": user_details is not None,
            "status": user_details.status if user_details else "not_started",
            "personal_details_filled": bool(user_details and user_details.form_data),
            "form_data_keys": list(user_details.form_data.keys()) if user_details and user_details.form_data else []
        }), 200
    except Exception as e:
        logger.error(f"Error getting user details status: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/users/role/user', methods=['GET'])
def get_users_with_role_user():
    """Get all users with role 'user'."""
    try:
        users = User.query.filter_by(role='user').all()
        return jsonify([{
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "firstname": user.firstname,
            "lastname": user.lastname,
            "organization_id": user.organization_id,
            "organization_name": user.organization.name if user.organization else None,
            "survey_code": user.survey_code
        } for user in users]), 200
    except Exception as e:
        logger.error(f"Error getting users with role user: {str(e)}")
        return jsonify({"error": str(e)}), 500


@users_bp.route('/users/upload', methods=['POST'])
def upload_users():
    """Upload users from CSV file."""
    import csv
    import io
    
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "File must be a CSV"}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"))
        reader = csv.DictReader(stream)
        
        created_users = []
        errors = []
        
        for row_num, row in enumerate(reader, start=2):
            try:
                username = row.get('username', '').strip()
                email = row.get('email', '').strip()
                
                if not username:
                    errors.append(f"Row {row_num}: Username is required")
                    continue
                
                if User.query.filter_by(username=username).first():
                    errors.append(f"Row {row_num}: Username '{username}' already exists")
                    continue
                
                if email and User.query.filter_by(email=email).first():
                    errors.append(f"Row {row_num}: Email '{email}' already exists")
                    continue
                
                password = row.get('password', '').strip() or secrets.token_urlsafe(8)
                survey_code = row.get('survey_code', '').strip() or generate_survey_code()
                
                new_user = User(
                    username=username,
                    password=password,
                    email=email or None,
                    role=validate_user_role(row.get('role', 'user')),
                    firstname=row.get('firstname', '').strip() or None,
                    lastname=row.get('lastname', '').strip() or None,
                    organization_id=int(row.get('organization_id')) if row.get('organization_id') else None,
                    survey_code=survey_code
                )
                db.session.add(new_user)
                db.session.flush()
                
                created_users.append({
                    "id": new_user.id,
                    "username": username,
                    "password": password,
                    "survey_code": survey_code
                })
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            "message": f"Upload complete. Created {len(created_users)} users.",
            "created_users": created_users,
            "errors": errors
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error uploading users: {str(e)}")
        return jsonify({"error": str(e)}), 500
