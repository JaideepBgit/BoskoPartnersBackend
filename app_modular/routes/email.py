"""
Email-related routes.
"""
from flask import Blueprint, request, jsonify
import logging
from sqlalchemy import or_

from ..config.database import db
from ..models.user import User
from ..models.organization import Organization
from ..models.email_template import EmailTemplate
from ..services.email_service import email_service
from ..utils.helpers import render_email_template

logger = logging.getLogger(__name__)

email_bp = Blueprint('email', __name__)


@email_bp.route('/send-welcome-email', methods=['POST'])
def send_welcome_email_endpoint():
    """Send welcome email to a new user."""
    data = request.json
    
    to_email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    firstname = data.get('firstname')
    survey_code = data.get('survey_code')
    template_id = data.get('template_id')
    
    if not to_email or not username or not password:
        return jsonify({"error": "Email, username, and password are required"}), 400
    
    try:
        # Get template if specified
        template_data = None
        if template_id:
            template = EmailTemplate.query.get(template_id)
            if template:
                template_data = template.to_dict()
        
        result = email_service.send_welcome_email(
            to_email=to_email,
            username=username,
            password=password,
            firstname=firstname,
            survey_code=survey_code,
            template_data=template_data
        )
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error sending welcome email: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/send-reminder-email', methods=['POST'])
def send_reminder_email_endpoint():
    """Send reminder email to a user about their pending survey."""
    data = request.json
    
    to_email = data.get('email')
    username = data.get('username')
    survey_code = data.get('survey_code')
    firstname = data.get('firstname')
    organization_name = data.get('organization_name')
    days_remaining = data.get('days_remaining')
    password = data.get('password')
    
    if not to_email or not username or not survey_code:
        return jsonify({"error": "Email, username, and survey_code are required"}), 400
    
    try:
        result = email_service.send_reminder_email(
            to_email=to_email,
            username=username,
            survey_code=survey_code,
            firstname=firstname,
            organization_name=organization_name,
            days_remaining=days_remaining,
            password=password
        )
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error sending reminder email: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/send-user-reminder/<int:user_id>', methods=['POST'])
def send_user_reminder_email(user_id):
    """Send reminder email to a specific user by user ID."""
    user = User.query.get_or_404(user_id)
    
    try:
        result = email_service.send_reminder_email(
            to_email=user.email,
            username=user.username,
            survey_code=user.survey_code,
            firstname=user.firstname,
            organization_name=user.organization.name if user.organization else None,
            password=user.password
        )
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"Error sending user reminder: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates', methods=['GET'])
def get_email_templates():
    """Get email templates, optionally filtered by organization."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        template_type = request.args.get('type')
        
        query = EmailTemplate.query
        
        if organization_id:
            query = query.filter_by(organization_id=organization_id)
        if template_type:
            query = query.filter_by(template_type=template_type)
        
        templates = query.all()
        
        return jsonify([t.to_dict() for t in templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting email templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/<int:template_id>', methods=['GET'])
def get_email_template(template_id):
    """Get a specific email template."""
    template = EmailTemplate.query.get_or_404(template_id)
    return jsonify(template.to_dict()), 200


@email_bp.route('/email-templates', methods=['POST'])
def save_email_template():
    """Create a new email template."""
    data = request.json
    
    organization_id = data.get('organization_id')
    name = data.get('name')
    
    if not organization_id or not name:
        return jsonify({"error": "Organization ID and name are required"}), 400
    
    try:
        template = EmailTemplate(
            organization_id=organization_id,
            name=name,
            subject=data.get('subject'),
            html_body=data.get('html_body'),
            text_body=data.get('text_body'),
            template_type=data.get('template_type', 'custom'),
            is_default=data.get('is_default', False)
        )
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            "message": "Email template created successfully",
            "id": template.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating email template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/<int:template_id>', methods=['PUT'])
def update_email_template(template_id):
    """Update an existing email template."""
    data = request.json
    template = EmailTemplate.query.get_or_404(template_id)
    
    try:
        if 'name' in data:
            template.name = data['name']
        if 'subject' in data:
            template.subject = data['subject']
        if 'html_body' in data:
            template.html_body = data['html_body']
        if 'text_body' in data:
            template.text_body = data['text_body']
        if 'template_type' in data:
            template.template_type = data['template_type']
        if 'is_default' in data:
            template.is_default = data['is_default']
        
        db.session.commit()
        
        return jsonify({
            "message": "Email template updated successfully",
            "id": template.id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/<int:template_id>', methods=['DELETE'])
def delete_email_template(template_id):
    """Delete an email template."""
    template = EmailTemplate.query.get_or_404(template_id)
    
    try:
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({"message": "Email template deleted successfully"}), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting email template: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/preview', methods=['POST'])
def render_email_template_preview():
    """Render email template preview with provided variables."""
    data = request.json
    
    template_content = data.get('template')
    variables = data.get('variables', {})
    
    if not template_content:
        return jsonify({"error": "Template content is required"}), 400
    
    try:
        rendered = render_email_template(template_content, **variables)
        return jsonify({"rendered": rendered}), 200
        
    except Exception as e:
        logger.error(f"Error rendering template preview: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/by-type/<template_type>', methods=['GET'])
def get_email_template_by_type(template_type):
    """Get email template by type (welcome, reminder, etc.)."""
    organization_id = request.args.get('organization_id', type=int)
    
    try:
        query = EmailTemplate.query.filter_by(template_type=template_type)
        
        if organization_id:
            # Try organization-specific first
            template = query.filter_by(organization_id=organization_id).first()
            if template:
                return jsonify(template.to_dict()), 200
        
        # Fallback to default
        template = query.filter_by(is_default=True).first()
        
        if template:
            return jsonify(template.to_dict()), 200
        
        return jsonify({"error": "Template not found"}), 404
        
    except Exception as e:
        logger.error(f"Error getting template by type: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/send-bulk-reminder-emails', methods=['POST'])
def send_bulk_reminder_emails():
    """Send reminder emails to multiple users at once."""
    data = request.json
    user_ids = data.get('user_ids', [])
    template_id = data.get('template_id')
    
    if not user_ids:
        return jsonify({"error": "user_ids are required"}), 400
    
    try:
        sent = []
        errors = []
        
        for user_id in user_ids:
            user = User.query.get(user_id)
            if not user:
                errors.append(f"User {user_id} not found")
                continue
            
            if not user.email:
                errors.append(f"User {user.username} has no email")
                continue
            
            try:
                result = email_service.send_reminder_email(
                    to_email=user.email,
                    username=user.username,
                    survey_code=user.survey_code,
                    firstname=user.firstname,
                    organization_name=user.organization.name if user.organization else None,
                    password=user.password
                )
                
                if result.get('success'):
                    sent.append({
                        "user_id": user_id,
                        "email": user.email,
                        "status": "sent"
                    })
                else:
                    errors.append(f"Failed to send to {user.email}: {result.get('error')}")
                    
            except Exception as e:
                errors.append(f"Error sending to {user.email}: {str(e)}")
        
        return jsonify({
            "message": f"Sent {len(sent)} reminder emails",
            "sent": sent,
            "errors": errors
        }), 200
        
    except Exception as e:
        logger.error(f"Error sending bulk reminders: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/generate-welcome-email-preview', methods=['POST'])
def generate_welcome_email_preview():
    """Generate welcome email preview with both text and HTML versions."""
    data = request.json
    
    username = data.get('username', 'test_user')
    firstname = data.get('firstname', 'Test')
    email = data.get('email', 'test@example.com')
    password = data.get('password', 'test_password')
    survey_code = data.get('survey_code', 'TEST123')
    template_id = data.get('template_id')
    
    try:
        # Get template if specified
        if template_id:
            template = EmailTemplate.query.get(template_id)
            if template:
                greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
                
                variables = {
                    'greeting': greeting,
                    'username': username,
                    'email': email,
                    'password': password,
                    'survey_code': survey_code
                }
                
                html_preview = render_email_template(template.html_body or '', **variables)
                text_preview = render_email_template(template.text_body or '', **variables)
                
                return jsonify({
                    "template_name": template.name,
                    "subject": template.subject,
                    "html_preview": html_preview,
                    "text_preview": text_preview
                }), 200
        
        # Default preview
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        return jsonify({
            "template_name": "Default Welcome",
            "subject": "Welcome to Saurara Platform",
            "html_preview": f"<h1>Welcome!</h1><p>{greeting},</p><p>Your credentials: Username: {username}, Password: {password}</p>",
            "text_preview": f"{greeting},\n\nYour credentials:\nUsername: {username}\nPassword: {password}\nSurvey Code: {survey_code}"
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/public/reminder', methods=['GET'])
def get_public_reminder_templates():
    """Get all public email templates that can be used for reminders."""
    try:
        templates = EmailTemplate.query.filter_by(
            template_type='reminder',
            is_default=True
        ).all()
        
        # Also get any templates marked as public
        public_templates = EmailTemplate.query.filter(
            EmailTemplate.template_type == 'reminder',
            EmailTemplate.is_default == False
        ).all()
        
        all_templates = templates + public_templates
        
        return jsonify([t.to_dict() for t in all_templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting public reminder templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/public/welcome', methods=['GET'])
def get_public_welcome_templates():
    """Get all public email templates that can be used for welcome emails."""
    try:
        templates = EmailTemplate.query.filter_by(
            template_type='welcome',
            is_default=True
        ).all()
        
        # Also get any templates marked as public
        public_templates = EmailTemplate.query.filter(
            EmailTemplate.template_type == 'welcome',
            EmailTemplate.is_default == False
        ).all()
        
        all_templates = templates + public_templates
        
        return jsonify([t.to_dict() for t in all_templates]), 200
        
    except Exception as e:
        logger.error(f"Error getting public welcome templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/email-templates/all', methods=['GET'])
def get_all_email_templates():
    """Dedicated endpoint to fetch all email templates with enhanced debugging."""
    try:
        organization_id = request.args.get('organization_id', type=int)
        
        logger.info(f"Fetching all email templates (org_id: {organization_id})")
        
        query = EmailTemplate.query
        
        if organization_id:
            # Get both org-specific and default templates
            query = query.filter(
                or_(
                    EmailTemplate.organization_id == organization_id,
                    EmailTemplate.is_default == True
                )
            )
        
        templates = query.all()
        
        logger.info(f"Found {len(templates)} email templates")
        
        result = []
        for t in templates:
            template_data = t.to_dict()
            template_data['organization_name'] = Organization.query.get(t.organization_id).name if t.organization_id else 'System Default'
            result.append(template_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error getting all email templates: {str(e)}")
        return jsonify({"error": str(e)}), 500


@email_bp.route('/test-email-config', methods=['GET'])
def test_email_config():
    """Test email configuration and SES connectivity."""
    import os
    
    try:
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        verified_email = os.getenv('SES_VERIFIED_EMAIL')
        smtp_username = os.getenv('SES_SMTP_USERNAME')
        
        config_status = {
            "aws_access_key_present": bool(aws_access_key),
            "aws_secret_key_present": bool(aws_secret_key),
            "verified_email": verified_email,
            "smtp_username_present": bool(smtp_username),
            "email_templates_count": EmailTemplate.query.count()
        }
        
        return jsonify({
            "status": "ok",
            "config": config_status
        }), 200
        
    except Exception as e:
        logger.error(f"Error testing email config: {str(e)}")
        return jsonify({"error": str(e)}), 500
