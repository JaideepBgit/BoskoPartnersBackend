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
    version_id = db.Column(db.Integer, db.ForeignKey('survey_template_versions.id'), nullable=False)
    survey_code = db.Column(db.String(100), nullable=False, unique=True)
    questions = db.Column(JSON, nullable=False)
    sections = db.Column(JSON, nullable=True)  # Store section names and their order
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
            "role": user.role,
            "survey_code": user.survey_code  # Include survey code for users
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

@app.route('/api/template-versions/<int:version_id>', methods=['PUT'])
def update_template_version(version_id):
    version = SurveyTemplateVersion.query.get_or_404(version_id)
    data = request.get_json() or {}
    
    updated = False
    
    if 'name' in data:
        version.name = data['name']
        updated = True
    
    if 'description' in data:
        version.description = data['description']
        updated = True
    
    if updated:
        db.session.commit()
        return jsonify({
            'id': version.id,
            'name': version.name,
            'description': version.description,
            'updated': True
        }), 200
    
    return jsonify({'error': 'No valid fields to update'}), 400

@app.route('/api/template-versions/<int:version_id>', methods=['DELETE'])
def delete_template_version(version_id):
    """Delete a template version and all its associated templates"""
    try:
        version = SurveyTemplateVersion.query.get_or_404(version_id)
        
        # Get all templates associated with this version
        associated_templates = SurveyTemplate.query.filter_by(version_id=version_id).all()
        template_ids = [template.id for template in associated_templates]
        
        # Delete records in the correct order to handle foreign key constraints
        deleted_counts = {
            'conditional_logic': 0,
            'survey_responses': 0,
            'questions': 0,
            'question_options': 0,
            'survey_versions': 0,
            'templates': 0
        }
        
        if template_ids:
            # 1. Delete conditional_logic records that reference these templates
            try:
                conditional_logic_result = db.session.execute(
                    text("DELETE FROM conditional_logic WHERE template_id IN :template_ids"),
                    {"template_ids": tuple(template_ids)}
                )
                deleted_counts['conditional_logic'] = conditional_logic_result.rowcount
                logger.info(f"Deleted {deleted_counts['conditional_logic']} conditional_logic records")
            except Exception as e:
                logger.warning(f"Error deleting conditional_logic records: {str(e)}")
            
            # 2. Delete survey responses
            survey_responses = SurveyResponse.query.filter(SurveyResponse.template_id.in_(template_ids)).all()
            for response in survey_responses:
                db.session.delete(response)
            deleted_counts['survey_responses'] = len(survey_responses)
            
            # 3. Delete questions and their options
            questions = Question.query.filter(Question.template_id.in_(template_ids)).all()
            question_ids = [q.id for q in questions]
            
            if question_ids:
                # Delete question options first
                question_options = QuestionOption.query.filter(QuestionOption.question_id.in_(question_ids)).all()
                for option in question_options:
                    db.session.delete(option)
                deleted_counts['question_options'] = len(question_options)
                
                # Then delete questions
                for question in questions:
                    db.session.delete(question)
                deleted_counts['questions'] = len(questions)
            
            # 4. Delete survey versions
            survey_versions = SurveyVersion.query.filter(SurveyVersion.survey_id.in_(template_ids)).all()
            for version_record in survey_versions:
                db.session.delete(version_record)
            deleted_counts['survey_versions'] = len(survey_versions)
        
        # 5. Delete the templates themselves
        for template in associated_templates:
            db.session.delete(template)
        deleted_counts['templates'] = len(associated_templates)
        
        # 6. Finally delete the version itself
        db.session.delete(version)
        db.session.commit()
        
        logger.info(f"Successfully deleted template version {version_id} and all associated records: {deleted_counts}")
        return jsonify({
            'deleted': True, 
            'version_id': version_id,
            'deleted_counts': deleted_counts
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template version {version_id}: {str(e)}")
        return jsonify({'error': f'Failed to delete template version: {str(e)}'}), 500

@app.route('/api/templates', methods=['GET'])
def get_templates():
    templates = SurveyTemplate.query.all()
    return jsonify([{
        "id": t.id, 
        "version_id": t.version_id,
        "version_name": t.version.name,
        "survey_code": t.survey_code,
        "sections": t.sections,
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
        "sections": template.sections,
        "created_at": template.created_at
    }), 200

@app.route('/api/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    data = request.get_json() or {}
    
    updated = False
    
    # Allow updating survey_code (template name)
    if 'survey_code' in data:
        logger.info(f"Updating survey_code for template {template_id} to: {data['survey_code']}")
        template.survey_code = data['survey_code']
        updated = True
    
    # Allow updating questions
    if 'questions' in data:
        logger.info(f"Updating questions for template {template_id}")
        logger.debug(f"New questions data: {data['questions']}")
        
        # Validate that all questions have required fields
        for question in data['questions']:
            if not all(key in question for key in ['id', 'question_text', 'question_type_id', 'order']):
                return jsonify({'error': 'Invalid question data: missing required fields'}), 400
        
        template.questions = data['questions']
        
        # Auto-update sections based on questions
        sections_from_questions = {}
        for question in data['questions']:
            section_name = question.get('section', 'Uncategorized')
            if section_name not in sections_from_questions:
                sections_from_questions[section_name] = len(sections_from_questions)
        
        # Preserve existing section order if available, add new sections at the end
        existing_sections = template.sections or {}
        updated_sections = {}
        
        # First, add existing sections in their current order
        for section_name, order in existing_sections.items():
            if section_name in sections_from_questions:
                updated_sections[section_name] = order
        
        # Then add new sections
        max_order = max(existing_sections.values()) if existing_sections else -1
        for section_name in sections_from_questions:
            if section_name not in updated_sections:
                max_order += 1
                updated_sections[section_name] = max_order
        
        template.sections = updated_sections
        updated = True
    
    # Allow updating sections order
    if 'sections' in data:
        logger.info(f"Updating sections for template {template_id}")
        logger.debug(f"New sections data: {data['sections']}")
        template.sections = data['sections']
        updated = True
    
    if updated:
        db.session.commit()
        logger.info(f"Successfully updated template {template_id}")
        return jsonify({'updated': True}), 200
    
    return jsonify({'error': 'No valid fields to update'}), 400

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """Delete a template and all its associated records"""
    try:
        template = SurveyTemplate.query.get_or_404(template_id)
        
        # Delete records in the correct order to handle foreign key constraints
        deleted_counts = {
            'conditional_logic': 0,
            'survey_responses': 0,
            'questions': 0,
            'question_options': 0,
            'survey_versions': 0
        }
        
        # 1. Delete conditional_logic records that reference this template
        try:
            conditional_logic_result = db.session.execute(
                text("DELETE FROM conditional_logic WHERE template_id = :template_id"),
                {"template_id": template_id}
            )
            deleted_counts['conditional_logic'] = conditional_logic_result.rowcount
            logger.info(f"Deleted {deleted_counts['conditional_logic']} conditional_logic records")
        except Exception as e:
            logger.warning(f"Error deleting conditional_logic records: {str(e)}")
        
        # 2. Delete survey responses
        survey_responses = SurveyResponse.query.filter_by(template_id=template_id).all()
        for response in survey_responses:
            db.session.delete(response)
        deleted_counts['survey_responses'] = len(survey_responses)
        
        # 3. Delete questions and their options
        questions = Question.query.filter_by(template_id=template_id).all()
        question_ids = [q.id for q in questions]
        
        if question_ids:
            # Delete question options first
            question_options = QuestionOption.query.filter(QuestionOption.question_id.in_(question_ids)).all()
            for option in question_options:
                db.session.delete(option)
            deleted_counts['question_options'] = len(question_options)
            
            # Then delete questions
            for question in questions:
                db.session.delete(question)
            deleted_counts['questions'] = len(questions)
        
        # 4. Delete survey versions
        survey_versions = SurveyVersion.query.filter_by(survey_id=template_id).all()
        for version in survey_versions:
            db.session.delete(version)
        deleted_counts['survey_versions'] = len(survey_versions)
        
        # 5. Finally delete the template itself
        db.session.delete(template)
        db.session.commit()
        
        logger.info(f"Successfully deleted template {template_id} and all associated records: {deleted_counts}")
        return jsonify({
            'deleted': True,
            'template_id': template_id,
            'deleted_counts': deleted_counts
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template {template_id}: {str(e)}")
        return jsonify({'error': f'Failed to delete template: {str(e)}'}), 500

@app.route('/api/templates/<int:template_id>/questions/<int:question_id>', methods=['DELETE'])
def delete_template_question(template_id, question_id):
    template = SurveyTemplate.query.get_or_404(template_id)
    questions = template.questions or []
    updated = [q for q in questions if q.get('id') != question_id]
    template.questions = updated
    db.session.commit()
    return jsonify({'deleted': True}), 200

@app.route('/api/templates/<int:template_id>/sections', methods=['GET'])
def get_template_sections(template_id):
    """Get sections for a template with their order"""
    template = SurveyTemplate.query.get_or_404(template_id)
    
    # Get sections from template.sections or derive from questions
    if template.sections:
        sections = template.sections
    else:
        # Derive sections from questions
        sections = {}
        for question in (template.questions or []):
            section_name = question.get('section', 'Uncategorized')
            if section_name not in sections:
                sections[section_name] = len(sections)
    
    # Convert to list format sorted by order
    sections_list = [{'name': name, 'order': order} for name, order in sections.items()]
    sections_list.sort(key=lambda x: x['order'])
    
    return jsonify(sections_list), 200

@app.route('/api/templates/<int:template_id>/sections', methods=['PUT'])
def update_template_sections(template_id):
    """Update section order for a template"""
    template = SurveyTemplate.query.get_or_404(template_id)
    data = request.get_json() or {}
    
    if 'sections' not in data:
        return jsonify({'error': 'sections field is required'}), 400
    
    # Convert list format back to dict format
    sections_dict = {}
    for i, section in enumerate(data['sections']):
        if isinstance(section, dict) and 'name' in section:
            sections_dict[section['name']] = i
        elif isinstance(section, str):
            sections_dict[section] = i
    
    template.sections = sections_dict
    db.session.commit()
    
    return jsonify({'updated': True}), 200

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
            'survey_code': user.survey_code,  # Include survey code for sharing with respondents
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
    """Initialize the database with the nine core question types only"""
    try:
        # Nine core question types data - no conditional logic
        question_types_data = [
            {
                'id': 1, 'name': 'short_text', 'display_name': 'Short Text',
                'category': 'Core Questions', 'description': 'Brief free-text responses and fill-in-the-blank fields',
                'config_schema': {'max_length': 255, 'placeholder': '', 'required': False}
            },
            {
                'id': 2, 'name': 'single_choice', 'display_name': 'Single Choice',
                'category': 'Core Questions', 'description': 'Radio button selection from predefined categorical options',
                'config_schema': {'options': [], 'required': False}
            },
            {
                'id': 3, 'name': 'yes_no', 'display_name': 'Yes/No',
                'category': 'Core Questions', 'description': 'Binary choice questions for clear decision points',
                'config_schema': {'yes_label': 'Yes', 'no_label': 'No', 'required': False}
            },
            {
                'id': 4, 'name': 'likert5', 'display_name': 'Five-Point Likert Scale',
                'category': 'Core Questions', 'description': 'Five-point scale from "A great deal" to "None"',
                'config_schema': {'scale_labels': {1: 'None', 2: 'A little', 3: 'A moderate amount', 4: 'A lot', 5: 'A great deal'}, 'required': False}
            },
            {
                'id': 5, 'name': 'multi_select', 'display_name': 'Multiple Select',
                'category': 'Core Questions', 'description': '"Select all that apply" checkbox questions',
                'config_schema': {'options': [], 'required': False}
            },
            {
                'id': 6, 'name': 'paragraph', 'display_name': 'Paragraph Text',
                'category': 'Core Questions', 'description': 'Open-ended narrative and essay responses',
                'config_schema': {'max_length': 2000, 'placeholder': '', 'required': False}
            },
            {
                'id': 7, 'name': 'numeric', 'display_name': 'Numeric Entry',
                'category': 'Core Questions', 'description': 'Absolute number input with validation',
                'config_schema': {'number_type': 'integer', 'min_value': None, 'max_value': None, 'required': False}
            },
            {
                'id': 8, 'name': 'percentage', 'display_name': 'Percentage Allocation',
                'category': 'Core Questions', 'description': 'Distribution and allocation percentage questions',
                'config_schema': {'items': [], 'total_percentage': 100, 'required': False}
            },
            {
                'id': 9, 'name': 'year_matrix', 'display_name': 'Year Matrix',
                'category': 'Core Questions', 'description': 'Row-by-year grid for temporal data collection',
                'config_schema': {'rows': [], 'start_year': 2024, 'end_year': 2029, 'required': False}
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
            'message': 'Core question types initialized successfully',
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
