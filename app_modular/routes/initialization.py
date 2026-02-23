"""
Initialization routes for database setup and test data.
These endpoints are typically used during development or initial deployment.
"""
from flask import Blueprint, request, jsonify
import logging

from ..config.database import db
from ..models.user import User, UserDetails
from ..models.organization import Organization, OrganizationType
from ..models.email_template import EmailTemplate

logger = logging.getLogger(__name__)

initialization_bp = Blueprint('initialization', __name__)


@initialization_bp.route('/test', methods=['GET'])
def test_api():
    """Simple test endpoint to verify API is working."""
    return jsonify({
        "status": "success",
        "message": "API is working"
    }), 200


@initialization_bp.route('/test-database', methods=['GET'])
def test_database():
    """Test database connectivity and insertion."""
    logger.info("Testing database connectivity")
    
    try:
        # Test database connection using text()
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        
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
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Database test failed: {str(e)}"
        }), 500


@initialization_bp.route('/initialize-test-data', methods=['GET'])
def initialize_test_data():
    """Initialize test data for the application."""
    try:
        # Check if test organization exists
        test_org = Organization.query.filter_by(name="Test Organization").first()
        if not test_org:
            test_org = Organization(name="Test Organization")
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
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Error initializing test data: {str(e)}"
        }), 500


@initialization_bp.route('/organization-types/initialize', methods=['POST'])
def initialize_organization_types():
    """Initialize organization types with the required types."""
    try:
        # Clear existing types
        OrganizationType.query.delete()
        
        # Add the required types with proper capitalization
        types = ['CHURCH', 'School', 'OTHER', 'Institution', 'Non_formal_organizations']
        for type_name in types:
            org_type = OrganizationType(type=type_name)
            db.session.add(org_type)
        
        # Also initialize Titles
        from ..models.user import Title
        # Check if titles exist
        if Title.query.count() == 0:
            titles = [
                'President', 'Pastor', 'Coach', 'Director', 'Manager', 
                'Administrator', 'Staff', 'Leader', 'Member', 'Primary Contact', 
                'Secondary Contact', 'Other'
            ]
            for title_name in titles:
                title = Title(name=title_name)
                db.session.add(title)

        db.session.commit()
        
        return jsonify({
            'message': 'Organization types and titles initialized successfully',
            'types': types
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing organization types: {str(e)}")
        return jsonify({'error': 'Failed to initialize organization types'}), 500


@initialization_bp.route('/initialize-default-email-templates', methods=['POST'])
def initialize_default_email_templates():
    """Initialize default email templates for welcome and reminder emails."""
    try:
        # Get the first organization to associate templates with
        first_org = Organization.query.first()
        if not first_org:
            return jsonify({'error': 'No organizations found. Please create an organization first.'}), 400
        
        # Check if default templates already exist
        existing_welcome = EmailTemplate.query.filter_by(
            organization_id=first_org.id, 
            name='Default Welcome Email'
        ).first()
        existing_reminder = EmailTemplate.query.filter_by(
            organization_id=first_org.id, 
            name='Default Reminder Email'
        ).first()
        
        templates_created = []
        
        # Create Welcome Email Template
        if not existing_welcome:
            welcome_html = """
            <html>
            <head>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
                    .container { max-width: 650px; margin: 0 auto; padding: 20px; background: #f8fafc; }
                    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 15px 15px 0 0; }
                    .content { background: #ffffff; padding: 40px 30px; border: 1px solid #e2e8f0; }
                    .footer { background: #f8fafc; padding: 30px; border-radius: 0 0 15px 15px; border: 1px solid #e2e8f0; border-top: none; text-align: center; }
                    .credentials { background: #e8f5e8; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #10b981; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎉 Welcome to Saurara!</h1>
                    </div>
                    <div class="content">
                        <p>{{greeting}},</p>
                        <p>Welcome to the Saurara Platform! Your account has been successfully created.</p>
                        <div class="credentials">
                            <h3>Your Account Credentials:</h3>
                            <ul>
                                <li><strong>Username:</strong> {{username}}</li>
                                <li><strong>Email:</strong> {{email}}</li>
                                <li><strong>Temporary Password:</strong> {{password}}</li>
                                <li><strong>Survey Code:</strong> {{survey_code}}</li>
                            </ul>
                        </div>
                        <p>Please change your password during your first login.</p>
                    </div>
                    <div class="footer">
                        <p>Best regards,<br><strong>The Saurara Research Team</strong></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            welcome_text = """{{greeting}},

Welcome to the Saurara Platform! Your account has been successfully created.

Your Account Credentials:
• Username: {{username}}
• Email: {{email}}
• Temporary Password: {{password}}
• Survey Code: {{survey_code}}

Please change your password during your first login.

Best regards,
The Saurara Research Team"""

            welcome_template = EmailTemplate(
                organization_id=first_org.id,
                name='Default Welcome Email',
                subject='Welcome to Saurara Platform',
                html_body=welcome_html,
                text_body=welcome_text,
                is_public=True
            )
            db.session.add(welcome_template)
            templates_created.append('Default Welcome Email')
        
        # Create Reminder Email Template
        if not existing_reminder:
            reminder_html = """
            <html>
            <head>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
                    .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }
                    .content { background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }
                    .footer { background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔔 Survey Reminder</h1>
                    </div>
                    <div class="content">
                        <p>{{greeting}},</p>
                        <p>This is a friendly reminder that you have a pending survey on the Saurara Platform.</p>
                        <p><strong>Survey Code:</strong> {{survey_code}}</p>
                        <p>Please complete your survey at your earliest convenience.</p>
                    </div>
                    <div class="footer">
                        <p>Best regards,<br><strong>The Saurara Research Team</strong></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            reminder_text = """{{greeting}},

This is a friendly reminder that you have a pending survey on the Saurara Platform.

Survey Code: {{survey_code}}

Please complete your survey at your earliest convenience.

Best regards,
The Saurara Research Team"""

            reminder_template = EmailTemplate(
                organization_id=first_org.id,
                name='Default Reminder Email',
                subject='Reminder: Complete Your Saurara Survey',
                html_body=reminder_html,
                text_body=reminder_text,
                is_public=True
            )
            db.session.add(reminder_template)
            templates_created.append('Default Reminder Email')
        
        db.session.commit()
        
        return jsonify({
            'message': 'Email templates initialization completed',
            'templates_created': templates_created,
            'templates_skipped': ['Default Welcome Email', 'Default Reminder Email'] if not templates_created else []
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing email templates: {str(e)}")
        return jsonify({'error': f'Failed to initialize email templates: {str(e)}'}), 500


@initialization_bp.route('/debug/email-templates', methods=['GET'])
def debug_email_templates():
    """Debug endpoint to check email templates table and data integrity."""
    try:
        count = EmailTemplate.query.count()
        templates = EmailTemplate.query.all()
        
        template_info = []
        for t in templates:
            template_info.append({
                'id': t.id,
                'name': t.name,
                'organization_id': t.organization_id,
                'subject': t.subject,
                'is_public': t.is_public,
                'has_html_body': bool(t.html_body),
                'has_text_body': bool(t.text_body)
            })
        
        return jsonify({
            'success': True,
            'total_templates': count,
            'templates': template_info
        }), 200
        
    except Exception as e:
        logger.error(f"Error debugging email templates: {str(e)}")
        return jsonify({'error': str(e)}), 500


@initialization_bp.route('/test/survey-assignments', methods=['GET'])
def test_survey_assignments():
    """Test endpoint to check survey assignments in database."""
    from ..models.survey import SurveyResponse
    
    try:
        # Get response counts by status
        assigned = SurveyResponse.query.filter_by(status='assigned').count()
        draft = SurveyResponse.query.filter_by(status='draft').count()
        submitted = SurveyResponse.query.filter_by(status='submitted').count()
        completed = SurveyResponse.query.filter_by(status='completed').count()
        
        return jsonify({
            'success': True,
            'assignments': {
                'assigned': assigned,
                'draft': draft,
                'submitted': submitted,
                'completed': completed,
                'total': assigned + draft + submitted + completed
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error checking survey assignments: {str(e)}")
        return jsonify({'error': str(e)}), 500


@initialization_bp.route('/test/email-templates-integration', methods=['GET'])
def test_email_templates_integration():
    """Test endpoint to verify email template integration."""
    try:
        # Check if we can query email templates
        templates = EmailTemplate.query.limit(5).all()
        
        # Check if organization relationships work
        template_orgs = []
        for t in templates:
            org_name = t.organization.name if t.organization else 'No org'
            template_orgs.append({
                'template': t.name,
                'organization': org_name
            })
        
        return jsonify({
            'success': True,
            'message': 'Email template integration test passed',
            'templates_found': len(templates),
            'template_organizations': template_orgs
        }), 200
        
    except Exception as e:
        logger.error(f"Error testing email template integration: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
