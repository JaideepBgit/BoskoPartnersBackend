from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy import text
import json
from datetime import datetime
import logging
import traceback
import uuid
from sqlalchemy import event
from uuid import uuid4

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app and SQLAlchemy
app = Flask(__name__)

# Configure CORS to allow requests from the React frontend
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# Database configuration
DB_USER = 'root'
DB_PASSWORD = 'rootroot'
DB_HOST = 'localhost'
DB_NAME = 'boskopartnersdb'

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True  # Log all SQL queries
db = SQLAlchemy(app)

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
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other'), default='user')
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationship with Organization
    organization = db.relationship('Organization', backref=db.backref('users', lazy=True))
    
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
    answers = db.Column(JSON, nullable=True)
    status = db.Column(db.Enum('pending','in_progress','completed'), 
                       nullable=False, default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('surveys', lazy=True))

    def __repr__(self):
        return f'<Survey {self.survey_code} for User {self.user_id}>'

# Routes

@app.route('/')
def index():
    return "Hello, welcome to the Flask app!"

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
            "username": user.username,
            "email": user.email,
            "role": user.role
        }
    }), 200


@app.route('/api/users/register', methods=['POST'])
def register():
    data = request.get_json()
    new_user = User(
      username=data['username'],
      email   =data['email'],
      password=data['password'],
      role    ='user',
      organization_id=data['organization_id']
    )
    db.session.add(new_user)
    db.session.flush()   # so new_user.id is set

    new_survey = Survey(
      user_id    = new_user.id,
      survey_code= str(uuid4()),
      answers    = {}
    )
    db.session.add(new_survey)
    db.session.commit()
    
    return jsonify({ "message": "User + survey created", "user_id": new_user.id }), 201

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

    survey = Survey.query.filter_by(survey_code=code).first()
    if not survey:
        return jsonify({"error": "Invalid survey code"}), 404

    # Build whatever payload the frontend needs
    payload = {
        "id": survey.id,
        "survey_code": survey.survey_code,
        "user_id": survey.user_id,
        "status": survey.status,
        "answers": survey.answers or {}
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

if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
    app.run(debug=True)
