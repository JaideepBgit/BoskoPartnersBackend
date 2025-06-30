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
import boto3
from botocore.exceptions import ClientError
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Email configuration
def load_ses_credentials():
    """Load SES credentials from CSV file"""
    try:
        credentials_path = os.path.join(os.path.dirname(__file__), '..', 'ses-email-user_credentials.csv')
        if os.path.exists(credentials_path):
            with open(credentials_path, 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    return {
                        'username': row['User name'],
                        'password': row['Password']
                    }
        
        # Fallback to environment variables
        return {
            'username': os.getenv('SES_USERNAME'),
            'password': os.getenv('SES_PASSWORD')
        }
    except Exception as e:
        logger.error(f"Error loading SES credentials: {str(e)}")
        return None

# Initialize SES client
def get_ses_client():
    """Initialize and return SES client"""
    try:
        # Get AWS credentials from environment variables
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        
        logger.info(f"Initializing SES client with region: {aws_region}")
        logger.info(f"AWS Access Key ID present: {bool(aws_access_key_id)}")
        logger.info(f"AWS Secret Access Key present: {bool(aws_secret_access_key)}")
        
        if not aws_access_key_id or not aws_secret_access_key:
            logger.error("AWS credentials not found in environment variables")
            return None
        
        # Create SES client with explicit credentials
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        return session.client('ses')
    except Exception as e:
        logger.error(f"Error initializing SES client: {str(e)}")
        return None

def send_welcome_email_smtp(to_email, username, password, firstname=None):
    """Send welcome email using SMTP (alternative method)"""
    try:
        # Get SMTP credentials from environment
        smtp_username = os.getenv('SES_SMTP_USERNAME')
        smtp_password = os.getenv('SES_SMTP_PASSWORD')
        smtp_host = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
        smtp_port = int(os.getenv('SES_SMTP_PORT', '587'))
        source_email = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')
        
        if not smtp_username or not smtp_password:
            raise Exception("SMTP credentials not found in environment variables")
        
        # Email content
        subject = "Welcome to Saurara Platform"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        body_text = f"""{greeting},

Welcome to the Saurara Platform! We are excited to have you join our community.

Your account has been successfully created with the following details:

Username: {username}
Email: {to_email}
Password: {password}

You can access the platform at: www.saurara.org

Please keep this information secure and change your password after your first login for enhanced security.

If you have any questions or need assistance, please don't hesitate to contact our support team.

Best regards,
The Saurara Team"""

        body_html = f"""
        <html>
        <head></head>
        <body>
            <h2>Welcome to Saurara Platform!</h2>
            <p>{greeting},</p>
            
            <p>Welcome to the Saurara Platform! We are excited to have you join our community.</p>
            
            <p>Your account has been successfully created with the following details:</p>
            
            <ul>
                <li><strong>Username:</strong> {username}</li>
                <li><strong>Email:</strong> {to_email}</li>
                <li><strong>Password:</strong> {password}</li>
            </ul>
            
            <p>You can access the platform at: <a href="http://www.saurara.org">www.saurara.org</a></p>
            
            <p>Please keep this information secure and change your password after your first login for enhanced security.</p>
            
            <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
            
            <p>Best regards,<br>
            The Saurara Team</p>
        </body>
        </html>
        """
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = source_email
        msg['To'] = to_email
        
        # Create the plain-text and HTML version of your message
        text_part = MIMEText(body_text, 'plain')
        html_part = MIMEText(body_html, 'html')
        
        # Add HTML/plain-text parts to MIMEMultipart message
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send the email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(source_email, to_email, msg.as_string())
        
        logger.info(f"Welcome email sent successfully via SMTP to {to_email}")
        return {
            'success': True,
            'method': 'SMTP',
            'message': 'Email sent successfully via SMTP'
        }
        
    except Exception as e:
        logger.error(f"Error sending welcome email via SMTP: {str(e)}")
        return {
            'success': False,
            'error': f"SMTP email sending failed: {str(e)}"
        }

def send_welcome_email(to_email, username, password, firstname=None):
    """Send welcome email to new user (tries SES API first, falls back to SMTP)"""
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_welcome_email_smtp(to_email, username, password, firstname)
        
        # Email content
        subject = "Welcome to Saurara Platform"
        
        # Create personalized greeting
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        body_text = f"""{greeting},

Welcome to the Saurara Platform! We are excited to have you join our community.

Your account has been successfully created with the following details:

Username: {username}
Email: {to_email}
Password: {password}

You can access the platform at: www.saurara.org

Please keep this information secure and change your password after your first login for enhanced security.

If you have any questions or need assistance, please don't hesitate to contact our support team.

Best regards,
The Saurara Team"""

        body_html = f"""
        <html>
        <head></head>
        <body>
            <h2>Welcome to Saurara Platform!</h2>
            <p>{greeting},</p>
            
            <p>Welcome to the Saurara Platform! We are excited to have you join our community.</p>
            
            <p>Your account has been successfully created with the following details:</p>
            
            <ul>
                <li><strong>Username:</strong> {username}</li>
                <li><strong>Email:</strong> {to_email}</li>
                <li><strong>Password:</strong> {password}</li>
            </ul>
            
            <p>You can access the platform at: <a href="http://www.saurara.org">www.saurara.org</a></p>
            
            <p>Please keep this information secure and change your password after your first login for enhanced security.</p>
            
            <p>If you have any questions or need assistance, please don't hesitate to contact our support team.</p>
            
            <p>Best regards,<br>
            The Saurara Team</p>
        </body>
        </html>
        """
        
        # Get verified sender email from environment
        source_email = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')
        
        # Send email
        response = ses_client.send_email(
            Destination={
                'ToAddresses': [to_email],
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': 'UTF-8',
                        'Data': body_html,
                    },
                    'Text': {
                        'Charset': 'UTF-8',
                        'Data': body_text,
                    },
                },
                'Subject': {
                    'Charset': 'UTF-8',
                    'Data': subject,
                },
            },
            Source=source_email,  # Must be verified in SES
        )
        
        logger.info(f"Welcome email sent successfully via SES API to {to_email}. Message ID: {response['MessageId']}")
        return {
            'success': True,
            'method': 'SES_API',
            'message_id': response['MessageId'],
            'message': 'Email sent successfully via SES API'
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"SES API ClientError: {error_code} - {error_message}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_welcome_email_smtp(to_email, username, password, firstname)
    except Exception as e:
        logger.error(f"Error sending welcome email via SES API: {str(e)}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_welcome_email_smtp(to_email, username, password, firstname)

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
            ],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
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
DB_PASSWORD = 'jaideep'
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
class OrganizationType(db.Model):
    __tablename__ = 'organization_types'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<OrganizationType {self.type}>'

class GeoLocation(db.Model):
    __tablename__ = 'geo_locations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    which = db.Column(db.Enum('user', 'organization'), nullable=True)
    continent = db.Column(db.String(255), nullable=True)
    region = db.Column(db.String(255), nullable=True)
    province = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(255), nullable=True)
    town = db.Column(db.String(255), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(255), nullable=True)
    postal_code = db.Column(db.String(50), nullable=True)
    latitude = db.Column(db.Numeric(10, 8), nullable=False, server_default='0')
    longitude = db.Column(db.Numeric(11, 8), nullable=False, server_default='0')
    
    def __repr__(self):
        return f'<GeoLocation {self.id}>'

class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.Integer, db.ForeignKey('organization_types.id'), nullable=True)
    address = db.Column(db.Integer, db.ForeignKey('geo_locations.id'), nullable=True)
    primary_contact = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    secondary_contact = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    head = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    parent_organization = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    highest_level_of_education = db.Column(db.String(255), nullable=True)
    details = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    # Relationships
    organization_type = db.relationship('OrganizationType', foreign_keys=[type])
    geo_location = db.relationship('GeoLocation', foreign_keys=[address])
    primary_contact_user = db.relationship('User', foreign_keys=[primary_contact], post_update=True)
    secondary_contact_user = db.relationship('User', foreign_keys=[secondary_contact], post_update=True)
    head_user = db.relationship('User', foreign_keys=[head], post_update=True)
    parent = db.relationship('Organization', remote_side=[id], foreign_keys=[parent_organization])
    
    def __repr__(self):
        return f'<Organization {self.name}>'

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other', 'primary_contact', 'secondary_contact', 'head'), default='user')
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    survey_code = db.Column(db.String(36), nullable=True)  # UUID as string for user surveys
    geo_location_id = db.Column(db.Integer, db.ForeignKey('geo_locations.id'), nullable=True)
    phone = db.Column(db.String(20), nullable=True)  # Added for contact information
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    organization = db.relationship('Organization', foreign_keys=[organization_id], backref=db.backref('users', lazy=True))
    geo_location = db.relationship('GeoLocation', foreign_keys=[geo_location_id])
    
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
    user = db.relationship('User', backref=db.backref('user_details', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_details', lazy=True))
    
    def __repr__(self):
        return f'<UserDetails user_id={self.user_id}>'

class SurveyTemplateVersion(db.Model):
    __tablename__ = 'survey_template_versions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
    # Relationships
    organization = db.relationship('Organization', backref=db.backref('template_versions', lazy=True))
    
    def __repr__(self):
        return f'<SurveyTemplateVersion {self.name}>'    

class SurveyTemplate(db.Model):
    __tablename__ = 'survey_templates'
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('survey_template_versions.id'), nullable=False)
    survey_code = db.Column(db.String(100), nullable=False, unique=True)
    questions = db.Column(JSON, nullable=False)
    sections = db.Column(JSON, nullable=True)  # Added sections column
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    version = db.relationship('SurveyTemplateVersion', backref=db.backref('templates', lazy=True))
    
    def __repr__(self):
        return f'<SurveyTemplate {self.survey_code}>'    

"""
# redefined
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
"""

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
    display_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    config_schema = db.Column(JSON, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    
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

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<Role {self.name}>'

class UserOrganizationRole(db.Model):
    __tablename__ = 'user_organization_roles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)  # Changed from role_type to role_id
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('organization_roles', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_roles', lazy=True))
    role = db.relationship('Role', backref=db.backref('user_organization_assignments', lazy=True))
    
    # Ensure unique combination of user, organization, and role
    __table_args__ = (UniqueConstraint('user_id', 'organization_id', 'role_id'),)

    def __repr__(self):
        return f'<UserOrganizationRole user_id={self.user_id} org_id={self.organization_id} role_id={self.role_id}>'

"""
FIXED - Survey model with unique backref name to avoid conflicts:
1. Changed backref from 'templates' to 'surveys' to avoid collision with SurveyTemplate model
2. This model appears to be for survey instances/templates, different from SurveyResponse
"""
class Survey(db.Model):
    __tablename__ = 'surveys'
    id = db.Column(db.Integer, primary_key=True)
    # version_id = db.Column(db.Integer, db.ForeignKey('survey_template_versions.id'), nullable=False)  # COMMENTED OUT - column doesn't exist in DB
    survey_code = db.Column(db.String(100), nullable=False, unique=True)
    questions = db.Column(JSON, nullable=False)
    sections = db.Column(JSON, nullable=True)  # Store section names and their order
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships - COMMENTED OUT because version_id column doesn't exist in actual database
    # version = db.relationship('SurveyTemplateVersion', backref=db.backref('surveys', lazy=True))
    
    def __repr__(self):
        return f'<Survey {self.survey_code}>'    

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
    
    """
    FIXED - Removed duplicate __repr__ method that was causing Python syntax issues
    """
    def __repr__(self):
        return f'<SurveyResponse {self.id} for template {self.template_id}>'



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

# To initialize the database tables (run once)
@app.cli.command('init-db')
def init_db():
    db.create_all()
    print("Database tables created successfully!")

# Survey Template API Endpoints
@app.route('/api/template-versions', methods=['GET'])
def get_template_versions():
    organization_id = request.args.get('organization_id')
    
    if organization_id:
        versions = SurveyTemplateVersion.query.filter_by(organization_id=organization_id).all()
    else:
        versions = SurveyTemplateVersion.query.all()
    
    result = []
    for v in versions:
        try:
            result.append({
                "id": v.id, 
                "name": v.name, 
                "description": v.description, 
                "organization_id": v.organization_id,
                "organization_name": v.organization.name if v.organization else None,
                "created_at": v.created_at
            })
        except Exception as e:
            logger.warning(f"Error processing template version {v.id}: {str(e)}")
            # Include version with minimal data if there's an issue
            result.append({
                "id": v.id, 
                "name": v.name, 
                "description": v.description, 
                "organization_id": getattr(v, 'organization_id', None),
                "organization_name": None,
                "created_at": v.created_at
            })
    
    return jsonify(result), 200

@app.route('/api/template-versions', methods=['POST'])
def add_template_version():
    data = request.get_json() or {}
    if 'name' not in data:
        return jsonify({'error': 'name required'}), 400
    if 'organization_id' not in data:
        return jsonify({'error': 'organization_id required'}), 400
    
    # Verify organization exists
    organization = Organization.query.get(data['organization_id'])
    if not organization:
        return jsonify({'error': 'Organization not found'}), 404
    
    version = SurveyTemplateVersion(
        name=data['name'],
        description=data.get('description'),
        organization_id=data['organization_id']
    )
    db.session.add(version)
    db.session.commit()
    return jsonify({
        'id': version.id, 
        'name': version.name, 
        'description': version.description,
        'organization_id': version.organization_id,
        'organization_name': version.organization.name
    }), 201

@app.route('/api/template-versions/<int:version_id>', methods=['DELETE'])
def delete_template_version(version_id):
    """Delete a template version"""
    try:
        version = SurveyTemplateVersion.query.get_or_404(version_id)
        
        # Simply delete the template version
        db.session.delete(version)
        db.session.commit()
        
        logger.info(f"Successfully deleted template version {version_id}")
        return jsonify({
            'deleted': True, 
            'version_id': version_id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting template version {version_id}: {str(e)}")
        return jsonify({'error': f'Failed to delete template version: {str(e)}'}), 500

@app.route('/api/templates', methods=['GET'])
def get_templates():
    organization_id = request.args.get('organization_id', type=int)
    query = SurveyTemplate.query
    if organization_id:
        # Join with SurveyTemplateVersion to filter by organization_id
        query = query.join(SurveyTemplateVersion).filter(SurveyTemplateVersion.organization_id == organization_id)
    templates = query.all()
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
    required_keys = ['version_id', 'questions']
    if not all(k in data for k in required_keys):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Generate unique survey code if not provided or if it already exists
    survey_code = data.get('survey_code', '')
    if not survey_code:
        # Generate a default survey code
        survey_code = f"template_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Check for duplicate survey_code and generate a unique one if needed
    counter = 1
    original_survey_code = survey_code
    while True:
        existing = SurveyTemplate.query.filter_by(survey_code=survey_code).first()
        if not existing:
            break
        survey_code = f"{original_survey_code}_{counter}"
        counter += 1
        
    template = SurveyTemplate(
        version_id=data['version_id'],
        survey_code=survey_code,
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


@app.route('/api/templates/<int:template_id>/', methods=['PUT'])
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
        updated = True
    
    if updated:
        db.session.commit()
        logger.info(f"Successfully updated template {template_id}")
        return jsonify({'updated': True}), 200
    
    return jsonify({'error': 'No valid fields to update'}), 400

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    #Delete a template and all its associated records
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


"""
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

"""
# Organization Types API Endpoints
@app.route('/api/organization-types', methods=['GET'])
def get_organization_types():
    org_types = OrganizationType.query.all()
    return jsonify([{
        'id': ot.id,
        'type': ot.type
    } for ot in org_types]), 200

@app.route('/api/organization-types', methods=['POST'])
def add_organization_type():
    try:
        data = request.get_json()
        logger.info(f"Adding organization type with data: {data}")
        
        if 'type' not in data:
            return jsonify({'error': 'type is required'}), 400
        
        type_name = data['type'].strip().lower()  # Normalize the input
        
        # Check if the organization type already exists
        existing_type = OrganizationType.query.filter_by(type=type_name).first()
        if existing_type:
            logger.info(f"Organization type '{type_name}' already exists with ID: {existing_type.id}")
            return jsonify({
                'message': 'Organization type already exists',
                'id': existing_type.id,
                'type': existing_type.type
            }), 409  # 409 Conflict status for existing resource
        
        # Create new organization type
        org_type = OrganizationType(type=type_name)
        db.session.add(org_type)
        db.session.commit()
        
        logger.info(f"Successfully created organization type '{type_name}' with ID: {org_type.id}")
        
        return jsonify({
            'message': 'Organization type created successfully',
            'id': org_type.id,
            'type': org_type.type
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding organization type: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to add organization type: {str(e)}'}), 500

@app.route('/api/organization-types/initialize', methods=['POST'])
def initialize_organization_types():
    """Initialize organization types with the required types"""
    try:
        # Clear existing types
        OrganizationType.query.delete()
        
        # Add the required types
        types = ['church', 'school', 'other', 'institution', 'non-formal organization']
        for type_name in types:
            org_type = OrganizationType(type=type_name)
            db.session.add(org_type)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Organization types initialized successfully',
            'types': types
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing organization types: {str(e)}")
        return jsonify({'error': 'Failed to initialize organization types'}), 500

# Geo Location API Endpoints
@app.route('/api/geo-locations', methods=['GET'])
def get_geo_locations():
    geo_locations = GeoLocation.query.all()
    return jsonify([{
        'id': gl.id,
        'continent': gl.continent,
        'region': gl.region,
        'country': gl.country,
        'province': gl.province,
        'city': gl.city,
        'town': gl.town,
        'address_line1': gl.address_line1,
        'address_line2': gl.address_line2,
        'postal_code': gl.postal_code,
        'which': gl.which
    } for gl in geo_locations]), 200

@app.route('/api/geo-locations', methods=['POST'])
def add_geo_location():
    data = request.get_json()
    
    geo_location = GeoLocation(
        user_id=data.get('user_id'),
        organization_id=data.get('organization_id'),
        which=data.get('which'),
        continent=data.get('continent'),
        region=data.get('region'),
        country=data.get('country'),
        province=data.get('province'),
        city=data.get('city'),
        town=data.get('town'),
        address_line1=data.get('address_line1'),
        address_line2=data.get('address_line2'),
        postal_code=data.get('postal_code'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude')
    )
    
    db.session.add(geo_location)
    db.session.commit()
    
    return jsonify({
        'id': geo_location.id,
        'message': 'Geo location added successfully'
    }), 201

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
        'organization_type': {
            'id': org.organization_type.id,
            'type': org.organization_type.type
        } if org.organization_type else None,
        'geo_location': {
            'id': org.geo_location.id,
            'continent': org.geo_location.continent,
            'region': org.geo_location.region,
            'country': org.geo_location.country,
            'province': org.geo_location.province,
            'city': org.geo_location.city,
            'town': org.geo_location.town,
            'address_line1': org.geo_location.address_line1,
            'address_line2': org.geo_location.address_line2,
            'postal_code': org.geo_location.postal_code
        } if org.geo_location else None,
        'primary_contact': {
            'id': org.primary_contact.id,
            'firstname': org.primary_contact.firstname,
            'lastname': org.primary_contact.lastname,
            'email': org.primary_contact.email,
            'phone': org.primary_contact.phone
        } if org.primary_contact else None,
        'secondary_contact': {
            'id': org.secondary_contact.id,
            'firstname': org.secondary_contact.firstname,
            'lastname': org.secondary_contact.lastname,
            'email': org.secondary_contact.email,
            'phone': org.secondary_contact.phone
        } if org.secondary_contact else None,
        'lead': {
            'id': org.head_user.id,
            'firstname': org.head_user.firstname,
            'lastname': org.head_user.lastname,
            'email': org.head_user.email,
            'phone': org.head_user.phone
        } if org.head_user else None,
        'website': org.website,
        'denomination_affiliation': org.details.get('denomination_affiliation') if org.details else None,
        'accreditation_status_or_body': org.details.get('accreditation_status_or_body') if org.details else None,
        'highest_level_of_education': org.highest_level_of_education,
        'affiliation_validation': org.details.get('affiliation_validation') if org.details else None,
        'umbrella_association_membership': org.details.get('umbrella_association_membership') if org.details else None,
        'misc': org.details,
        'created_at': org.created_at
    }
    return jsonify(result)

@app.route('/api/organizations', methods=['POST'])
def add_organization():
    try:
        data = request.get_json()
        logger.info(f"Adding new organization with data: {data}")
        
        # Handle geo location if provided
        geo_location_id = None
        if 'geo_location' in data and data['geo_location']:
            geo_data = data['geo_location']
            
            # Ensure numeric values for coordinates
            try:
                latitude = float(geo_data.get('latitude', 0))
                longitude = float(geo_data.get('longitude', 0))
            except (ValueError, TypeError):
                latitude = 0
                longitude = 0
            
            geo_location = GeoLocation(
                which='organization',
                continent=geo_data.get('continent'),
                region=geo_data.get('region'),
                country=geo_data.get('country'),
                province=geo_data.get('province'),
                city=geo_data.get('city'),
                town=geo_data.get('town'),
                address_line1=geo_data.get('address_line1'),
                address_line2=geo_data.get('address_line2'),
                postal_code=geo_data.get('postal_code'),
                latitude=latitude,
                longitude=longitude
            )
            db.session.add(geo_location)
            db.session.flush()  # Get the ID
            geo_location_id = geo_location.id
            logger.info(f"Created geo location with ID: {geo_location_id}")
        
        # Handle contacts (primary, secondary, lead)
        primary_contact_id = None
        secondary_contact_id = None
        lead_id = None
        
        # Handle existing users assigned as contacts or head
        existing_primary_contact_id = data.get('primary_contact_id')
        existing_secondary_contact_id = data.get('secondary_contact_id')
        existing_head_id = data.get('head_id')
        
        # Create primary contact if provided (new user)
        if 'primary_contact' in data and data['primary_contact']:
            contact_data = data['primary_contact']
            
            # Check if user already exists by email
            existing_user = User.query.filter_by(email=contact_data['email']).first()
            if existing_user:
                logger.info(f"User with email {contact_data['email']} already exists, using existing user ID: {existing_user.id}")
                primary_contact_id = existing_user.id
            else:
                # Generate unique username
                base_username = contact_data.get('username', f"primary_{data['name'].lower().replace(' ', '_')}")
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                primary_contact = User(
                    username=username,
                    email=contact_data['email'],
                    password=contact_data.get('password', 'defaultpass123'),  # Should be hashed in production
                    role='primary_contact',
                    firstname=contact_data.get('firstname'),
                    lastname=contact_data.get('lastname'),
                    phone=contact_data.get('phone')
                )
                db.session.add(primary_contact)
                db.session.flush()
                primary_contact_id = primary_contact.id
                logger.info(f"Created primary contact with ID: {primary_contact_id} and username: {username}")
        
        # Create secondary contact if provided (new user)
        if 'secondary_contact' in data and data['secondary_contact']:
            contact_data = data['secondary_contact']
            
            # Check if user already exists by email
            existing_user = User.query.filter_by(email=contact_data['email']).first()
            if existing_user:
                logger.info(f"User with email {contact_data['email']} already exists, using existing user ID: {existing_user.id}")
                secondary_contact_id = existing_user.id
            else:
                # Generate unique username
                base_username = contact_data.get('username', f"secondary_{data['name'].lower().replace(' ', '_')}")
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                secondary_contact = User(
                    username=username,
                    email=contact_data['email'],
                    password=contact_data.get('password', 'defaultpass123'),  # Should be hashed in production
                    role='secondary_contact',
                    firstname=contact_data.get('firstname'),
                    lastname=contact_data.get('lastname'),
                    phone=contact_data.get('phone')
                )
                db.session.add(secondary_contact)
                db.session.flush()
                secondary_contact_id = secondary_contact.id
                logger.info(f"Created secondary contact with ID: {secondary_contact_id} and username: {username}")
        
        # Create lead if provided (new user)
        if 'lead' in data and data['lead']:
            lead_data = data['lead']
            
            # Check if user already exists by email
            existing_user = User.query.filter_by(email=lead_data['email']).first()
            if existing_user:
                logger.info(f"User with email {lead_data['email']} already exists, using existing user ID: {existing_user.id}")
                lead_id = existing_user.id
            else:
                # Generate unique username
                base_username = lead_data.get('username', f"lead_{data['name'].lower().replace(' ', '_')}")
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                lead = User(
                    username=username,
                    email=lead_data['email'],
                    password=lead_data.get('password', 'defaultpass123'),  # Should be hashed in production
                    role='head',  # Head/Lead role
                    firstname=lead_data.get('firstname'),
                    lastname=lead_data.get('lastname'),
                    phone=lead_data.get('phone')
                )
                db.session.add(lead)
                db.session.flush()
                lead_id = lead.id
                logger.info(f"Created lead with ID: {lead_id} and username: {username}")
        
        # Create the organization
        new_org = Organization(
            name=data['name'],
            type=data.get('organization_type_id'),  # Maps to new 'type' column
            address=geo_location_id,  # Maps to new 'address' column
            primary_contact=primary_contact_id or existing_primary_contact_id,  # Maps to new 'primary_contact' column
            secondary_contact=secondary_contact_id or existing_secondary_contact_id,  # Maps to new 'secondary_contact' column
            head=lead_id or existing_head_id,  # Maps to new 'head' column
            website=data.get('website'),
            highest_level_of_education=data.get('highest_level_of_education'),
            details=data.get('misc')  # Maps to new 'details' column
        )
        
        db.session.add(new_org)
        db.session.flush()  # Get the organization ID
        
        # Update geo location organization_id if it was created
        if geo_location_id:
            geo_location.organization_id = new_org.id
        
        # Update contacts organization_id for newly created users only
        if primary_contact_id and 'primary_contact' in data:
            # Find the user and update their organization_id
            primary_user = User.query.get(primary_contact_id)
            if primary_user:
                primary_user.organization_id = new_org.id
        if secondary_contact_id and 'secondary_contact' in data:
            # Find the user and update their organization_id
            secondary_user = User.query.get(secondary_contact_id)
            if secondary_user:
                secondary_user.organization_id = new_org.id
        if lead_id and 'lead' in data:
            # Find the user and update their organization_id
            lead_user = User.query.get(lead_id)
            if lead_user:
                lead_user.organization_id = new_org.id
        
        # Create user_organization_roles entries for assigned contacts
        def add_user_organization_role(user_id, role_name):
            if user_id:
                role = Role.query.filter_by(name=role_name).first()
                if role:
                    # Check if role assignment already exists
                    existing_role = UserOrganizationRole.query.filter_by(
                        user_id=user_id,
                        organization_id=new_org.id,
                        role_id=role.id
                    ).first()
                    
                    if not existing_role:
                        user_org_role = UserOrganizationRole(
                            user_id=user_id,
                            organization_id=new_org.id,
                            role_id=role.id
                        )
                        db.session.add(user_org_role)
                        logger.info(f"Added {role_name} role for user {user_id} in organization {new_org.id}")
                else:
                    logger.warning(f"Role {role_name} not found in database")
        
        # Add organizational roles for all contacts (both new and existing)
        final_primary_id = primary_contact_id or existing_primary_contact_id
        final_secondary_id = secondary_contact_id or existing_secondary_contact_id
        final_head_id = lead_id or existing_head_id
        
        add_user_organization_role(final_primary_id, 'primary_contact')
        add_user_organization_role(final_secondary_id, 'secondary_contact')
        add_user_organization_role(final_head_id, 'head')
        
        # Create a default template version for the organization
        default_template_version = SurveyTemplateVersion(
            name=f"{new_org.name} - Default Survey Template",
            description=f"Default survey template version for {new_org.name}",
            organization_id=new_org.id
        )
        db.session.add(default_template_version)
        
        db.session.commit()
        logger.info(f"Successfully created organization with ID: {new_org.id} and default template version")
        
        return jsonify({
            'message': 'Organization added successfully',
            'id': new_org.id,
            'default_template_version_id': default_template_version.id
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding organization: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to add organization: {str(e)}'}), 500

@app.route('/api/organizations/<int:org_id>', methods=['PUT'])
def update_organization(org_id):
    try:
        org = Organization.query.get_or_404(org_id)
        data = request.get_json()
        logger.info(f"Updating organization {org_id} with data: {data}")
        
        # Update basic organization fields
        if 'name' in data:
            org.name = data['name']
        if 'organization_type_id' in data:
            org.type = data['organization_type_id']  # Maps to new 'type' column
        if 'website' in data:
            org.website = data['website']
        if 'highest_level_of_education' in data:
            org.highest_level_of_education = data['highest_level_of_education']
        if 'misc' in data:
            org.details = data['misc']  # Maps to new 'details' column
        
        # Update geo location if provided
        if 'geo_location' in data and data['geo_location']:
            geo_data = data['geo_location']
            if org.address:  # Maps to new 'address' column
                # Update existing geo location
                geo_location = GeoLocation.query.get(org.address)
                geo_location.continent = geo_data.get('continent', geo_location.continent)
                geo_location.region = geo_data.get('region', geo_location.region)
                geo_location.country = geo_data.get('country', geo_location.country)
                geo_location.province = geo_data.get('province', geo_location.province)
                geo_location.city = geo_data.get('city', geo_location.city)
                geo_location.town = geo_data.get('town', geo_location.town)
                geo_location.address_line1 = geo_data.get('address_line1', geo_location.address_line1)
                geo_location.address_line2 = geo_data.get('address_line2', geo_location.address_line2)
                geo_location.postal_code = geo_data.get('postal_code', geo_location.postal_code)
                geo_location.latitude = geo_data.get('latitude', geo_location.latitude)
                geo_location.longitude = geo_data.get('longitude', geo_location.longitude)
            else:
                # Create new geo location
                geo_location = GeoLocation(
                    organization_id=org_id,
                    which='organization',
                    continent=geo_data.get('continent'),
                    region=geo_data.get('region'),
                    country=geo_data.get('country'),
                    province=geo_data.get('province'),
                    city=geo_data.get('city'),
                    town=geo_data.get('town'),
                    address_line1=geo_data.get('address_line1'),
                    address_line2=geo_data.get('address_line2'),
                    postal_code=geo_data.get('postal_code'),
                    latitude=geo_data.get('latitude'),
                    longitude=geo_data.get('longitude')
                )
                db.session.add(geo_location)
                db.session.flush()
                org.address = geo_location.id  # Maps to new 'address' column
        
        # Note: Contact updates would be more complex and should be handled separately
        # to avoid complications with user management
        
        db.session.commit()
        logger.info(f"Successfully updated organization {org_id}")
        
        return jsonify({'message': 'Organization updated successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error updating organization: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to update organization: {str(e)}'}), 500

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


# Organization Contacts API Endpoints
@app.route('/api/organizations/<int:org_id>/contacts', methods=['PUT'])
def update_organization_contacts(org_id):
    #Update organization contacts (primary, secondary, lead)
    try:
        org = Organization.query.get_or_404(org_id)
        data = request.get_json()
        logger.info(f"Updating contacts for organization {org_id}")
        
        # Update primary contact
        if 'primary_contact' in data:
            contact_data = data['primary_contact']
            if contact_data and contact_data.get('email'):
                if org.primary_contact:  # Maps to new 'primary_contact' column
                    # Update existing contact
                    contact = User.query.get(org.primary_contact)
                    contact.firstname = contact_data.get('firstname', contact.firstname)
                    contact.lastname = contact_data.get('lastname', contact.lastname)
                    contact.email = contact_data.get('email', contact.email)
                    contact.phone = contact_data.get('phone', contact.phone)
                else:
                    # Create new contact
                    contact = User(
                        username=contact_data.get('username', f"primary_{org.name.lower().replace(' ', '_')}_{org_id}"),
                        email=contact_data['email'],
                        password=contact_data.get('password', 'defaultpass123'),
                        role='primary_contact',
                        firstname=contact_data.get('firstname'),
                        lastname=contact_data.get('lastname'),
                        phone=contact_data.get('phone'),
                        organization_id=org_id
                    )
                    db.session.add(contact)
                    db.session.flush()
                    org.primary_contact = contact.id  # Maps to new 'primary_contact' column
            elif org.primary_contact:
                # Remove primary contact if data is empty/null
                org.primary_contact = None
        
        # Update secondary contact
        if 'secondary_contact' in data:
            contact_data = data['secondary_contact']
            if contact_data and contact_data.get('email'):
                if org.secondary_contact:  # Maps to new 'secondary_contact' column
                    # Update existing contact
                    contact = User.query.get(org.secondary_contact)
                    contact.firstname = contact_data.get('firstname', contact.firstname)
                    contact.lastname = contact_data.get('lastname', contact.lastname)
                    contact.email = contact_data.get('email', contact.email)
                    contact.phone = contact_data.get('phone', contact.phone)
                else:
                    # Create new contact
                    contact = User(
                        username=contact_data.get('username', f"secondary_{org.name.lower().replace(' ', '_')}_{org_id}"),
                        email=contact_data['email'],
                        password=contact_data.get('password', 'defaultpass123'),
                        role='secondary_contact',
                        firstname=contact_data.get('firstname'),
                        lastname=contact_data.get('lastname'),
                        phone=contact_data.get('phone'),
                        organization_id=org_id
                    )
                    db.session.add(contact)
                    db.session.flush()
                    org.secondary_contact = contact.id  # Maps to new 'secondary_contact' column
            elif org.secondary_contact:
                # Remove secondary contact if data is empty/null
                org.secondary_contact = None
        
        # Update lead/head
        if 'lead' in data:
            lead_data = data['lead']
            if lead_data and lead_data.get('email'):
                if org.head:  # Maps to new 'head' column
                    # Update existing lead
                    lead = User.query.get(org.head)
                    lead.firstname = lead_data.get('firstname', lead.firstname)
                    lead.lastname = lead_data.get('lastname', lead.lastname)
                    lead.email = lead_data.get('email', lead.email)
                    lead.phone = lead_data.get('phone', lead.phone)
                else:
                    # Create new lead
                    lead = User(
                        username=lead_data.get('username', f"lead_{org.name.lower().replace(' ', '_')}_{org_id}"),
                        email=lead_data['email'],
                        password=lead_data.get('password', 'defaultpass123'),
                        role='other',
                        firstname=lead_data.get('firstname'),
                        lastname=lead_data.get('lastname'),
                        phone=lead_data.get('phone'),
                        organization_id=org_id
                    )
                    db.session.add(lead)
                    db.session.flush()
                    org.head = lead.id  # Maps to new 'head' column
            elif org.head:
                # Remove lead if data is empty/null
                org.head = None
        
        db.session.commit()
        logger.info(f"Successfully updated contacts for organization {org_id}")
        
        return jsonify({'message': 'Organization contacts updated successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error updating organization contacts: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to update organization contacts: {str(e)}'}), 500

# User Organizational Roles API Endpoints
@app.route('/api/user-organizational-roles', methods=['POST'])
def add_user_organizational_role():
    #Add a role for a user within an organization
    try:
        data = request.get_json()
        logger.info(f"Adding user organizational role with data: {data}")
        
        required_fields = ['user_id', 'organization_id', 'role_name']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Check if user exists
        user = User.query.get(data['user_id'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if organization exists
        org = Organization.query.get(data['organization_id'])
        if not org:
            return jsonify({'error': 'Organization not found'}), 404
        
        # Find or create the role
        role_name = data['role_name'].strip().lower()
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            # Create new role if it doesn't exist
            role = Role(
                name=role_name,
                description=f'Role: {role_name}'
            )
            db.session.add(role)
            db.session.flush()  # Get the role ID
            logger.info(f"Created new role '{role_name}' with ID: {role.id}")
        
        # Check if this role already exists for this user and organization
        existing_role = UserOrganizationRole.query.filter_by(
            user_id=data['user_id'],
            organization_id=data['organization_id'],
            role_id=role.id
        ).first()
        
        if existing_role:
            return jsonify({
                'message': 'User already has this role in the organization',
                'id': existing_role.id
            }), 409
        
        # Create new user organizational role
        user_org_role = UserOrganizationRole(
            user_id=data['user_id'],
            organization_id=data['organization_id'],
            role_id=role.id
        )
        
        db.session.add(user_org_role)
        db.session.commit()
        
        logger.info(f"Successfully created user organizational role with ID: {user_org_role.id}")
        
        return jsonify({
            'message': 'User organizational role created successfully',
            'id': user_org_role.id,
            'role_name': role.name
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding user organizational role: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to add user organizational role: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/organizational-roles', methods=['GET'])
def get_user_organizational_roles(user_id):
    #Get all organizational roles for a specific user
    try:
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get all organizational roles for this user
        user_org_roles = UserOrganizationRole.query.filter_by(user_id=user_id).all()
        
        result = []
        for user_role in user_org_roles:
            result.append({
                'id': user_role.id,
                'organization_id': user_role.organization_id,
                'role_type': user_role.role.name if user_role.role else None,  # Changed to get role name from Role table
                'role_id': user_role.role_id,
                'organization_name': user_role.organization.name if user_role.organization else None,
                'created_at': user_role.created_at.isoformat() if user_role.created_at else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error fetching user organizational roles: {str(e)}")
        return jsonify({'error': f'Failed to fetch user organizational roles: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/organizational-roles', methods=['PUT'])
def update_user_organizational_roles(user_id):
    #Update all organizational roles for a specific user
    try:
        data = request.get_json()
        logger.info(f"Updating organizational roles for user {user_id} with data: {data}")
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Remove all existing organizational roles for this user
        UserOrganizationRole.query.filter_by(user_id=user_id).delete()
        
        # Add new roles if provided
        if 'roles' in data and data['roles']:
            for role_data in data['roles']:
                if isinstance(role_data, dict) and 'organization_id' in role_data and 'role_type' in role_data:
                    # Verify organization exists
                    org = Organization.query.get(role_data['organization_id'])
                    if not org:
                        logger.warning(f"Organization {role_data['organization_id']} not found, skipping role")
                        continue
                    
                    # Find or create the role
                    role_name = role_data['role_type'].strip().lower()
                    role = Role.query.filter_by(name=role_name).first()
                    if not role:
                        # Create new role if it doesn't exist
                        role = Role(
                            name=role_name,
                            description=f'Role: {role_name}'
                        )
                        db.session.add(role)
                        db.session.flush()  # Get the role ID
                        logger.info(f"Created new role '{role_name}' with ID: {role.id}")
                    
                    # Create user organizational role
                    user_org_role = UserOrganizationRole(
                        user_id=user_id,
                        organization_id=role_data['organization_id'],
                        role_id=role.id
                    )
                    db.session.add(user_org_role)
        
        db.session.commit()
        logger.info(f"Successfully updated organizational roles for user {user_id}")
        
        return jsonify({'message': 'User organizational roles updated successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error updating user organizational roles: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to update user organizational roles: {str(e)}'}), 500

# Redefined
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
    
    if 'organization_id' in data:
        # Verify organization exists
        organization = Organization.query.get(data['organization_id'])
        if not organization:
            return jsonify({'error': 'Organization not found'}), 404
        version.organization_id = data['organization_id']
        updated = True
    
    if updated:
        db.session.commit()
        return jsonify({
            'id': version.id,
            'name': version.name,
            'description': version.description,
            'organization_id': version.organization_id,
            'organization_name': version.organization.name if version.organization else None,
            'updated': True
        }), 200
    
    return jsonify({'error': 'No valid fields to update'}), 400



@app.route('/api/templates/<int:template_id>/sections', methods=['GET'])
def get_template_sections(template_id):
    #Get sections for a template with their order
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
    #Update section order for a template
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
    if 'phone' in data:
        user.phone = data['phone']
    if 'organization_id' in data:
        user.organization_id = data['organization_id']
    
    # Update geo location if provided
    if 'geo_location' in data and data['geo_location']:
        geo_data = data['geo_location']
        if user.geo_location_id:
            # Update existing geo location
            geo_location = GeoLocation.query.get(user.geo_location_id)
            geo_location.continent = geo_data.get('continent', geo_location.continent)
            geo_location.region = geo_data.get('region', geo_location.region)
            geo_location.country = geo_data.get('country', geo_location.country)
            geo_location.province = geo_data.get('province', geo_location.province)
            geo_location.city = geo_data.get('city', geo_location.city)
            geo_location.town = geo_data.get('town', geo_location.town)
            geo_location.address_line1 = geo_data.get('address_line1', geo_location.address_line1)
            geo_location.address_line2 = geo_data.get('address_line2', geo_location.address_line2)
            geo_location.postal_code = geo_data.get('postal_code', geo_location.postal_code)
            geo_location.latitude = geo_data.get('latitude', geo_location.latitude)
            geo_location.longitude = geo_data.get('longitude', geo_location.longitude)
        else:
            # Create new geo location
            geo_location = GeoLocation(
                user_id=user_id,
                which='user',
                continent=geo_data.get('continent'),
                region=geo_data.get('region'),
                country=geo_data.get('country'),
                province=geo_data.get('province'),
                city=geo_data.get('city'),
                town=geo_data.get('town'),
                address_line1=geo_data.get('address_line1'),
                address_line2=geo_data.get('address_line2'),
                postal_code=geo_data.get('postal_code'),
                latitude=geo_data.get('latitude'),
                longitude=geo_data.get('longitude')
            )
            db.session.add(geo_location)
            db.session.flush()
            user.geo_location_id = geo_location.id
    
    # Handle organizational roles if provided
    if 'roles' in data:
        # Remove existing roles for this user
        UserOrganizationRole.query.filter_by(user_id=user_id).delete()
        
        # Add new roles
        if data['roles']:
            for role_data in data['roles']:
                if isinstance(role_data, dict) and 'organization_id' in role_data and 'role_type' in role_data:
                    user_org_role = UserOrganizationRole(
                        user_id=user_id,
                        organization_id=role_data['organization_id'],
                        role_type=role_data['role_type']
                    )
                    db.session.add(user_org_role)
    
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
            'phone': user.phone,
            'organization_id': user.organization_id,
            'geo_location': {
                'id': user.geo_location.id,
                'continent': user.geo_location.continent,
                'region': user.geo_location.region,
                'country': user.geo_location.country,
                'province': user.geo_location.province,
                'city': user.geo_location.city,
                'town': user.geo_location.town,
                'address_line1': user.geo_location.address_line1,
                'address_line2': user.geo_location.address_line2,
                'postal_code': user.geo_location.postal_code
            } if user.geo_location else None,
            'survey_code': user.survey_code,  # Include survey code for sharing with respondents
            'organization': {
                'id': user.organization.id,
                'name': user.organization.name,
                'organization_type': {
                    'id': user.organization.organization_type.id,
                    'type': user.organization.organization_type.type
                } if user.organization.organization_type else None,
                'geo_location': {
                    'id': user.organization.geo_location.id,
                    'continent': user.organization.geo_location.continent,
                    'region': user.organization.geo_location.region,
                    'country': user.organization.geo_location.country,
                    'province': user.organization.geo_location.province,
                    'city': user.organization.geo_location.city,
                    'town': user.organization.geo_location.town,
                    'address_line1': user.organization.geo_location.address_line1,
                    'address_line2': user.organization.geo_location.address_line2,
                    'postal_code': user.organization.geo_location.postal_code
                } if user.organization.geo_location else None,
                'website': user.organization.website,
                'denomination_affiliation': user.organization.details.get('denomination_affiliation') if user.organization.details else None,
                'accreditation_status_or_body': user.organization.details.get('accreditation_status_or_body') if user.organization.details else None,
                'highest_level_of_education': user.organization.highest_level_of_education,
                'affiliation_validation': user.organization.details.get('affiliation_validation') if user.organization.details else None,
                'umbrella_association_membership': user.organization.details.get('umbrella_association_membership') if user.organization.details else None
            } if user.organization else None
        }
        result.append(user_data)
    
    return jsonify(result)

# Add stub API endpoints for removed models to keep frontend working
# These will return empty data until the models are implemented

# Role API Endpoints
@app.route('/api/roles', methods=['GET'])
def get_roles():
    """Get all roles"""
    try:
        roles = Role.query.all()
        return jsonify([{
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'created_at': role.created_at.isoformat() if role.created_at else None
        } for role in roles]), 200
    except Exception as e:
        logger.error(f"Error fetching roles: {str(e)}")
        return jsonify({'error': 'Failed to fetch roles'}), 500

@app.route('/api/roles', methods=['POST'])
def add_role():
    """Add a new role"""
    try:
        data = request.get_json()
        logger.info(f"Adding role with data: {data}")
        
        if 'name' not in data:
            return jsonify({'error': 'name is required'}), 400
        
        role_name = data['name'].strip().lower()  # Normalize the input
        
        # Check if the role already exists
        existing_role = Role.query.filter_by(name=role_name).first()
        if existing_role:
            logger.info(f"Role '{role_name}' already exists with ID: {existing_role.id}")
            return jsonify({
                'message': 'Role already exists',
                'id': existing_role.id,
                'name': existing_role.name,
                'description': existing_role.description
            }), 409  # 409 Conflict status for existing resource
        
        # Create new role
        role = Role(
            name=role_name,
            description=data.get('description', f'Role: {role_name}')
        )
        
        db.session.add(role)
        db.session.commit()
        
        logger.info(f"Successfully created role '{role_name}' with ID: {role.id}")
        
        return jsonify({
            'message': 'Role created successfully',
            'id': role.id,
            'name': role.name,
            'description': role.description
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding role: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
        return jsonify({'error': f'Failed to add role: {str(e)}'}), 500

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

@app.route('/api/initialize-enhanced-data', methods=['POST'])
def initialize_enhanced_data():
    """Initialize sample data for testing the enhanced organization system"""
    try:
        # Initialize organization types
        OrganizationType.query.delete()
        types = ['church', 'school', 'other', 'institution', 'non-formal organization']
        for type_name in types:
            org_type = OrganizationType(type=type_name)
            db.session.add(org_type)
        
        # Create sample geo location
        sample_geo = GeoLocation(
            which='organization',
            continent='North America',
            region='North America',
            country='United States',
            province='California',
            city='Los Angeles',
            town='Downtown',
            address_line1='123 Main Street',
            postal_code='90210'
        )
        db.session.add(sample_geo)
        db.session.flush()
        
        # Create sample organization
        church_type = OrganizationType.query.filter_by(type='church').first()
        sample_org = Organization(
            name='Sample Church Organization',
            type=church_type.id,  # Maps to new 'type' column
            address=sample_geo.id,  # Maps to new 'address' column
            website='https://samplechurch.org',
            details={'denomination_affiliation': 'Methodist', 'umbrella_association_membership': 'World Methodist Council'}  # Maps to new 'details' JSON column
        )
        db.session.add(sample_org)
        
        # Update geo location with organization_id
        sample_geo.organization_id = sample_org.id
        
        db.session.commit()
        
        return jsonify({
            'message': 'Enhanced data initialized successfully',
            'organization_types': types,
            'sample_org_id': sample_org.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing enhanced data: {str(e)}")
        return jsonify({'error': 'Failed to initialize enhanced data'}), 500

# Add admin dashboard statistics endpoints
@app.route('/api/admin/dashboard-stats', methods=['GET'])
def get_admin_dashboard_stats():
    """Get statistics for admin dashboard"""
    try:
        # Get total users
        total_users = User.query.filter_by(role='user').count()
        
        # Get active users (users with survey_code)
        active_users = User.query.filter_by(role='user').filter(User.survey_code.isnot(None)).count()
        
        # Get completed surveys (users who have submitted user_details)
        completed_surveys = UserDetails.query.filter_by(is_submitted=True).count()
        
        # Get total organizations
        total_organizations = Organization.query.count()
        
        # Get organizations by type
        org_types = db.session.query(Organization.type, db.func.count(Organization.id)).group_by(Organization.type).all()
        organizations_by_type = {}
        for org_type_id, count in org_types:
            if org_type_id:
                org_type = OrganizationType.query.get(org_type_id)
                type_name = org_type.type if org_type else 'Unknown'
                organizations_by_type[type_name] = count
        
        # Get survey completion rate
        completion_rate = (completed_surveys / total_users * 100) if total_users > 0 else 0
        
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'completed_surveys': completed_surveys,
            'total_organizations': total_organizations,
            'organizations_by_type': organizations_by_type,
            'completion_rate': round(completion_rate, 1)
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching admin dashboard stats: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch dashboard stats: {str(e)}'}), 500

@app.route('/api/admin/organization-stats', methods=['GET'])
def get_organization_stats():
    """Get detailed organization statistics for admin dashboard"""
    try:
        # Get all organizations with their user counts and completion stats
        organizations = Organization.query.all()
        org_stats = []
        
        for org in organizations:
            # Count users in this organization
            user_count = User.query.filter_by(organization_id=org.id, role='user').count()
            
            # Count completed surveys for this organization
            completed_count = db.session.query(UserDetails).join(User).filter(
                UserDetails.is_submitted == True,
                User.organization_id == org.id
            ).count()
            
            # Calculate completion rate
            completion_rate = (completed_count / user_count * 100) if user_count > 0 else 0
            
            org_stats.append({
                'id': org.id,
                'name': org.name,
                'type': org.organization_type.type if org.organization_type else 'Unknown',
                'user_count': user_count,
                'completed_surveys': completed_count,
                'completion_rate': round(completion_rate, 1),
                'location': f"{org.geo_location.city}, {org.geo_location.country}" if org.geo_location else 'Unknown'
            })
        
        return jsonify(org_stats), 200
        
    except Exception as e:
        logger.error(f"Error fetching organization stats: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch organization stats: {str(e)}'}), 500

# Email API Endpoints
@app.route('/api/send-welcome-email', methods=['POST'])
def send_welcome_email_endpoint():
    """Send welcome email to a new user"""
    try:
        data = request.get_json()
        logger.info(f"Sending welcome email with data: {data}")
        
        # Validate required fields
        required_fields = ['to_email', 'username', 'password']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Send the email
        result = send_welcome_email(
            to_email=data['to_email'],
            username=data['username'],
            password=data['password'],
            firstname=data.get('firstname')
        )
        
        if result['success']:
            return jsonify({
                'message': 'Welcome email sent successfully',
                'method': result.get('method'),
                'message_id': result.get('message_id'),
                'to_email': data['to_email']
            }), 200
        else:
            return jsonify({
                'error': result['error']
            }), 500
            
    except Exception as e:
        logger.error(f"Error in send welcome email endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to send welcome email: {str(e)}'}), 500

@app.route('/api/test-email-config', methods=['GET'])
def test_email_config():
    """Test email configuration and SES connectivity"""
    try:
        results = {
            'ses_api': {'available': False, 'message': ''},
            'smtp': {'available': False, 'message': ''},
            'environment_vars': {}
        }
        
        # Check environment variables
        env_vars = [
            'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION',
            'SES_SMTP_USERNAME', 'SES_SMTP_PASSWORD', 'SES_VERIFIED_EMAIL'
        ]
        for var in env_vars:
            value = os.getenv(var)
            results['environment_vars'][var] = {
                'set': bool(value),
                'value': value[:10] + '...' if value and len(value) > 10 else value
            }
        
        # Test SES API client initialization
        try:
            ses_client = get_ses_client()
            if ses_client:
                try:
                    quota_response = ses_client.get_send_quota()
                    results['ses_api'] = {
                        'available': True,
                        'message': 'SES API client initialized successfully',
                        'quota': {
                            'max_24_hour_send': quota_response['Max24HourSend'],
                            'max_send_rate': quota_response['MaxSendRate'],
                            'sent_last_24_hours': quota_response['SentLast24Hours']
                        }
                    }
                except ClientError as e:
                    results['ses_api'] = {
                        'available': False,
                        'message': f'SES API credentials invalid: {e.response["Error"]["Message"]}'
                    }
            else:
                results['ses_api'] = {
                    'available': False,
                    'message': 'SES API client failed to initialize'
                }
        except Exception as e:
            results['ses_api'] = {
                'available': False,
                'message': f'SES API test failed: {str(e)}'
            }
        
        # Test SMTP credentials availability
        smtp_username = os.getenv('SES_SMTP_USERNAME')
        smtp_password = os.getenv('SES_SMTP_PASSWORD')
        
        if smtp_username and smtp_password:
            try:
                # Test SMTP connection (without actually sending)
                smtp_host = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
                smtp_port = int(os.getenv('SES_SMTP_PORT', '587'))
                
                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_username, smtp_password)
                
                results['smtp'] = {
                    'available': True,
                    'message': 'SMTP credentials valid and connection successful'
                }
            except Exception as e:
                results['smtp'] = {
                    'available': False,
                    'message': f'SMTP test failed: {str(e)}'
                }
        else:
            results['smtp'] = {
                'available': False,
                'message': 'SMTP credentials not found in environment'
            }
        
        # Determine overall status
        if results['ses_api']['available'] or results['smtp']['available']:
            status = 'success'
            message = 'Email functionality is available'
        else:
            status = 'error'
            message = 'No working email configuration found'
        
        return jsonify({
            'status': status,
            'message': message,
            'details': results,
            'region': os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        }), 200 if status == 'success' else 500
        
    except Exception as e:
        logger.error(f"Error testing email config: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Email configuration test failed: {str(e)}'
        }), 500

if __name__ == '__main__':
    #with app.app_context():
        # Drop and recreate tables to ensure schema is up-to-date
        #print("Recreating database tables to ensure schema is up-to-date...")
        #db.drop_all()  # This will drop all tables - be careful in production!
        #db.create_all()  # This will create all tables based on your models
        #print("Database tables created successfully!")
    app.run(debug=True)
