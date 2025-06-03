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
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app and SQLAlchemy
app = Flask(__name__)

# Configure CORS to allow requests from the React frontend
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",    # for local dev
                "http://3.142.171.30",       # your EC2-served frontend
                "http://18.222.89.189"
            ]
        }
    },
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization"]
)

# 1) Env-based settings
env_user     = os.getenv("DB_USER")
env_password = os.getenv("DB_PASSWORD")
env_host     = os.getenv("DB_HOST")
env_port     = os.getenv("DB_PORT", "3306")
env_name     = os.getenv("DB_NAME")

# 2) Attempt to build a URL from env
db_url = None
if env_user and env_password and env_host and env_name:
    db_url_candidate = (
        f"mysql+pymysql://{env_user}:{env_password}"
        f"@{env_host}:{env_port}/{env_name}"
    )
    # 3) Test it
    try:
        engine = create_engine(db_url_candidate)
        conn = engine.connect()
        conn.close()
        db_url = db_url_candidate
        logger.info("✅ Connected using .env settings")
    except OperationalError as e:
        logger.warning(f"⚠️  .env DB connection failed: {e}")

# 4) Fallback to local_* variables if env failed
if not db_url:
    # Local defaults
    local_db_user     = 'root'
    local_db_password = 'jaideep'
    local_db_host     = 'localhost'
    local_db_port     = '3306'
    local_db_name     = 'boskopartnersdb'

    fallback_url = (
        f"mysql+pymysql://{local_db_user}:{local_db_password}"
        f"@{local_db_host}:{local_db_port}/{local_db_name}"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = fallback_url
    logger.info("✅ Using local database settings")
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url

"""
# Database configuration
DB_USER = 'root'
DB_PASSWORD = 'rootroot'
DB_HOST = 'localhost'
DB_NAME = 'boskopartnersdb'

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
"""
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


class Survey(db.Model):
    __tablename__ = 'surveys'
    id = db.Column(db.Integer, primary_key=True)
    survey_code = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
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

# Question Types API Endpoints
@app.route('/api/question-types', methods=['GET'])
def get_question_types():
    """Get all question types, optionally filtered by category"""
    category = request.args.get('category')
    
    query = QuestionType.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    
    question_types = query.all()
    
    return jsonify([{
        'id': qt.id,
        'name': qt.name,
        'display_name': qt.display_name,
        'category': qt.category,
        'description': qt.description,
        'config_schema': qt.config_schema
    } for qt in question_types]), 200

@app.route('/api/question-types/<int:type_id>', methods=['GET'])
def get_question_type(type_id):
    """Get a specific question type by ID"""
    question_type = QuestionType.query.get_or_404(type_id)
    
    return jsonify({
        'id': question_type.id,
        'name': question_type.name,
        'display_name': question_type.display_name,
        'category': question_type.category,
        'description': question_type.description,
        'config_schema': question_type.config_schema
    }), 200

@app.route('/api/question-types/categories', methods=['GET'])
def get_question_type_categories():
    """Get all unique question type categories"""
    categories = db.session.query(QuestionType.category).filter_by(is_active=True).distinct().all()
    return jsonify([cat[0] for cat in categories]), 200

@app.route('/api/question-types/initialize', methods=['POST'])
def initialize_question_types():
    """Initialize the database with all question types from the configuration"""
    try:
        # Question types data matching the frontend configuration
        question_types_data = [
            # Standard Content Questions
            {
                'id': 1, 'name': 'text_graphic', 'display_name': 'Text / Graphic',
                'category': 'Standard Content', 'description': 'Display text, images, or other media content',
                'config_schema': {'content_type': 'text', 'content': '', 'alignment': 'left'}
            },
            {
                'id': 2, 'name': 'multiple_choice', 'display_name': 'Multiple Choice',
                'category': 'Standard Content', 'description': 'Single or multiple selection from predefined options',
                'config_schema': {'selection_type': 'single', 'options': [], 'randomize_options': False, 'allow_other': False, 'other_text': 'Other (please specify)'}
            },
            {
                'id': 3, 'name': 'matrix_table', 'display_name': 'Matrix Table',
                'category': 'Standard Content', 'description': 'Grid of questions with same answer choices',
                'config_schema': {'statements': [], 'scale_points': [], 'force_response': False, 'randomize_statements': False}
            },
            {
                'id': 4, 'name': 'text_entry', 'display_name': 'Text Entry',
                'category': 'Standard Content', 'description': 'Open-ended text responses',
                'config_schema': {'input_type': 'single_line', 'validation': None, 'max_length': None, 'placeholder': ''}
            },
            {
                'id': 5, 'name': 'form_field', 'display_name': 'Form Field',
                'category': 'Standard Content', 'description': 'Structured form inputs (name, address, etc.)',
                'config_schema': {'field_type': 'name', 'required_fields': [], 'format': 'standard'}
            },
            {
                'id': 6, 'name': 'slider', 'display_name': 'Slider',
                'category': 'Standard Content', 'description': 'Numeric input using a slider interface',
                'config_schema': {'min_value': 0, 'max_value': 100, 'step': 1, 'default_value': None, 'labels': {'min_label': '', 'max_label': ''}}
            },
            {
                'id': 7, 'name': 'rank_order', 'display_name': 'Rank Order',
                'category': 'Standard Content', 'description': 'Drag and drop ranking of items',
                'config_schema': {'items': [], 'force_ranking': True, 'randomize_items': False}
            },
            {
                'id': 8, 'name': 'side_by_side', 'display_name': 'Side by Side',
                'category': 'Standard Content', 'description': 'Multiple questions displayed horizontally',
                'config_schema': {'questions': [], 'layout': 'equal_width'}
            },
            {
                'id': 9, 'name': 'autocomplete', 'display_name': 'Autocomplete',
                'category': 'Standard Content', 'description': 'Text input with autocomplete suggestions',
                'config_schema': {'suggestions': [], 'allow_custom': True, 'max_suggestions': 10}
            },
            # Specialty Questions
            {
                'id': 10, 'name': 'constant_sum', 'display_name': 'Constant Sum',
                'category': 'Specialty Questions', 'description': 'Numeric entries that sum to a specific total',
                'config_schema': {'items': [], 'total_sum': 100, 'allow_decimals': False}
            },
            {
                'id': 11, 'name': 'pick_group_rank', 'display_name': 'Pick, Group & Rank',
                'category': 'Specialty Questions', 'description': 'Select, categorize, and rank items',
                'config_schema': {'items': [], 'groups': [], 'max_picks': None, 'require_ranking': True}
            },
            {
                'id': 12, 'name': 'hot_spot', 'display_name': 'Hot Spot',
                'category': 'Specialty Questions', 'description': 'Click on areas of an image',
                'config_schema': {'image_url': '', 'hot_spots': [], 'max_selections': None}
            },
            {
                'id': 13, 'name': 'heat_map', 'display_name': 'Heat Map',
                'category': 'Specialty Questions', 'description': 'Visual heat map responses on images',
                'config_schema': {'image_url': '', 'heat_intensity': 'medium'}
            },
            {
                'id': 14, 'name': 'graphic_slider', 'display_name': 'Graphic Slider',
                'category': 'Specialty Questions', 'description': 'Slider with custom graphics',
                'config_schema': {'min_value': 0, 'max_value': 100, 'step': 1, 'graphic_type': 'emoji', 'graphics': []}
            },
            {
                'id': 15, 'name': 'drill_down', 'display_name': 'Drill Down',
                'category': 'Specialty Questions', 'description': 'Hierarchical selection (country > state > city)',
                'config_schema': {'levels': [], 'data_source': 'custom'}
            },
            {
                'id': 16, 'name': 'net_promoter_score', 'display_name': 'Net Promoter Score',
                'category': 'Specialty Questions', 'description': 'Standard NPS question with 0-10 scale',
                'config_schema': {'scale_type': '0_to_10', 'labels': {'detractor': 'Not at all likely', 'promoter': 'Extremely likely'}}
            },
            {
                'id': 17, 'name': 'highlight', 'display_name': 'Highlight',
                'category': 'Specialty Questions', 'description': 'Highlight text or sections in content',
                'config_schema': {'content': '', 'highlight_color': '#ffff00', 'max_highlights': None}
            },
            {
                'id': 18, 'name': 'signature', 'display_name': 'Signature',
                'category': 'Specialty Questions', 'description': 'Digital signature capture',
                'config_schema': {'required': True, 'canvas_width': 400, 'canvas_height': 200}
            },
            {
                'id': 19, 'name': 'video_response', 'display_name': 'Video Response',
                'category': 'Specialty Questions', 'description': 'Record video responses',
                'config_schema': {'max_duration': 300, 'allow_retake': True, 'quality': 'medium'}
            },
            {
                'id': 20, 'name': 'user_testing', 'display_name': 'User Testing',
                'category': 'Specialty Questions', 'description': 'Website or app usability testing',
                'config_schema': {'target_url': '', 'tasks': [], 'record_screen': True}
            },
            {
                'id': 21, 'name': 'tree_testing', 'display_name': 'Tree Testing',
                'category': 'Specialty Questions', 'description': 'Information architecture testing',
                'config_schema': {'tree_structure': {}, 'tasks': [], 'show_parent_labels': True}
            },
            # Advanced Questions
            {
                'id': 22, 'name': 'timing', 'display_name': 'Timing',
                'category': 'Advanced Questions', 'description': 'Measure response time and page timing',
                'config_schema': {'track_page_time': True, 'track_question_time': True, 'visible_timer': False}
            },
            {
                'id': 23, 'name': 'meta_info', 'display_name': 'Meta Info',
                'category': 'Advanced Questions', 'description': 'Capture browser and device information',
                'config_schema': {'capture_browser': True, 'capture_device': True, 'capture_location': False}
            },
            {
                'id': 24, 'name': 'file_upload', 'display_name': 'File Upload',
                'category': 'Advanced Questions', 'description': 'Upload files and documents',
                'config_schema': {'allowed_types': ['pdf', 'doc', 'docx', 'jpg', 'png'], 'max_size_mb': 10, 'max_files': 1}
            },
            {
                'id': 25, 'name': 'captcha', 'display_name': 'Captcha',
                'category': 'Advanced Questions', 'description': 'Bot prevention and verification',
                'config_schema': {'captcha_type': 'recaptcha', 'difficulty': 'medium'}
            },
            {
                'id': 26, 'name': 'location_selector', 'display_name': 'Location Selector',
                'category': 'Advanced Questions', 'description': 'Geographic location selection',
                'config_schema': {'selection_type': 'map', 'default_zoom': 10, 'restrict_country': None}
            },
            {
                'id': 27, 'name': 'arcgis_map', 'display_name': 'ArcGIS Map',
                'category': 'Advanced Questions', 'description': 'Advanced mapping with ArcGIS integration',
                'config_schema': {'map_service_url': '', 'layers': [], 'tools': ['pan', 'zoom']}
            }
        ]
        
        # Clear existing question types and add new ones
        QuestionType.query.delete()
        
        for qt_data in question_types_data:
            question_type = QuestionType(
                id=qt_data['id'],
                name=qt_data['name'],
                display_name=qt_data['display_name'],
                category=qt_data['category'],
                description=qt_data['description'],
                config_schema=qt_data['config_schema'],
                is_active=True
            )
            db.session.add(question_type)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Question types initialized successfully',
            'count': len(question_types_data)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing question types: {str(e)}")
        return jsonify({'error': 'Failed to initialize question types'}), 500

if __name__ == '__main__':
    #with app.app_context():
        # Drop and recreate tables to ensure schema is up-to-date
        #print("Recreating database tables to ensure schema is up-to-date...")
        #db.drop_all()  # This will drop all tables - be careful in production!
        #db.create_all()  # This will create all tables based on your models
        #print("Database tables created successfully!")
    app.run(debug=True)
