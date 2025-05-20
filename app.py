from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy import text
from sqlalchemy import UniqueConstraint
import json
from datetime import datetime
import logging
import traceback
import uuid
from sqlalchemy import event
from uuid import uuid4
import os
from werkzeug.utils import secure_filename

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app and SQLAlchemy
app = Flask(__name__)

# Configure CORS to allow requests from the React frontend
CORS(
    app,
    resources={r"/api/*": {"origins": "http://localhost:3000"}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"]
)

# Database configuration
DB_USER = 'root'
DB_PASSWORD = 'jaideep'
DB_HOST = 'localhost'
DB_NAME = 'boskopartnersdb'

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True  # Log all SQL queries
db = SQLAlchemy(app)

# Function to create tables if they don't exist
def create_tables():
    with app.app_context():
        db.create_all()
        print("Tables created or already exist.")

# Define models
class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Enum('church', 'school', 'other'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Organization {self.name}>'

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other'), default='user')
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    survey_code = db.Column(db.String(36), nullable=True)  # UUID as string for user surveys
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationship with Organization
    organization = db.relationship('Organization', foreign_keys=[organization_id], backref=db.backref('users', lazy=True))
    
    def __repr__(self):
        return f'<User {self.username}>'

class UserDetails(db.Model):
    __tablename__ = 'user_details'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    form_data = db.Column(JSON, nullable=True)  # Store JSON data
    is_submitted = db.Column(db.Boolean, default=False)
    last_page = db.Column(db.Integer, default=1)  # Track which page user is on
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('details', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('details', lazy=True))
    
    def __repr__(self):
        return f'<UserDetails user_id={self.user_id}>'

class SurveyTemplateVersion(db.Model):
    __tablename__ = 'survey_template_versions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<SurveyTemplateVersion {self.name}>'    

class SurveyTemplate(db.Model):
    __tablename__ = 'survey_templates'
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('survey_template_versions.id'), nullable=False)
    survey_code = db.Column(db.String(100), nullable=False, unique=True)
    questions = db.Column(JSON, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    version = db.relationship('SurveyTemplateVersion', backref=db.backref('templates', lazy=True))
    
    def __repr__(self):
        return f'<SurveyTemplate {self.survey_code}>'    

class SurveyResponse(db.Model):
    __tablename__ = 'survey_responses'
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    answers = db.Column(JSON, nullable=False)
    status = db.Column(db.Enum('pending','in_progress','completed'), 
                       nullable=False, default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    template = db.relationship('SurveyTemplate', backref=db.backref('responses', lazy=True))
    user = db.relationship('User', backref=db.backref('survey_responses', lazy=True))
    
    def __repr__(self):
        return f'<SurveyResponse {self.id} for template {self.template_id}>'

    def __repr__(self):
        return f'<Survey {self.survey_code} for User {self.user_id}>'

class SurveyVersion(db.Model):
    __tablename__ = 'survey_versions'
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    __table_args__ = (UniqueConstraint('survey_id', 'version_number'),)
    survey = db.relationship('SurveyTemplate', backref=db.backref('versions', lazy=True))

    def __repr__(self):
        return f'<SurveyVersion survey_id={self.survey_id} v{self.version_number}>'

class QuestionType(db.Model):
    __tablename__ = 'question_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<QuestionType {self.name}>'

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('survey_templates.id'), nullable=False)
    question_type_id = db.Column(db.Integer, db.ForeignKey('question_types.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    section = db.Column(db.String(100), nullable=True)  # New column for section
    order = db.Column(db.Integer, nullable=False)
    is_required = db.Column(db.Boolean, default=False)
    config = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    template = db.relationship('SurveyTemplate', backref=db.backref('question_list', lazy=True))
    type = db.relationship('QuestionType')
    
    def __repr__(self):
        return f'<Question {self.question_text[:20]}...>'

class QuestionOption(db.Model):
    __tablename__ = 'question_options'
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    option_text = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False)
    question = db.relationship('Question', backref=db.backref('options', lazy=True))

    def __repr__(self):
        return f'<QuestionOption q_id={self.question_id} option={self.option_text}>'

# Routes

@app.route('/')
def index():
    return "Hello, welcome to the Bosko Partners app!"

# Example route to list users
@app.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    users_list = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'organization_id': user.organization_id
    } for user in users]
    return jsonify(users_list)

# Login API Endpoint
@app.route('/api/users/login', methods=['POST'])
def login():
    data = request.get_json()
    identifier = data.get("username")  # Can be username or email
    password = data.get("password")
    
    if not identifier or not password:
        return jsonify({"error": "Username/email and password required"}), 400

    # Check for a user matching either the username or email
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # NOTE: In production, passwords should be hashed. This is for demonstration only.
    if user.password != password:
        return jsonify({"error": "Invalid credentials"}), 401

    # Signal that the login is successful (redirect to landing page on frontend)
    return jsonify({
        "message": "Login successful",
        "data": {
            "id": user.id,
            "organization_id": user.organization_id,
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }), 200


@app.route('/api/users/register', methods=['POST'])
def register():
    data = request.get_json()
    # Generate a UUID for the survey code if role is 'user'
    survey_code = str(uuid4()) if data.get('role', 'user') == 'user' else None
    
    new_user = User(
      username=data['username'],
      email   =data['email'],
      password=data['password'],
      role=data.get('role', 'user'),
      organization_id=data['organization_id'],
      survey_code=survey_code
    )
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({ 
        "message": "User created successfully", 
        "user_id": new_user.id,
        "survey_code": survey_code
    }), 201

@app.route('/api/surveys/validate', methods=['POST'])
def validate_survey():
    """
    Expects JSON { "survey_code": "<code>" }.
    Returns 200 + survey info if valid, 400 if missing code, 404 if not found.
    """
    data = request.get_json() or {}
    code = data.get("survey_code")
    if not code:
        return jsonify({"error": "survey_code is required"}), 400

    # Find the user with this survey code
    user = User.query.filter_by(survey_code=code).first()
    if not user:
        return jsonify({"error": "Invalid survey code"}), 404

    # Build whatever payload the frontend needs
    payload = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "survey_code": user.survey_code,
        "organization_id": user.organization_id,
        "role": user.role
    }
    return jsonify({"valid": True, "survey": payload}), 200

# Add these API endpoints
@app.route('/api/user-details/<int:user_id>', methods=['GET'])
def get_user_details(user_id):
    """
    Retrieve user details for a specific user.
    This is used to load saved form data when a user returns to continue filling out the form.
    """
    try:
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get user details
        details = UserDetails.query.filter_by(user_id=user_id).first()
        
        if not details:
            # Return empty data if no details exist yet
            return jsonify({
                "user_id": user_id,
                "form_data": {
                    "personal": {},
                    "organizational": {}
                },
                "is_submitted": False,
                "last_page": 1
            }), 200
        
        # Return user details
        return jsonify({
            "user_id": details.user_id,
            "organization_id": details.organization_id,
            "form_data": details.form_data,
            "is_submitted": details.is_submitted,
            "last_page": details.last_page
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving user details: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "An error occurred while retrieving user details"}), 500

@app.route('/api/user-details/status/<int:user_id>', methods=['GET'])
def get_user_details_status(user_id):
    """
    Get the status of user details for the dashboard.
    Returns whether personal details are filled and other status information.
    """
    try:
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get user details
        details = UserDetails.query.filter_by(user_id=user_id).first()
        logger.info(f"Fetched details: {details!r}")
        if not details:
            # Return default status if no details exist yet
            return jsonify({
                "user_id": user_id,
                "personal_details_filled": False,
                "organizational_details_filled": False,
                "is_submitted": False,
                "last_page": 1
            }), 200
        
        # Check if personal details are filled (first name and last name are required)
        personal_filled = False
        organizational_filled = False
        
        if details.form_data and 'personal' in details.form_data:
            personal = details.form_data['personal']
            if personal.get('firstName') and personal.get('lastName'):
                personal_filled = True
        
        if details.form_data and 'organizational' in details.form_data:
            org = details.form_data['organizational']
            if (org.get('country') and org.get('region') and 
                org.get('church') and org.get('school')):
                organizational_filled = True
        
        # Return status information
        return jsonify({
            "user_id": details.user_id,
            "personal_details_filled": personal_filled,
            "organizational_details_filled": organizational_filled,
            "is_submitted": details.is_submitted,
            "last_page": details.last_page,
            "form_data": details.form_data  # Include form data for display on dashboard
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving user details status: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": "An error occurred while retrieving user details status"}), 500

@app.route('/api/user-details/save', methods=['POST'])
def save_user_details():
    """Save form data (both Save & Continue and Save & Exit)"""
    logger.info("POST request to save user_details")
    
    try:
        data = request.json
        logger.debug(f"Received data: {data}")
        
        user_id = data.get('user_id')
        organization_id = data.get('organization_id')
        form_data = data.get('form_data', {})
        last_page = data.get('current_page', 1)
        action = data.get('action', 'continue')  # 'continue' or 'exit'
        
        if not user_id or not organization_id:
            logger.error("Missing required fields: user_id or organization_id")
            return jsonify({"error": "Missing required fields"}), 400
        
        logger.info(f"Processing save for user_id: {user_id}, org_id: {organization_id}, page: {last_page}, action: {action}")
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User with ID {user_id} not found")
            return jsonify({"error": f"User with ID {user_id} not found"}), 404
            
        # Check if organization exists
        org = Organization.query.get(organization_id)
        if not org:
            logger.error(f"Organization with ID {organization_id} not found")
            return jsonify({"error": f"Organization with ID {organization_id} not found"}), 404
        
        # Find existing or create new
        user_details = UserDetails.query.filter_by(user_id=user_id).first()
        
        if not user_details:
            logger.info(f"Creating new UserDetails record for user_id: {user_id}")
            user_details = UserDetails(
                user_id=user_id,
                organization_id=organization_id,
                form_data=form_data,
                last_page=last_page
            )
            db.session.add(user_details)
        else:
            logger.info(f"Updating existing UserDetails record for user_id: {user_id}")
            # Update existing record
            user_details.form_data = form_data
            user_details.last_page = last_page
            user_details.updated_at = datetime.utcnow()
        
        db.session.commit()
        logger.info(f"Successfully saved user_details for user_id: {user_id}")
        
        return jsonify({
            "message": "Data saved successfully",
            "action": action,
            "last_page": last_page
        }), 200
    except Exception as e:
        logger.error(f"Error saving user_details: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/user-details/submit', methods=['POST'])
def submit_user_details():
    """Final submission of the form"""
    logger.info("POST request to submit user_details")
    
    try:
        data = request.json
        logger.debug(f"Received data: {data}")
        
        user_id = data.get('user_id')
        form_data = data.get('form_data', {})
        organization_id = data.get('organization_id', 1)  # Default to 1 if not provided
        
        if not user_id:
            logger.error("Missing required field: user_id")
            return jsonify({"error": "Missing required field: user_id"}), 400
            
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User with ID {user_id} not found")
            return jsonify({"error": f"User with ID {user_id} not found"}), 404
        
        # Find existing user details or create new
        user_details = UserDetails.query.filter_by(user_id=user_id).first()
        
        if not user_details:
            logger.info(f"Creating new user details record for user_id: {user_id}")
            user_details = UserDetails(
                user_id=user_id,
                organization_id=organization_id,
                form_data=form_data,
                is_submitted=True,
                last_page=3  # Assuming submission is from the last page
            )
            db.session.add(user_details)
        else:
            logger.info(f"Updating existing user details record for user_id: {user_id}")
            # Update and mark as submitted
            user_details.form_data = form_data
            user_details.is_submitted = True
            user_details.updated_at = datetime.utcnow()
        
        db.session.commit()
        logger.info(f"Successfully submitted form for user_id: {user_id}")
        
        return jsonify({
            "message": "Form submitted successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error submitting user_details: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# Add this API endpoint to view all user details
@app.route('/api/user-details', methods=['GET'])
def get_all_user_details():
    """Retrieve all user details from the database"""
    user_details = UserDetails.query.all()
    print(f"Number of user details retrieved: {len(user_details)}")
    user_details_list = []
    for detail in user_details:
        user_details_list.append({
            'id': detail.id,
            'user_id': detail.user_id,
            'organization_id': detail.organization_id,
            'form_data': detail.form_data,
            'is_submitted': detail.is_submitted,
            'last_page': detail.last_page,
            'created_at': detail.created_at.isoformat() if detail.created_at else None,
            'updated_at': detail.updated_at.isoformat() if detail.updated_at else None
        })
        print(f"User Details: {detail.id}, {detail.user_id}, {detail.organization_id}, {detail.form_data}, {detail.is_submitted}")
    return jsonify(user_details_list), 200

# Add a test endpoint to verify database connectivity
@app.route('/api/test-database', methods=['GET'])
def test_database():
    """Test database connectivity and insertion"""
    logger.info("Testing database connectivity")
    
    try:
        # Test database connection
        db.session.execute("SELECT 1")
        
        # Create a test user_details entry
        test_data = {
            "personal": {
                "firstName": "Test",
                "lastName": "User"
            },
            "organizational": {
                "country": "Test Country",
                "region": "Test Region"
            }
        }
        
        # Create a test record
        test_detail = UserDetails(
            user_id=999,
            organization_id=1,
            form_data=test_data,
            last_page=1
        )
        
        # Add and commit to test insertion
        db.session.add(test_detail)
        db.session.commit()
        
        # Query to verify it was added
        inserted_record = UserDetails.query.filter_by(user_id=999).first()
        
        if inserted_record:
            # Delete the test record
            db.session.delete(inserted_record)
            db.session.commit()
            
            return jsonify({
                "status": "success",
                "message": "Database connection and insertion test successful"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to verify inserted record"
            }), 500
            
    except Exception as e:
        logger.error(f"Database test failed: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Database test failed: {str(e)}"
        }), 500

# Make sure users and organizations exist for testing
@app.route('/api/initialize-test-data', methods=['GET'])
def initialize_test_data():
    """Initialize test data for the application"""
    try:
        # Check if test organization exists
        test_org = Organization.query.filter_by(name="Test Organization").first()
        if not test_org:
            test_org = Organization(name="Test Organization", type="other")
            db.session.add(test_org)
            db.session.commit()
        
        # Check if test user exists
        test_user = User.query.filter_by(username="testuser").first()
        if not test_user:
            test_user = User(
                username="testuser",
                email="test@example.com",
                password="password",
                role="user",
                organization_id=test_org.id,
                firstname="Test",
                lastname="User"
            )
            db.session.add(test_user)
            db.session.commit()
            
        return jsonify({
            "status": "success",
            "message": "Test data initialized successfully",
            "test_user_id": test_user.id,
            "test_org_id": test_org.id
        }), 200
    except Exception as e:
        logger.error(f"Error initializing test data: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Error initializing test data: {str(e)}"
        }), 500

# Add a simple test endpoint to verify API is working
@app.route('/api/test', methods=['GET'])
def test_api():
    """Simple test endpoint to verify API is working"""
    return jsonify({
        "status": "success",
        "message": "API is working"
    }), 200

# Survey Template API Endpoints
@app.route('/api/template-versions', methods=['GET'])
def get_template_versions():
    versions = SurveyTemplateVersion.query.all()
    return jsonify([{"id": v.id, "name": v.name, "description": v.description, "created_at": v.created_at} for v in versions]), 200

@app.route('/api/template-versions', methods=['POST'])
def add_template_version():
    data = request.get_json() or {}
    if 'name' not in data:
        return jsonify({'error': 'name required'}), 400
    version = SurveyTemplateVersion(
        name=data['name'],
        description=data.get('description')
    )
    db.session.add(version)
    db.session.commit()
    return jsonify({
        'id': version.id, 
        'name': version.name, 
        'description': version.description
    }), 201

@app.route('/api/template-versions/<int:version_id>', methods=['DELETE'])
def delete_template_version(version_id):
    version = SurveyTemplateVersion.query.get_or_404(version_id)
    db.session.delete(version)
    db.session.commit()
    return jsonify({'deleted': True}), 200

@app.route('/api/templates', methods=['GET'])
def get_templates():
    templates = SurveyTemplate.query.all()
    return jsonify([{
        "id": t.id, 
        "version_id": t.version_id,
        "version_name": t.version.name,
        "survey_code": t.survey_code,
        "created_at": t.created_at
    } for t in templates]), 200

@app.route('/api/templates', methods=['POST'])
def add_template():
    data = request.get_json() or {}
    required_keys = ['version_id', 'survey_code', 'questions']
    if not all(k in data for k in required_keys):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check for duplicate survey_code
    existing = SurveyTemplate.query.filter_by(survey_code=data['survey_code']).first()
    if existing:
        return jsonify({'error': 'Survey code already exists'}), 400
        
    template = SurveyTemplate(
        version_id=data['version_id'],
        survey_code=data['survey_code'],
        questions=data['questions'],
    )
    db.session.add(template)
    db.session.commit()
    return jsonify({
        'id': template.id,
        'survey_code': template.survey_code
    }), 201

@app.route('/api/templates/<int:template_id>', methods=['GET'])
def get_template(template_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    return jsonify({
        "id": template.id,
        "version_id": template.version_id,
        "version_name": template.version.name,
        "survey_code": template.survey_code,
        "questions": template.questions,
        "created_at": template.created_at
    }), 200

@app.route('/api/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    data = request.get_json() or {}
    
    # Only allow updating questions for now
    if 'questions' in data:
        template.questions = data['questions']
        db.session.commit()
        return jsonify({'updated': True}), 200
    return jsonify({'error': 'No valid fields to update'}), 400

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    return jsonify({'deleted': True}), 200

@app.route('/api/templates/<int:template_id>/questions/<int:question_id>', methods=['DELETE'])
def delete_template_question(template_id, question_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    questions = template.questions or []
    updated = [q for q in questions if q.get('id') != question_id]
    template.questions = updated
    db.session.commit()
    return jsonify({'deleted': True}), 200

# Survey Responses API Endpoints
@app.route('/api/responses', methods=['GET'])
def get_responses():
    responses = SurveyResponse.query.all()
    return jsonify([{
        "id": r.id,
        "template_id": r.template_id,
        "user_id": r.user_id,
        "status": r.status,
        "created_at": r.created_at
    } for r in responses]), 200

@app.route('/api/templates/<int:template_id>/responses', methods=['POST'])
def add_response(template_id):
    data = request.get_json() or {}
    if 'user_id' not in data or 'answers' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
        
    response = SurveyResponse(
        template_id=template_id,
        user_id=data['user_id'],
        answers=data['answers'],
        status=data.get('status', 'pending')
    )
    db.session.add(response)
    db.session.commit()
    return jsonify({
        'id': response.id,
        'status': response.status
    }), 201

@app.route('/api/responses/<int:response_id>', methods=['GET'])
def get_response(response_id):
    response = SurveyResponse.query.get_or_404(response_id)
    return jsonify({
        "id": response.id,
        "template_id": response.template_id,
        "user_id": response.user_id,
        "answers": response.answers,
        "status": response.status,
        "created_at": response.created_at,
        "updated_at": response.updated_at
    }), 200

@app.route('/api/responses/<int:response_id>', methods=['PUT'])
def update_response(response_id):
    response = SurveyResponse.query.get_or_404(response_id)
    data = request.get_json() or {}
    
    for field in ['answers', 'status']:
        if field in data:
            setattr(response, field, data[field])
    
    db.session.commit()
    return jsonify({'updated': True}), 200

# Legacy Inventory endpoints for backward compatibility
@app.route('/api/surveys/<int:survey_id>/versions', methods=['GET'])
def get_survey_versions(survey_id):
    # For backward compatibility
    return jsonify([]), 200

@app.route('/api/surveys/<int:survey_id>/versions', methods=['POST'])
def add_survey_version(survey_id):
    # For backward compatibility
    return jsonify({'error': 'API deprecated, use template API instead'}), 400

@app.route('/api/versions/<int:version_id>', methods=['DELETE'])
def delete_survey_version(version_id):
    # For backward compatibility
    return jsonify({'error': 'API deprecated, use template API instead'}), 400

@app.route('/api/versions/<int:version_id>/questions', methods=['GET'])
def get_version_questions(version_id):
    # For backward compatibility
    return jsonify([]), 200

@app.route('/api/versions/<int:version_id>/questions', methods=['POST'])
def add_version_question(version_id):
    # For backward compatibility
    return jsonify({'error': 'API deprecated, use template API instead'}), 400

@app.route('/api/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    # For backward compatibility
    return jsonify({'error': 'API deprecated, use template API instead'}), 400

@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    # For backward compatibility
    return jsonify({'error': 'API deprecated, use template API instead'}), 400

# Organization API Endpoints
@app.route('/api/organizations', methods=['GET'])
def get_organizations():
    organizations = Organization.query.all()
    result = []
    for org in organizations:
        org_data = {
            'id': org.id,
            'name': org.name,
            'type': org.type,
        }
        result.append(org_data)
    return jsonify(result)

@app.route('/api/organizations/<int:org_id>', methods=['GET'])
def get_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    result = {
        'id': org.id,
        'name': org.name,
        'type': org.type
    }
    return jsonify(result)

@app.route('/api/organizations', methods=['POST'])
def add_organization():
    data = request.get_json()
    
    # Create the organization without type-specific details
    new_org = Organization(
        name=data['name'],
        type=data['type']
    )
    
    db.session.add(new_org)
    db.session.commit()
    
    return jsonify({
        'message': 'Organization added successfully',
        'id': new_org.id
    }), 201

@app.route('/api/organizations/<int:org_id>', methods=['PUT'])
def update_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    data = request.get_json()
    
    # Update basic organization fields only
    org.name = data.get('name', org.name)
    org.type = data.get('type', org.type)
    
    db.session.commit()
    
    return jsonify({'message': 'Organization updated successfully'})

@app.route('/api/organizations/<int:org_id>', methods=['DELETE'])
def delete_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    
    # Delete organization
    db.session.delete(org)
    db.session.commit()
    
    return jsonify({'message': 'Organization deleted successfully'})

@app.route('/api/organizations/<int:org_id>/users', methods=['GET'])
def get_organization_users(org_id):
    # Check if organization exists
    org = Organization.query.get_or_404(org_id)
    
    # Get users directly associated with the organization
    users = User.query.filter_by(organization_id=org_id).all()
    
    result = []
    for user in users:
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'firstname': user.firstname,
            'lastname': user.lastname
        }
        result.append(user_data)
    
    return jsonify(result)

# File upload endpoint for organizations
@app.route('/api/organizations/upload', methods=['POST'])
def upload_organizations():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Check file extension
    if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        return jsonify({'error': 'File must be CSV or XLSX format'}), 400
    
    # Save the file temporarily
    filename = secure_filename(file.filename)
    file_path = os.path.join('/tmp', filename)
    file.save(file_path)
    
    # Process the file (placeholder - actual implementation would depend on file format)
    try:
        # This is a placeholder for the actual file processing logic
        # In a real implementation, you would parse the CSV/XLSX and create organizations
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'status': 'pending_processing'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

# User API Endpoints
@app.route('/api/users', methods=['GET'])
def get_all_users():
    users = User.query.all()
    result = []
    for user in users:
        # Note: OrganizationUserRole has been removed
        # No roles will be included in the response
        
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'organization_id': user.organization_id
        }
        result.append(user_data)
    return jsonify(result)

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Note: OrganizationUserRole has been removed
    # No roles will be included in the response
    
    result = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'firstname': user.firstname,
        'lastname': user.lastname,
        'organization_id': user.organization_id
    }
    return jsonify(result)

@app.route('/api/users', methods=['POST'])
def add_user():
    data = request.get_json()
    
    # Create the user
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=data['password'],  # In production, this should be hashed
        role=data.get('role', 'user'),
        firstname=data.get('firstname'),
        lastname=data.get('lastname'),
        organization_id=data.get('organization_id')
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # Note: OrganizationUserRole has been removed
    # No role assignments will be performed
    
    return jsonify({
        'message': 'User added successfully',
        'id': new_user.id
    }), 201

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    # Update user fields
    if 'username' in data:
        user.username = data['username']
    if 'email' in data:
        user.email = data['email']
    if 'password' in data:
        user.password = data['password']  # In production, this should be hashed
    if 'role' in data:
        user.role = data['role']
    if 'firstname' in data:
        user.firstname = data['firstname']
    if 'lastname' in data:
        user.lastname = data['lastname']
    if 'organization_id' in data:
        user.organization_id = data['organization_id']
    
    # Note: OrganizationUserRole has been removed
    # No role management operations will be performed
    
    db.session.commit()
    
    return jsonify({'message': 'User updated successfully'})

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Note: OrganizationUserRole has been removed
    # No need to delete related roles
    
    # Delete user
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'message': 'User deleted successfully'})

# File upload endpoint for users
@app.route('/api/users/upload', methods=['POST'])
def upload_users():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Check file extension
    if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        return jsonify({'error': 'File must be CSV or XLSX format'}), 400
    
    # Save the file temporarily
    filename = secure_filename(file.filename)
    file_path = os.path.join('/tmp', filename)
    file.save(file_path)
    
    # Process the file (placeholder - actual implementation would depend on file format)
    try:
        # This is a placeholder for the actual file processing logic
        # In a real implementation, you would parse the CSV/XLSX and create users
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': filename,
            'status': 'pending_processing'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        # Clean up the temporary file
        if os.path.exists(file_path):
            os.remove(file_path)

# To initialize the database tables (run once)
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("Database tables created successfully!")

@app.route('/api/users/role/user', methods=['GET'])
def get_users_with_role_user():
    users = User.query.filter_by(role='user').all()
    result = []
    
    for user in users:
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'organization': {
                'id': user.organization.id,
                'name': user.organization.name,
                'type': user.organization.type
            } if user.organization else None
        }
        result.append(user_data)
    
    return jsonify(result)

# Add stub API endpoints for removed models to keep frontend working
# These will return empty data until the models are implemented

# Role API Endpoints (Stub)
@app.route('/api/roles', methods=['GET'])
def get_roles():
    # Return empty list since the Role model is not yet implemented
    return jsonify([])

@app.route('/api/roles', methods=['POST'])
def add_role():
    # Simulate adding a role (will be implemented later)
    return jsonify({
        'id': 1,  # Dummy ID
        'name': request.json.get('name', ''),
        'description': request.json.get('description', '')
    }), 201

# Denomination API Endpoints (Stub)
@app.route('/api/denominations', methods=['GET'])
def get_denominations():
    # Return empty list since the Denomination model is not yet implemented
    return jsonify([])

# Accreditation Bodies API Endpoints (Stub)
@app.route('/api/accreditation-bodies', methods=['GET'])
def get_accreditation_bodies():
    # Return empty list since the AccreditationBody model is not yet implemented
    return jsonify([])

# Umbrella Associations API Endpoints (Stub)
@app.route('/api/umbrella-associations', methods=['GET'])
def get_umbrella_associations():
    # Return empty list since the UmbrellaAssociation model is not yet implemented
    return jsonify([])

if __name__ == '__main__':
    #with app.app_context():
        # Drop and recreate tables to ensure schema is up-to-date
        #print("Recreating database tables to ensure schema is up-to-date...")
        #db.drop_all()  # This will drop all tables - be careful in production!
        #db.create_all()  # This will create all tables based on your models
        #print("Database tables created successfully!")
    app.run(debug=True)
