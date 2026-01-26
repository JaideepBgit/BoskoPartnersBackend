from flask import Flask, request, jsonify, g, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy import text, or_
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import joinedload
import json 
from datetime import datetime, timedelta
import secrets
import logging
import traceback

# Disable Numba debug logging
logging.getLogger('numba').setLevel(logging.WARNING)
import uuid
import time
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
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time as time_module
import secrets
from datetime import timedelta

# Ensure .env values override any existing environment variables and are resolved
# relative to this file's directory, so local edits take effect on reloads.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'), override=True)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Import services
from document_parser import DocumentParserService

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

# Helper function to check email service status
def is_email_service_active_for_organization(org_id):
    """Check if email service is currently active for an organization"""
    try:
        org = Organization.query.get(org_id)
        if not org:
            return False, "Organization not found"
        
        # Email service is always active for existing organizations
        return True, "Email service is active"
    except Exception as e:
        logger.error(f"Error checking email service status for organization {org_id}: {str(e)}")
        return False, f"Error checking email service status: {str(e)}"

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

def send_welcome_email_smtp(to_email, username, password, firstname=None, survey_code=None):
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
        
        # Debug the password being used in SMTP email template
        logger.info(f"SMTP Email template variables - Username: '{username}', Email: '{to_email}', Password: '{password}', Survey Code: '{survey_code}', Greeting: '{greeting}'")
        
        body_text = f"""{greeting},

Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

Your Account Credentials:
• Username: {username}
• Email Address: {to_email}
• Temporary Password: {password}
• Survey Code: {survey_code if survey_code else 'Not assigned'}
• Platform Access: www.saurara.org

Quick Start Guide:
1. Visit www.saurara.org
2. Click on "Login" or "Survey Access"
3. Enter your username and password above
4. Complete your profile setup when ready
5. Explore survey opportunities and platform features
6. Connect with your organization and peers

Important Security Information:
For your account security, please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals.

What Awaits You:
As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. Every response makes a difference!

Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

Getting the Most Out of Saurara:
- Complete your profile for better survey matching
- Respond to surveys thoughtfully and thoroughly
- Stay engaged with platform updates and announcements
- Reach out for support whenever needed

Need Assistance?
Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard! 🌟

Best regards,
The Saurara Research Team

---
Platform: www.saurara.org
Support: info@saurara.org
Stay Connected: Follow us for updates and insights"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 650px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 15px 15px 0 0; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3); }}
                .content {{ background: #ffffff; padding: 40px 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); }}
                .footer {{ background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); padding: 30px; border-radius: 0 0 15px 15px; border: 1px solid #e2e8f0; border-top: none; }}
                .welcome-banner {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 20px; border-radius: 12px; margin: 25px 0; text-align: center; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }}
                .credentials-box {{ background: linear-gradient(135deg, #e8f5e8 0%, #dcf4dc 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #10b981; box-shadow: 0 2px 10px rgba(16, 185, 129, 0.1); }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3); transition: transform 0.2s; }}
                .button:hover {{ transform: translateY(-2px); }}
                .quick-start {{ background: linear-gradient(135deg, #fff9e6 0%, #fef3c7 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #f59e0b; }}
                .security-alert {{ background: linear-gradient(135deg, #fef7e0 0%, #fed7aa 100%); padding: 20px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #f97316; }}
                .features-grid {{ background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #8b5cf6; }}
                .tips-section {{ background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #10b981; }}
                .support-box {{ background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #3b82f6; }}
                .welcome-tag {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 6px 15px; border-radius: 25px; font-size: 12px; font-weight: bold; display: inline-block; }}
                .credential-item {{ background: white; padding: 12px; margin: 8px 0; border-radius: 8px; border-left: 3px solid #10b981; }}
                .feature-item {{ margin: 10px 0; padding: 8px 0; }}
                .tip-item {{ margin: 8px 0; padding: 5px 0; }}
                ol {{ padding-left: 25px; }}
                ol li {{ margin: 10px 0; padding: 5px 0; }}
                .sparkle {{ color: #f59e0b; }}
                .heart {{ color: #ef4444; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 32px; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">🎉 Welcome to Saurara!</h1>
                    <p style="margin: 15px 0 0 0; font-size: 18px; opacity: 0.95; font-weight: 300;">Research & Community Excellence Platform</p>
                    <div style="margin-top: 20px;">
                        <span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px; font-size: 14px;">✨ Your Journey Begins Now ✨</span>
                    </div>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <div class="highlight">
                        <p><strong>🌟 Welcome to the Saurara Platform!</strong></p>
                        <p>We are excited to have you join our community. Your account has been successfully created and you're ready to get started!</p>
                    </div>
                    
                    <div class="account-details">
                        <h3 style="color: #2c5530; margin-top: 0;">🔐 Your Account Details</h3>
                        <ul style="list-style-type: none; padding-left: 0;">
                            <li><strong>👤 Username:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{username}</code></li>
                            <li><strong>📧 Email:</strong> {to_email}</li>
                            <li><strong>🔑 Password:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{password}</code></li>
                            <li><strong>🆔 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code if survey_code else 'Not assigned'}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="http://www.saurara.org" class="button">🚀 Access Platform Now</a>
                    </div>
                    
                    <div class="steps">
                        <h3 style="color: #b8860b; margin-top: 0;">📝 Getting Started</h3>
                        <ol>
                            <li>Visit <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                            <li>Click on "Login" or "Survey Access"</li>
                            <li>Enter your username and password</li>
                            <li>Complete your profile and survey when ready</li>
                            <li>Explore the platform features</li>
                        </ol>
                    </div>
                    
                    <div class="security-box">
                        <h3 style="color: #d97706; margin-top: 0;">🔒 Security Reminder</h3>
                        <p style="margin-bottom: 0;">Please keep your login information secure and consider changing your password after your first login for enhanced security.</p>
                    </div>
                    
                    <h3 style="color: #667eea;">🎯 What's Next?</h3>
                    <p>You'll soon receive information about surveys and research initiatives relevant to your organization. Your participation helps us understand and improve educational and community programs.</p>
                    
                    <div style="background: #e8f4fd; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #1565c0; margin-top: 0;">🆘 Need Help?</h3>
                        <p style="margin-bottom: 0;">If you have any questions or need assistance getting started, please don't hesitate to contact our support team. We're here to help!</p>
                    </div>
                    
                    <p style="font-weight: bold; color: #667eea;">Thank you for joining the Saurara community! 🌟</p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; text-align: center; color: #4b5563; font-size: 16px;">
                        <strong>Best regards,<br>The Saurara Research Team</strong>
                    </p>
                    <hr style="border: none; border-top: 2px solid #d1d5db; margin: 20px 0;">
                    <div style="text-align: center;">
                        <span class="welcome-tag">WELCOME</span>
                    </div>
                    <p style="margin: 15px 0 0 0; text-align: center; color: #6b7280; font-size: 14px;">
                        <a href="http://www.saurara.org" style="color: #667eea; text-decoration: none; font-weight: 500;">www.saurara.org</a> | 
                        <a href="mailto:info@saurara.org" style="color: #667eea; text-decoration: none; font-weight: 500;">info@saurara.org</a><br>
                        <strong>Stay Connected:</strong> Follow us for updates and insights
                    </p>
                </div>
            </div>
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

def send_welcome_email(to_email, username, password, firstname=None, survey_code=None, email_template_id=None):
    """Send welcome email to new user using database template (tries SES API first, falls back to SMTP)"""
    logger.info(f"[EMAIL] Starting send_welcome_email - to_email: {to_email}, username: {username}, firstname: {firstname}, survey_code: {survey_code}, email_template_id: {email_template_id}")
    
    try:
        # Try to get specific email template by ID, or fallback to default welcome template
        if email_template_id:
            logger.info(f"[EMAIL] Attempting to use specific email template ID: {email_template_id}")
            try:
                template = EmailTemplate.query.get(email_template_id)
                if template:
                    template_data = {
                        'name': template.name,
                        'subject': template.subject,
                        'html_body': template.html_body,
                        'text_body': template.text_body
                    }
                    use_template = True
                    logger.info(f"[EMAIL] Successfully loaded specific email template ID {email_template_id}: {template.name}")
                else:
                    logger.warning(f"[EMAIL] Specific template ID {email_template_id} not found, falling back to default")
                    # Fallback to default template if specified template not found
                    template_response = get_email_template_by_type('welcome')
                    use_template = template_response[1] == 200
                    if use_template:
                        template_data = template_response[0].get_json()
                        logger.info("[EMAIL] Specified template not found, using default welcome template")
                    else:
                        logger.error("[EMAIL] Failed to load both specific and default templates")
                        use_template = False
            except Exception as e:
                logger.error(f"[EMAIL] Error fetching specific email template {email_template_id}: {str(e)}")
                # Fallback to default template
                logger.info(f"[EMAIL] Attempting fallback to default welcome template")
                template_response = get_email_template_by_type('welcome')
                use_template = template_response[1] == 200
                if use_template:
                    template_data = template_response[0].get_json()
                    logger.info("[EMAIL] Error with specific template, using default welcome template")
                else:
                    logger.error("[EMAIL] Failed to load fallback default template")
                    use_template = False
        else:
            # Use default welcome template
            logger.info(f"[EMAIL] No specific template ID provided, using default welcome template")
            template_response = get_email_template_by_type('welcome')
            use_template = template_response[1] == 200
            if use_template:
                template_data = template_response[0].get_json()
                logger.info("[EMAIL] Successfully loaded default welcome template")
            else:
                logger.error("[EMAIL] Failed to load default welcome template")
        
        if use_template:
            logger.info(f"[EMAIL] Processing template data: {template_data.get('name', 'Unknown')}")
            subject = template_data['subject']
            
            # Create personalized greeting
            greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
            logger.info(f"[EMAIL] Created greeting: {greeting}")
            
            # Template variables
            template_vars = {
                'greeting': greeting,
                'username': username,
                'email': to_email,
                'password': password,
                'survey_code': survey_code if survey_code else 'Not assigned'
            }
            logger.info(f"[EMAIL] Template variables prepared: {list(template_vars.keys())}")
            
            # Render template content
            try:
                body_text = render_email_template(template_data['text_body'], **template_vars)
                body_html = render_email_template(template_data['html_body'], **template_vars)
                logger.info(f"[EMAIL] Template rendering successful")
            except Exception as render_error:
                logger.error(f"[EMAIL] Template rendering failed: {str(render_error)}")
                raise render_error
            
            logger.info(f"[EMAIL] Using email template: {template_data['name']}")
        else:
            # Fallback to hardcoded content if template not found
            logger.warning("[EMAIL] Welcome email template not found, using fallback content")
            subject = "Welcome to Saurara Platform"
            greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
            logger.info(f"[EMAIL] Using fallback greeting: {greeting}")
            
            body_text = f"""{greeting},

🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

🔐 Your Account Credentials:
• Username: {username}
• Email Address: {to_email}
• Temporary Password: {password}
• Survey Code: {survey_code if survey_code else 'Not assigned'}
• Platform Access: www.saurara.org

Welcome aboard! 🌟

Best regards,
The Saurara Research Team"""

            body_html = f"""<html><body><h1>Welcome to Saurara!</h1><p>{greeting},</p><p>🎉 Welcome to the Saurara Platform!</p><p><strong>Your Account Credentials:</strong><br>Username: {username}<br>Password: {password}<br>Survey Code: {survey_code if survey_code else 'Not assigned'}</p><p>Best regards,<br>The Saurara Research Team</p></body></html>"""
            logger.info(f"[EMAIL] Fallback content prepared with subject: {subject}")
        
        logger.info(f"[EMAIL] Attempting to get SES client")
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("[EMAIL] SES API client failed, trying SMTP method...")
            return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)
        else:
            logger.info(f"[EMAIL] SES client obtained successfully")
        
        # Debug the password being used in email template
        logger.info(f"[EMAIL] Template variables - Username: '{username}', Email: '{to_email}', Password: '{password}', Survey Code: '{survey_code}'")
        
        # Get verified sender email from environment
        source_email = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')
        logger.info(f"[EMAIL] Using source email: {source_email}")
        
        # Send email
        logger.info(f"[EMAIL] Preparing to send email via SES API")
        logger.info(f"[EMAIL] Email details - To: {to_email}, Subject: {subject}, Source: {source_email}")
        
        try:
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
            logger.info(f"[EMAIL] SES API call successful")
        except Exception as ses_error:
            logger.error(f"[EMAIL] SES API call failed: {str(ses_error)}")
            raise ses_error
        
        logger.info(f"[EMAIL] Welcome email sent successfully via SES API to {to_email}. Message ID: {response['MessageId']}")
        return {
            'success': True,
            'method': 'SES_API',
            'message_id': response['MessageId'],
            'message': 'Email sent successfully via SES API'
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[EMAIL] SES API ClientError: {error_code} - {error_message}")
        logger.warning("[EMAIL] SES API failed, trying SMTP method as fallback...")
        return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)
    except Exception as e:
        logger.error(f"[EMAIL] Error sending welcome email via SES API: {str(e)}")
        logger.warning("[EMAIL] SES API failed, trying SMTP method as fallback...")
        return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)

def send_survey_assignment_email(to_email, username, password, survey_code, firstname=None, organization_name=None, survey_name=None, assigned_by=None):
    """Send survey assignment email to user (tries SES API first, falls back to SMTP).
    Includes user's existing password and survey code from users table.
    """
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_survey_assignment_email_smtp(to_email, username, password, survey_code, firstname, organization_name, survey_name, assigned_by)
        
        # Email content
        subject = f"📋 New Survey Assignment: {survey_name or 'Survey'}"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        org_text = f" from {organization_name}" if organization_name else ""
        assigned_by_text = f" by {assigned_by}" if assigned_by else " by your administrator"
        survey_title = survey_name or "New Survey"
        
        body_text = f"""{greeting},

We're pleased to inform you that you have been assigned a new survey{org_text} on the Saurara Platform!

📋 Survey Assignment Details:
• Survey: {survey_title}
• Assigned{assigned_by_text}
• Username: {username}
• Password: {password}
• Survey Code: {survey_code}
• Survey Link: www.saurara.org

🎯 About This Survey:
You have been specifically selected to participate in this important research initiative. Your insights and experiences are valuable to understanding and improving educational and community programs.

📝 How to Access Your Survey:
1. Visit www.saurara.org
2. Click on "Survey Access" or "Login"
3. Enter your survey code: {survey_code}
4. Complete the survey at your convenience
5. Submit your responses when finished

⏱️ Survey Information:
• Estimated completion time: 15-20 minutes
• You can save your progress and return later
• All responses are confidential and secure
• Your participation is greatly appreciated

🌟 Why Your Participation Matters:
Your responses contribute to meaningful research that helps improve educational initiatives and community programs. Every answer you provide helps us better understand the needs and challenges in your field.

Need Help?
If you have any questions about the survey or experience technical difficulties, please don't hesitate to contact our support team. We're here to ensure you have a smooth experience.

Thank you for your time and valuable contribution to this research!

Best regards,
The Saurara Research Team

---
Survey Platform: www.saurara.org | Support: info@saurara.org"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .footer {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; }}
                .highlight {{ background: #e8f5e8; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; }}
                .survey-details {{ background: #f0f8ff; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .button {{ display: inline-block; background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0; }}
                .steps {{ background: #fff9e6; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .steps ol {{ margin: 0; padding-left: 20px; }}
                .steps li {{ margin: 8px 0; }}
                .assignment-tag {{ background: #28a745; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">📋 New Survey Assignment</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Research Platform</p>
                    <span class="assignment-tag">NEW ASSIGNMENT</span>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <p>We're pleased to inform you that you have been assigned a new survey{org_text} on the Saurara Platform!</p>
                    
                    <div class="highlight">
                        <p><strong>🎯 Survey Assignment</strong></p>
                        <p>You have been specifically selected to participate in: <strong>{survey_title}</strong></p>
                        <p>Assigned{assigned_by_text}</p>
                    </div>
                    
                    <div class="survey-details">
                        <h3 style="color: #155724; margin-top: 0;">📊 Survey Access Information</h3>
                        <ul style="list-style-type: none; padding-left: 0;">
                            <li><strong>📋 Survey:</strong> {survey_title}</li>
                            <li><strong>👤 Username:</strong> {username}</li>
                            <li><strong>🔑 Password:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{password}</code></li>
                            <li><strong>🔑 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #28a745;">www.saurara.org</a></li>
                        </ul>
                    </div>
                    
                    <div class="steps">
                        <h3 style="color: #856404; margin-top: 0;">📝 How to Access Your Survey</h3>
                        <ol>
                            <li><strong>Visit</strong> <a href="http://www.saurara.org" style="color: #28a745;">www.saurara.org</a></li>
                            <li><strong>Click</strong> on "Survey Access" or "Login"</li>
                            <li><strong>Enter</strong> your survey code: <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>Complete</strong> the survey at your convenience</li>
                            <li><strong>Submit</strong> your responses when finished</li>
                        </ol>
                    </div>
                    
                    <div style="background: #d1ecf1; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #17a2b8;">
                        <h3 style="color: #0c5460; margin-top: 0;">⏱️ Survey Information</h3>
                        <ul style="margin: 0;">
                            <li><strong>Estimated time:</strong> 15-20 minutes</li>
                            <li><strong>Progress saving:</strong> Available (you can return later)</li>
                            <li><strong>Confidentiality:</strong> All responses are secure and confidential</li>
                            <li><strong>Support:</strong> Help available if needed</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="http://www.saurara.org" class="button" style="color: white; text-decoration: none;">🚀 Access Survey Now</a>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107;">
                        <p style="margin: 0;"><strong>🌟 Why Your Participation Matters:</strong></p>
                        <p style="margin: 5px 0 0 0;">Your responses contribute to meaningful research that helps improve educational initiatives and community programs. Every answer you provide helps us better understand the needs and challenges in your field.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; text-align: center; color: #6c757d; font-size: 14px;">
                        <strong>🆘 Need Help?</strong><br>
                        Contact our support team if you have questions or technical difficulties.<br>
                        <strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">www.saurara.org</a> | 
                        <strong>📧 Support:</strong> <a href="mailto:info@saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">info@saurara.org</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send the email
        response = ses_client.send_email(
            Source=os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org'),
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {
                    'Text': {'Data': body_text, 'Charset': 'UTF-8'},
                    'Html': {'Data': body_html, 'Charset': 'UTF-8'}
                }
            }
        )
        
        logger.info(f"Survey assignment email sent successfully via SES API to {to_email}")
        return {
            'success': True,
            'method': 'SES API',
            'message': 'Survey assignment email sent successfully via SES API',
            'message_id': response['MessageId']
        }
        
    except Exception as e:
        logger.error(f"Error sending survey assignment email via SES API: {str(e)}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_survey_assignment_email_smtp(to_email, username, password, survey_code, firstname, organization_name, survey_name, assigned_by)

def send_survey_assignment_email_smtp(to_email, username, password, survey_code, firstname=None, organization_name=None, survey_name=None, assigned_by=None):
    """Send survey assignment email using SMTP (includes password and survey code)."""
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
        subject = f"📋 New Survey Assignment: {survey_name or 'Survey'}"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        org_text = f" from {organization_name}" if organization_name else ""
        assigned_by_text = f" by {assigned_by}" if assigned_by else " by your administrator"
        survey_title = survey_name or "New Survey"
        
        body_text = f"""{greeting},

We're pleased to inform you that you have been assigned a new survey{org_text} on the Saurara Platform!

📋 Survey Assignment Details:
• Survey: {survey_title}
• Assigned{assigned_by_text}
• Username: {username}
• Password: {password}
• Survey Code: {survey_code}
• Survey Link: www.saurara.org

🎯 About This Survey:
You have been specifically selected to participate in this important research initiative. Your insights and experiences are valuable to understanding and improving educational and community programs.

📝 How to Access Your Survey:
1. Visit www.saurara.org
2. Click on "Survey Access" or "Login"
3. Enter your survey code: {survey_code}
4. Complete the survey at your convenience
5. Submit your responses when finished

⏱️ Survey Information:
• Estimated completion time: 15-20 minutes
• You can save your progress and return later
• All responses are confidential and secure
• Your participation is greatly appreciated

🌟 Why Your Participation Matters:
Your responses contribute to meaningful research that helps improve educational initiatives and community programs. Every answer you provide helps us better understand the needs and challenges in your field.

Need Help?
If you have any questions about the survey or experience technical difficulties, please don't hesitate to contact our support team. We're here to ensure you have a smooth experience.

Thank you for your time and valuable contribution to this research!

Best regards,
The Saurara Research Team

---
Survey Platform: www.saurara.org | Support: info@saurara.org"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .footer {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; }}
                .highlight {{ background: #e8f5e8; padding: 15px; border-left: 4px solid #28a745; margin: 20px 0; }}
                .survey-details {{ background: #f0f8ff; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .button {{ display: inline-block; background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0; }}
                .steps {{ background: #fff9e6; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .steps ol {{ margin: 0; padding-left: 20px; }}
                .steps li {{ margin: 8px 0; }}
                .assignment-tag {{ background: #28a745; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">📋 New Survey Assignment</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Research Platform</p>
                    <span class="assignment-tag">NEW ASSIGNMENT</span>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <p>We're pleased to inform you that you have been assigned a new survey{org_text} on the Saurara Platform!</p>
                    
                    <div class="highlight">
                        <p><strong>🎯 Survey Assignment</strong></p>
                        <p>You have been specifically selected to participate in: <strong>{survey_title}</strong></p>
                        <p>Assigned{assigned_by_text}</p>
                    </div>
                    
                    <div class="survey-details">
                        <h3 style="color: #155724; margin-top: 0;">📊 Survey Access Information</h3>
                        <ul style="list-style-type: none; padding-left: 0;">
                            <li><strong>📋 Survey:</strong> {survey_title}</li>
                            <li><strong>👤 Username:</strong> {username}</li>
                            <li><strong>🔑 Password:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{password}</code></li>
                            <li><strong>🔑 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #28a745;">www.saurara.org</a></li>
                        </ul>
                    </div>
                    
                    <div class="steps">
                        <h3 style="color: #856404; margin-top: 0;">📝 How to Access Your Survey</h3>
                        <ol>
                            <li><strong>Visit</strong> <a href="http://www.saurara.org" style="color: #28a745;">www.saurara.org</a></li>
                            <li><strong>Click</strong> on "Survey Access" or "Login"</li>
                            <li><strong>Enter</strong> your survey code: <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>Complete</strong> the survey at your convenience</li>
                            <li><strong>Submit</strong> your responses when finished</li>
                        </ol>
                    </div>
                    
                    <div style="background: #d1ecf1; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #17a2b8;">
                        <h3 style="color: #0c5460; margin-top: 0;">⏱️ Survey Information</h3>
                        <ul style="margin: 0;">
                            <li><strong>Estimated time:</strong> 15-20 minutes</li>
                            <li><strong>Progress saving:</strong> Available (you can return later)</li>
                            <li><strong>Confidentiality:</strong> All responses are secure and confidential</li>
                            <li><strong>Support:</strong> Help available if needed</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="http://www.saurara.org" class="button" style="color: white; text-decoration: none;">🚀 Access Survey Now</a>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107;">
                        <p style="margin: 0;"><strong>🌟 Why Your Participation Matters:</strong></p>
                        <p style="margin: 5px 0 0 0;">Your responses contribute to meaningful research that helps improve educational initiatives and community programs. Every answer you provide helps us better understand the needs and challenges in your field.</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; text-align: center; color: #6c757d; font-size: 14px;">
                        <strong>🆘 Need Help?</strong><br>
                        Contact our support team if you have questions or technical difficulties.<br>
                        <strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">www.saurara.org</a> | 
                        <strong>📧 Support:</strong> <a href="mailto:info@saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">info@saurara.org</a>
                    </p>
                </div>
            </div>
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
        
        logger.info(f"Survey assignment email sent successfully via SMTP to {to_email}")
        return {
            'success': True,
            'method': 'SMTP',
            'message': 'Survey assignment email sent successfully via SMTP'
        }
        
    except Exception as e:
        logger.error(f"Error sending survey assignment email via SMTP: {str(e)}")
        return {
            'success': False,
            'error': f"SMTP survey assignment email sending failed: {str(e)}"
        }

def send_reminder_email_smtp(to_email, username, survey_code, firstname=None, organization_name=None, days_remaining=None, password=None):
    """Send reminder email using SMTP"""
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
        subject = "🔔 Reminder: Complete Your Saurara Survey"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        org_text = f" from {organization_name}" if organization_name else ""
        deadline_text = f" You have {days_remaining} days remaining to complete it." if days_remaining else ""
        password_text = f"\n• Password: {password}" if password else ""
        
        body_text = f"""{greeting},

We hope this message finds you well!

This is a friendly reminder that you have a pending survey{org_text} on the Saurara Platform that requires your attention.{deadline_text}

Your Survey Details:
• Username: {username}{password_text}
• Survey Code: {survey_code}
• Survey Link: www.saurara.org

🔑 NEED YOUR PASSWORD?
Your login password was sent in your WELCOME EMAIL when your account was created. 
Please search your email inbox for "Welcome to Saurara Platform" to find your credentials.

If you cannot find your welcome email or need to reset your password, please use the 
"Forgot Password" link on the login page or contact support at info@saurara.org

Why Your Response Matters:
Your input is invaluable in helping us understand and improve educational and community initiatives. Every response contributes to meaningful research that can make a real difference in communities like yours.

What You Need to Do:
1. Visit www.saurara.org
2. Enter your survey code: {survey_code}
3. Complete the survey at your convenience
4. Submit your responses

The survey typically takes 15-20 minutes to complete, and you can save your progress and return later if needed.

Need Help?
If you're experiencing any difficulties or have questions about the survey, please don't hesitate to reach out to our support team. We're here to help!

We truly appreciate your time and participation. Your voice matters, and we look forward to receiving your valuable insights.

Thank you for being part of the Saurara community!

Best regards,
The Saurara Research Team

---
This is an automated reminder. If you have already completed the survey, please disregard this message.
Visit: www.saurara.org | Email: info@saurara.org"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .footer {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; }}
                .highlight {{ background: #f0f8ff; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; }}
                .survey-details {{ background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0; }}
                .steps {{ background: #fff9e6; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .steps ol {{ margin: 0; padding-left: 20px; }}
                .steps li {{ margin: 8px 0; }}
                .reminder-tag {{ background: #ff6b6b; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">🔔 Survey Reminder</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Research Platform</p>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <p>We hope this message finds you well!</p>
                    
                    <div class="highlight">
                        <p><strong>📋 Pending Survey Reminder</strong></p>
                        <p>You have a pending survey{org_text} on the Saurara Platform that requires your attention.{deadline_text}</p>
                    </div>
                    
                    <div class="survey-details">
                        <h3 style="color: #2c5530; margin-top: 0;">📊 Your Survey Details</h3>
                        <ul style="list-style-type: none; padding-left: 0;">
                            <li><strong>👤 Username:</strong> {username}</li>
                            {'<li><strong>🔐 Password:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">' + password + '</code></li>' if password else ''}
                            <li><strong>🔑 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                        </ul>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                        <h3 style="color: #f57c00; margin-top: 0;">🔑 Need Your Password?</h3>
                        <p style="margin-bottom: 0;">
                            Your login password was sent in your <strong>Welcome Email</strong> when your account was created. 
                            Please search your email inbox for "Welcome to Saurara Platform" to find your credentials.
                            <br><br>
                            If you cannot find your welcome email or need to reset your password, please use the 
                            <strong>"Forgot Password"</strong> link on the login page or contact support at 
                            <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a>
                        </p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="http://www.saurara.org" class="button">🚀 Complete Survey Now</a>
                    </div>
                    
                    <h3 style="color: #667eea;">🎯 Why Your Response Matters</h3>
                    <p>Your input is invaluable in helping us understand and improve educational and community initiatives. Every response contributes to meaningful research that can make a real difference in communities like yours.</p>
                    
                    <div class="steps">
                        <h3 style="color: #b8860b; margin-top: 0;">📝 Quick Steps to Complete</h3>
                        <ol>
                            <li>Visit <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                            <li>Enter your survey code: <strong>{survey_code}</strong></li>
                            <li>Complete the survey at your convenience</li>
                            <li>Submit your responses</li>
                        </ol>
                        <p style="margin-bottom: 0;"><em>⏱️ Typically takes 15-20 minutes • 💾 Save progress and return later</em></p>
                    </div>
                    
                    <div style="background: #e8f4fd; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #1565c0; margin-top: 0;">🆘 Need Help?</h3>
                        <p style="margin-bottom: 0;">If you're experiencing any difficulties or have questions about the survey, please don't hesitate to reach out to our support team. We're here to help!</p>
                    </div>
                    
                    <p>We truly appreciate your time and participation. Your voice matters, and we look forward to receiving your valuable insights.</p>
                    
                    <p style="font-weight: bold; color: #667eea;">Thank you for being part of the Saurara community! 🌟</p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; text-align: center; color: #666; font-size: 14px;">
                        <strong>Best regards,<br>The Saurara Research Team</strong>
                    </p>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 15px 0;">
                    <p style="margin: 0; text-align: center; color: #888; font-size: 12px;">
                        <span class="reminder-tag">REMINDER</span><br><br>
                        This is an automated reminder. If you have already completed the survey, please disregard this message.<br>
                        <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                        <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a>
                    </p>
                </div>
            </div>
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
        
        logger.info(f"Reminder email sent successfully via SMTP to {to_email}")
        return {
            'success': True,
            'method': 'SMTP',
            'message': 'Reminder email sent successfully via SMTP'
        }
        
    except Exception as e:
        logger.error(f"Error sending reminder email via SMTP: {str(e)}")
        return {
            'success': False,
            'error': f"SMTP email sending failed: {str(e)}"
        }

def send_reminder_email(to_email, username, survey_code, firstname=None, organization_name=None, days_remaining=None, organization_id=None, template_id=None, password=None):
    """Send reminder email to user using database template (tries SES API first, falls back to SMTP)"""
    try:
        # Try to get reminder email template from database
        template = None
        use_template = False
        
        # If specific template_id is provided, use that template
        if template_id:
            try:
                template = EmailTemplate.query.get(template_id)
                if template:
                    template_data = {
                        'name': template.name,
                        'subject': template.subject,
                        'html_body': template.html_body,
                        'text_body': template.text_body
                    }
                    use_template = True
                    logger.info(f"Using specific email template ID {template_id}: {template.name}")
            except Exception as e:
                logger.error(f"Error fetching specific email template {template_id}: {str(e)}")
        
        # If no specific template or template not found, use organization-aware lookup
        if not use_template:
            template, status_code, message = get_email_template_by_type_and_organization('reminder', organization_id)
            use_template = status_code == 200
            if use_template:
                template_data = {
                    'name': template.name,
                    'subject': template.subject,
                    'html_body': template.html_body,
                    'text_body': template.text_body
                }
                logger.info(f"Using email template: {template.name} (Org: {template.organization_id})")
            else:
                logger.warning(f"No reminder template found for organization {organization_id}, using fallback")
        
        if use_template:
            subject = template_data['subject']
            
            # Create personalized greeting and template variables
            greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
            org_text = f" from {organization_name}" if organization_name else ""
            deadline_text = f" You have {days_remaining} days remaining to complete it." if days_remaining else ""
            password_text = f"\n• Password: {password}" if password else ""
            
            template_vars = {
                'greeting': greeting,
                'username': username,
                'password': password or '',
                'survey_code': survey_code,
                'org_text': org_text,
                'deadline_text': deadline_text,
                'password_text': password_text
            }
            
            # Render template content
            body_text = render_email_template(template_data['text_body'], **template_vars)
            body_html = render_email_template(template_data['html_body'], **template_vars)
            
            logger.info(f"Using email template: {template_data['name']}")
        else:
            # Fallback to hardcoded content if template not found
            logger.warning("Reminder email template not found, using fallback content")
            subject = "🔔 Reminder: Complete Your Saurara Survey"
            greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
            org_text = f" from {organization_name}" if organization_name else ""
            deadline_text = f" You have {days_remaining} days remaining to complete it." if days_remaining else ""
            
            body_text = f"""{greeting},

We hope this message finds you well!

This is a friendly reminder that you have a pending survey{org_text} on the Saurara Platform that requires your attention.{deadline_text}

Your Survey Details:
• Username: {username}
• Survey Code: {survey_code}
• Survey Link: www.saurara.org

🔑 NEED YOUR PASSWORD?
Your login password was sent in your WELCOME EMAIL when your account was created. 
Please search your email inbox for "Welcome to Saurara Platform" to find your credentials.

If you cannot find your welcome email or need to reset your password, please use the 
"Forgot Password" link on the login page or contact support at info@saurara.org

Best regards,
The Saurara Research Team"""

            body_html = f"""<html><body><h1>Survey Reminder</h1><p>{greeting},</p><p>This is a friendly reminder that you have a pending survey on the Saurara Platform.</p><p><strong>Survey Code:</strong> {survey_code}</p><div style="background: #fff3cd; padding: 15px; margin: 20px 0; border-left: 4px solid #ffc107;"><h3>🔑 Need Your Password?</h3><p>Your login password was sent in your <strong>Welcome Email</strong> when your account was created. Please search your email inbox for "Welcome to Saurara Platform" to find your credentials.</p><p>If you cannot find your welcome email or need to reset your password, please use the "Forgot Password" link on the login page or contact support at info@saurara.org</p></div><p>Visit: www.saurara.org</p><p>Best regards,<br>The Saurara Research Team</p></body></html>"""
        
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining, password)
        
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
        
        logger.info(f"Reminder email sent successfully via SES API to {to_email}. Message ID: {response['MessageId']}")
        return {
            'success': True,
            'method': 'SES_API',
            'message_id': response['MessageId'],
            'message': 'Reminder email sent successfully via SES API'
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"[EMAIL] SES API ClientError: {error_code} - {error_message}")
        logger.warning("[EMAIL] SES API failed, trying SMTP method as fallback...")
        return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining, password)
    except Exception as e:
        logger.error(f"[EMAIL] Error sending reminder email via SES API: {str(e)}")
        logger.warning("[EMAIL] SES API failed, trying SMTP method as fallback...")
        return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining, password)

# Geocoding utility functions
def geocode_address(address_components):
    """
    Geocode an address using multiple components and return latitude, longitude
    
    Args:
        address_components (dict): Dictionary containing address components like:
            - address_line1, address_line2, city, town, province, country, postal_code
    
    Returns:
        tuple: (latitude, longitude) or (None, None) if geocoding fails
    """
    try:
        # Initialize geocoder with a user agent
        geolocator = Nominatim(user_agent="bosko_partners_survey_app")
        
        # Build address string from components
        address_parts = []
        
        # Add address lines
        if address_components.get('address_line1'):
            address_parts.append(address_components['address_line1'])
        if address_components.get('address_line2'):
            address_parts.append(address_components['address_line2'])
        
        # Add city/town
        if address_components.get('city'):
            address_parts.append(address_components['city'])
        elif address_components.get('town'):
            address_parts.append(address_components['town'])
        
        # Add province/state
        if address_components.get('province'):
            address_parts.append(address_components['province'])
        
        # Add country
        if address_components.get('country'):
            address_parts.append(address_components['country'])
        
        # Add postal code
        if address_components.get('postal_code'):
            address_parts.append(address_components['postal_code'])
        
        if not address_parts:
            logger.warning("No address components provided for geocoding")
            return None, None
        
        # Create full address string
        full_address = ', '.join(filter(None, address_parts))
        logger.info(f"Geocoding address: {full_address}")
        
        # Attempt geocoding with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                location = geolocator.geocode(full_address, timeout=10)
                if location:
                    logger.info(f"Successfully geocoded address to: {location.latitude}, {location.longitude}")
                    return float(location.latitude), float(location.longitude)
                else:
                    logger.warning(f"No geocoding results found for address: {full_address}")
                    break
            except GeocoderTimedOut:
                logger.warning(f"Geocoding timeout on attempt {attempt + 1} for address: {full_address}")
                if attempt < max_retries - 1:
                    time_module.sleep(1)  # Wait before retry
                continue
            except GeocoderServiceError as e:
                logger.error(f"Geocoding service error: {str(e)}")
                break
        
        return None, None
        
    except Exception as e:
        logger.error(f"Error during geocoding: {str(e)}")
        return None, None

def update_geo_location_coordinates(geo_location_id):
    """
    Update latitude and longitude for a GeoLocation record if they are zero
    
    Args:
        geo_location_id (int): ID of the GeoLocation record to update
    
    Returns:
        bool: True if coordinates were updated, False otherwise
    """
    try:
        geo_location = GeoLocation.query.get(geo_location_id)
        if not geo_location:
            logger.warning(f"GeoLocation with ID {geo_location_id} not found")
            return False
        
        # Check if coordinates need updating (are zero or None)
        lat = float(geo_location.latitude) if geo_location.latitude else 0
        lng = float(geo_location.longitude) if geo_location.longitude else 0
        
        if lat != 0 or lng != 0:
            logger.info(f"GeoLocation {geo_location_id} already has coordinates: {lat}, {lng}")
            return False
        
        # Prepare address components for geocoding
        address_components = {
            'address_line1': geo_location.address_line1,
            'address_line2': geo_location.address_line2,
            'city': geo_location.city,
            'town': geo_location.town,
            'province': geo_location.province,
            'country': geo_location.country,
            'postal_code': geo_location.postal_code
        }
        
        # Attempt geocoding
        new_lat, new_lng = geocode_address(address_components)
        
        if new_lat is not None and new_lng is not None:
            # Update the database
            geo_location.latitude = new_lat
            geo_location.longitude = new_lng
            db.session.commit()
            
            logger.info(f"Updated GeoLocation {geo_location_id} coordinates to: {new_lat}, {new_lng}")
            return True
        else:
            logger.warning(f"Failed to geocode address for GeoLocation {geo_location_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating coordinates for GeoLocation {geo_location_id}: {str(e)}")
        db.session.rollback()
        return False

def geocode_survey_response_locations(response_data_list):
    """
    Process a list of survey response data and geocode any with zero coordinates
    
    Args:
        response_data_list (list): List of survey response dictionaries
    
    Returns:
        list: Updated list with geocoded coordinates where possible
    """
    try:
        for response_data in response_data_list:
            # Check if coordinates need updating
            lat = response_data.get('latitude', 0)
            lng = response_data.get('longitude', 0)
            
            # Convert to float for comparison
            try:
                lat = float(lat) if lat is not None else 0
                lng = float(lng) if lng is not None else 0
            except (ValueError, TypeError):
                lat = lng = 0
            
            if lat == 0 and lng == 0:
                # Try to geocode using available address information
                # Handle different field names from different endpoints
                address_components = {
                    'address_line1': response_data.get('physical_address') or response_data.get('address_line1'),
                    'city': response_data.get('city'),
                    'town': response_data.get('town'),
                    'province': response_data.get('state') or response_data.get('province'),
                    'country': response_data.get('country'),
                    'postal_code': response_data.get('postal_code')
                }
                
                new_lat, new_lng = geocode_address(address_components)
                
                if new_lat is not None and new_lng is not None:
                    response_data['latitude'] = new_lat
                    response_data['longitude'] = new_lng
                    logger.info(f"Geocoded response {response_data.get('id', 'unknown')} to: {new_lat}, {new_lng}")
        
        return response_data_list
        
    except Exception as e:
        logger.error(f"Error geocoding survey response locations: {str(e)}")
        return response_data_list

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
                "http://18.222.89.189",
                "https://saurara.org",       # production domain
                "http://saurara.org"         # production domain (http fallback)
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

class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=True)
    html_body = db.Column(db.Text, nullable=True)  # Using Text for MEDIUMTEXT compatibility
    text_body = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    organization = db.relationship('Organization', foreign_keys=[organization_id], backref=db.backref('email_templates', lazy=True, cascade='all, delete-orphan'))
    
    # Unique constraint for organization_id + name
    __table_args__ = (
        db.UniqueConstraint('organization_id', 'name', name='uq_org_name'),
        db.Index('idx_email_templates_org', 'organization_id'),
    )
    
    def __repr__(self):
        return f'<EmailTemplate {self.name} (Org: {self.organization_id})>'
    
    def to_dict(self):
        """Convert EmailTemplate to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'organization_id': self.organization_id,
            'organization_name': self.organization.name if self.organization else None,
            'name': self.name,
            'subject': self.subject,
            'html_body': self.html_body,
            'text_body': self.text_body,
            'is_public': self.is_public,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'survey_templates': [],  # No associations needed
            'organization_roles': []  # No associations needed
        }
    





# ---------- Email Template Models (Simplified) ----------


# Title model for the titles table
class Title(db.Model):
    __tablename__ = 'titles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    def __repr__(self):
        return f'<Title {self.name}>'


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'user', 'manager', 'other', 'head', 'root'), default='user')
    firstname = db.Column(db.String(50))
    lastname = db.Column(db.String(50))
    survey_code = db.Column(db.String(36), nullable=True)  # UUID as string for user surveys
    geo_location_id = db.Column(db.Integer, db.ForeignKey('geo_locations.id'), nullable=True)
    phone = db.Column(db.String(20), nullable=True)  # Added for contact information
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)  # New: references titles table
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Password reset fields
    reset_token = db.Column(db.String(128), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    organization = db.relationship('Organization', foreign_keys=[organization_id], backref=db.backref('users', lazy=True))
    geo_location = db.relationship('GeoLocation', foreign_keys=[geo_location_id])
    title = db.relationship('Title', foreign_keys=[title_id], backref=db.backref('users', lazy=True))
    
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

class UserOrganizationTitle(db.Model):
    """
    Maps users to organizations with specific titles.
    Renamed from user_organization_roles to user_organization_titles.
    """
    __tablename__ = 'user_organization_titles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    title_id = db.Column(db.Integer, db.ForeignKey('titles.id'), nullable=True)  # Changed from role_id to title_id
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    
    # Relationships
    user = db.relationship('User', backref=db.backref('organization_titles', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('user_titles', lazy=True))
    title = db.relationship('Title', backref=db.backref('user_organization_assignments', lazy=True))
    
    # Ensure unique combination of user, organization, and title
    __table_args__ = (UniqueConstraint('user_id', 'organization_id', 'title_id'),)

    def __repr__(self):
        return f'<UserOrganizationTitle user_id={self.user_id} org_id={self.organization_id} title_id={self.title_id}>'


# Keep alias for backward compatibility with existing code
UserOrganizationRole = UserOrganizationTitle

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    answers = db.Column(JSON, nullable=False)
    status = db.Column(db.Enum('pending','in_progress','completed'), 
                       nullable=False, default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    survey_code = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    template = db.relationship('SurveyTemplate', backref=db.backref('responses', lazy=True))
    user = db.relationship('User', backref=db.backref('survey_responses', lazy=True))
    
    """
    FIXED - Removed duplicate __repr__ method that was causing Python syntax issues
    """
    def __repr__(self):
        return f'<SurveyResponse {self.id} for template {self.template_id}>'


class ReportTemplate(db.Model):
    __tablename__ = 'report_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    config = db.Column(JSON, nullable=False)  # Store report configuration
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=False)  # Public templates can be used by all admins
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    creator = db.relationship('User', backref=db.backref('report_templates', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'config': self.config,
            'created_by': self.created_by,
            'is_public': self.is_public,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'creator_name': f"{self.creator.firstname} {self.creator.lastname}" if self.creator else "Unknown"
        }

    def __repr__(self):
        return f'<ReportTemplate {self.id}: {self.name}>'


class ContactReferral(db.Model):
    __tablename__ = 'contact_referrals'
    id = db.Column(db.Integer, primary_key=True)
    
    # Primary contact information
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    full_phone = db.Column(db.String(50), nullable=True)
    whatsapp = db.Column(db.String(50), nullable=True)
    preferred_contact = db.Column(db.String(50), nullable=True)
    type_of_institution = db.Column(db.String(100), nullable=True)
    institution_name = db.Column(db.String(255), nullable=True)
    title = db.Column(db.String(100), nullable=True)
    physical_address = db.Column(db.Text, nullable=True)
    country = db.Column(db.String(100), nullable=True)
    
    # Referral tracking
    referred_by_id = db.Column(db.Integer, db.ForeignKey('contact_referrals.id', ondelete='CASCADE'), nullable=True)
    is_primary = db.Column(db.Boolean, default=True)
    
    # Metadata
    device_info = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    location_data = db.Column(JSON, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(),
                           onupdate=db.func.current_timestamp())
    
    # Relationships
    referrals = db.relationship('ContactReferral', 
                               backref=db.backref('referred_by', remote_side=[id]),
                               lazy=True,
                               cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'full_phone': self.full_phone,
            'whatsapp': self.whatsapp,
            'preferred_contact': self.preferred_contact,
            'type_of_institution': self.type_of_institution,
            'institution_name': self.institution_name,
            'title': self.title,
            'physical_address': self.physical_address,
            'country': self.country,
            'referred_by_id': self.referred_by_id,
            'is_primary': self.is_primary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<ContactReferral {self.first_name} {self.last_name}>'


"""
class EmailTemplate(db.Model):
    __tablename__ = 'email_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=True)
    html_body = db.Column(db.Text, nullable=True)
    text_body = db.Column(db.Text, nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    # Relationships
    organization = db.relationship('Organization', backref=db.backref('email_templates', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'subject': self.subject,
            'html_body': self.html_body,
            'text_body': self.text_body,
            'organization_id': self.organization_id,
            'is_public': self.is_public,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<EmailTemplate {self.id}: {self.name}>'
"""

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
        'organization_id': user.organization_id,
        'title': user.title.name if user.title else None,
        'title_id': user.title_id
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
    
    # Log user's geographic information on login
    if user.geo_location_id:
        geo_location = GeoLocation.query.get(user.geo_location_id)
        if geo_location:
            logger.info(f"User {user.id} ({user.username}) logging in with geographic data: lat={geo_location.latitude}, lng={geo_location.longitude}, city={geo_location.city}, country={geo_location.country}")
        else:
            logger.info(f"User {user.id} ({user.username}) has geo_location_id {user.geo_location_id} but no geo location found")
    else:
        logger.info(f"User {user.id} ({user.username}) has no geo_location_id")
    
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
            "survey_code": user.survey_code,  # Include survey code for users
            "title": user.title.name if user.title else None,  # Include title name
            "title_id": user.title_id  # Include title ID
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
            # Support legacy shape (region/church/school) and new form shape (province/city/address_line1)
            legacy_ok = bool(org.get('country') and org.get('region') and org.get('church') and org.get('school'))
            newform_ok = bool(org.get('country') and org.get('province') and org.get('city') and org.get('address_line1'))
            organizational_filled = legacy_ok or newform_ok
        
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
    """Delete a template version and all its associated templates"""
    try:
        version = SurveyTemplateVersion.query.get_or_404(version_id)
        
        # First, find all templates that reference this version
        templates = SurveyTemplate.query.filter_by(version_id=version_id).all()
        template_ids = [t.id for t in templates]
        
        deleted_counts = {
            'templates': 0,
            'responses': 0,
            'conditional_logic': 0
        }
        
        if template_ids:
            logger.info(f"Found {len(template_ids)} templates to delete for version {version_id}")
            
            # Delete associated records in proper order to avoid foreign key constraints
            
            # 1. Delete conditional_logic records that reference these templates
            try:
                if len(template_ids) == 1:
                    conditional_logic_result = db.session.execute(
                        text("DELETE FROM conditional_logic WHERE template_id = :template_id"),
                        {"template_id": template_ids[0]}
                    )
                else:
                    conditional_logic_result = db.session.execute(
                        text("DELETE FROM conditional_logic WHERE template_id IN :template_ids"),
                        {"template_ids": tuple(template_ids)}
                    )
                deleted_counts['conditional_logic'] = conditional_logic_result.rowcount
                logger.info(f"Deleted {deleted_counts['conditional_logic']} conditional_logic records")
            except Exception as e:
                logger.warning(f"Error deleting conditional_logic records: {str(e)}")
            
            # 2. Delete survey_responses that reference these templates
            try:
                if len(template_ids) == 1:
                    responses_result = db.session.execute(
                        text("DELETE FROM survey_responses WHERE template_id = :template_id"),
                        {"template_id": template_ids[0]}
                    )
                else:
                    responses_result = db.session.execute(
                        text("DELETE FROM survey_responses WHERE template_id IN :template_ids"),
                        {"template_ids": tuple(template_ids)}
                    )
                deleted_counts['responses'] = responses_result.rowcount
                logger.info(f"Deleted {deleted_counts['responses']} survey_responses records")
            except Exception as e:
                logger.warning(f"Error deleting survey_responses records: {str(e)}")
            
            # 3. Delete the survey templates
            for template in templates:
                db.session.delete(template)
                deleted_counts['templates'] += 1
            
            logger.info(f"Deleted {deleted_counts['templates']} survey templates")
        
        # 4. Finally, delete the template version
        db.session.delete(version)
        db.session.commit()
        
        logger.info(f"Successfully deleted template version {version_id} and all associated records")
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
    organization_id = request.args.get('organization_id', type=int)
    query = SurveyTemplate.query
    if organization_id:
        # Join with SurveyTemplateVersion to filter by organization_id
        query = query.join(SurveyTemplateVersion).filter(SurveyTemplateVersion.organization_id == organization_id)
    templates = query.all()
    
    # If no templates exist, create a default one
    if len(templates) == 0:
        try:
            # Check if there's at least one template version
            template_version = SurveyTemplateVersion.query.first()
            if not template_version:
                # Create a default template version
                default_org = Organization.query.first()
                if default_org:
                    template_version = SurveyTemplateVersion(
                        name="Default Survey Template",
                        description="Default template for survey responses",
                        organization_id=default_org.id
                    )
                    db.session.add(template_version)
                    db.session.flush()
            
            if template_version:
                # Create a default template
                default_template = SurveyTemplate(
                    version_id=template_version.id,
                    survey_code=f"default_template_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    questions=[]
                )
                db.session.add(default_template)
                db.session.commit()
                templates = [default_template]
                logger.info("Created default survey template")
        except Exception as e:
            logger.error(f"Error creating default template: {str(e)}")
            db.session.rollback()
    
    return jsonify([{
        "id": t.id, 
        "version_id": t.version_id,
        "version_name": t.version.name if t.version else "Default",
        "survey_code": t.survey_code,
        "created_at": t.created_at
    } for t in templates]), 200

@app.route('/api/survey-templates/available', methods=['GET'])
def get_available_survey_templates():
    """Get all available survey templates with complete information for users"""
    try:
        # Query to get templates with their versions and organization info
        templates_query = db.session.query(
            SurveyTemplate.id.label('template_id'),
            SurveyTemplate.survey_code,
            SurveyTemplate.questions,
            SurveyTemplate.sections,
            SurveyTemplate.created_at.label('template_created_at'),
            SurveyTemplateVersion.id.label('version_id'),
            SurveyTemplateVersion.name.label('version_name'),
            SurveyTemplateVersion.description.label('version_description'),
            Organization.id.label('organization_id'),
            Organization.name.label('organization_name'),
            OrganizationType.type.label('organization_type')
        ).join(
            SurveyTemplateVersion, SurveyTemplate.version_id == SurveyTemplateVersion.id
        ).join(
            Organization, SurveyTemplateVersion.organization_id == Organization.id
        ).join(
            OrganizationType, Organization.type == OrganizationType.id
        ).all()
        
        templates_data = []
        for template in templates_query:
            # Count questions and sections
            questions = template.questions or []
            sections = template.sections or {}
            
            template_data = {
                'id': template.template_id,
                'survey_code': template.survey_code,
                'version': {
                    'id': template.version_id,
                    'name': template.version_name,
                    'description': template.version_description,
                    'organization': {
                        'id': template.organization_id,
                        'name': template.organization_name,
                        'organization_type': {
                            'type': template.organization_type
                        }
                    }
                },
                'questions_count': len(questions),
                'sections_count': len(sections) if isinstance(sections, dict) else 0,
                'questions': questions,
                'sections': sections,
                'created_at': template.template_created_at.isoformat() if template.template_created_at else None
            }
            templates_data.append(template_data)
        
        return jsonify(templates_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching available survey templates: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch survey templates: {str(e)}'}), 500

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
        "sections": template.sections,
        "created_at": template.created_at
    }), 200


@app.route('/api/templates/<int:template_id>', methods=['PUT'])
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
        
        # Validate that all questions have required fields - make validation more flexible
        for i, question in enumerate(data['questions']):
            # Check for essential fields but be more flexible about what's required
            if not question.get('question_text'):
                logger.error(f"Question {i} missing question_text: {question}")
                return jsonify({'error': f'Question {i+1}: question_text is required'}), 400
            if not question.get('question_type_id'):
                logger.error(f"Question {i} missing question_type_id: {question}")
                return jsonify({'error': f'Question {i+1}: question_type_id is required'}), 400
            # Ensure order exists, default to index if missing
            if 'order' not in question:
                question['order'] = i
            # Ensure id exists, generate one if missing
            if 'id' not in question:
                question['id'] = f"q_{i}_{int(time.time())}"
        
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

@app.route('/api/templates/<int:template_id>/copy', methods=['POST'])
def copy_template_to_organization(template_id):
    """Copy a template to another organization's template version"""
    try:
        data = request.get_json() or {}
        required_keys = ['target_organization_id']
        
        if not all(k in data for k in required_keys):
            return jsonify({'error': 'Missing required fields: target_organization_id'}), 400
        
        target_organization_id = data['target_organization_id']
        target_version_name = data.get('target_version_name', 'Copied Templates')
        new_survey_code = data.get('new_survey_code', '')
        
        # Get the source template
        source_template = SurveyTemplate.query.get_or_404(template_id)
        
        # Verify target organization exists
        target_organization = Organization.query.get(target_organization_id)
        if not target_organization:
            return jsonify({'error': 'Target organization not found'}), 404
        
        # Find or create a template version for the target organization
        target_version = SurveyTemplateVersion.query.filter_by(
            organization_id=target_organization_id,
            name=target_version_name
        ).first()
        
        if not target_version:
            # Create a new template version for the target organization
            target_version = SurveyTemplateVersion(
                name=target_version_name,
                description=f"Templates copied from {source_template.version.organization.name}",
                organization_id=target_organization_id
            )
            db.session.add(target_version)
            db.session.flush()  # Get the ID
        
        # Check if we should update an existing template or create a new one
        existing_template = None
        if new_survey_code:
            # If a survey code is provided, check if it exists in the target version
            existing_template = SurveyTemplate.query.filter_by(
                version_id=target_version.id,
                survey_code=new_survey_code
            ).first()
        
        if existing_template:
            # Update existing template with new questions and sections
            existing_template.questions = source_template.questions  # Deep copy of questions
            existing_template.sections = source_template.sections    # Deep copy of sections
            copied_template = existing_template
            action = 'updated'
            logger.info(f"Updated existing template {existing_template.id} in version {target_version.id}")
        else:
            # Generate unique survey code if not provided
            if not new_survey_code:
                new_survey_code = f"{source_template.survey_code}_copy_to_{target_organization.name.lower().replace(' ', '_')}"
            
            # Ensure the survey code is unique across all templates
            counter = 1
            original_survey_code = new_survey_code
            while True:
                existing = SurveyTemplate.query.filter_by(survey_code=new_survey_code).first()
                if not existing:
                    break
                new_survey_code = f"{original_survey_code}_{counter}"
                counter += 1
            
            # Create the copied template
            copied_template = SurveyTemplate(
                version_id=target_version.id,
                survey_code=new_survey_code,
                questions=source_template.questions,  # Deep copy of questions
                sections=source_template.sections     # Deep copy of sections
            )
            
            db.session.add(copied_template)
            action = 'created'
            logger.info(f"Created new template {new_survey_code} in version {target_version.id}")
        
        db.session.commit()
        
        logger.info(f"Template {template_id} copied to organization {target_organization_id} as template {copied_template.id}")
        
        return jsonify({
            'success': True,
            'action': action,
            'copied_template': {
                'id': copied_template.id,
                'survey_code': copied_template.survey_code,
                'version_id': copied_template.version_id,
                'version_name': target_version.name,
                'organization_id': target_organization_id,
                'organization_name': target_organization.name
            },
            'message': f'Template successfully {action} in {target_organization.name}'
        }), 201 if action == 'created' else 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error copying template {template_id}: {str(e)}")
        return jsonify({'error': f'Failed to copy template: {str(e)}'}), 500

# Survey Responses API Endpoints
@app.route('/api/responses', methods=['GET'])
def get_responses():
    responses = SurveyResponse.query.all()
    return jsonify([{
        "id": r.id,
        "template_id": r.template_id,
        "user_id": r.user_id,
        "status": r.status,
        "survey_code": r.survey_code,
        "start_date": r.start_date.isoformat() if r.start_date else None,
        "end_date": r.end_date.isoformat() if r.end_date else None,
        "created_at": r.created_at
    } for r in responses]), 200


@app.route('/api/templates/<int:template_id>/responses', methods=['POST'])
def add_response(template_id):
    """Create or update a survey response (Save Draft should update existing)."""
    data = request.get_json() or {}
    if 'user_id' not in data or 'answers' not in data:
        return jsonify({'error': 'Missing required fields'}), 400

    # Parse date fields if provided
    start_date = None
    end_date = None

    if data.get('start_date'):
        try:
            start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
        except ValueError:
            try:
                start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid start_date format'}), 400

    if data.get('end_date'):
        try:
            end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
        except ValueError:
            try:
                end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid end_date format'}), 400

    # Check if a response already exists for this user and template
    existing_response = SurveyResponse.query.filter_by(
        template_id=template_id,
        user_id=data['user_id']
    ).first()

    if existing_response:
        # Update existing response (Save Draft behavior)
        existing_response.answers = data['answers']
        if 'status' in data and data['status']:
            existing_response.status = data['status']
        if start_date is not None:
            existing_response.start_date = start_date
        if end_date is not None:
            existing_response.end_date = end_date
        db.session.commit()
        return jsonify({
            'id': existing_response.id,
            'status': existing_response.status,
            'start_date': existing_response.start_date.isoformat() if existing_response.start_date else None,
            'end_date': existing_response.end_date.isoformat() if existing_response.end_date else None
        }), 200

    # Otherwise create a new response
    response = SurveyResponse(
        template_id=template_id,
        user_id=data['user_id'],
        answers=data['answers'],
        status=data.get('status', 'pending'),
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(response)
    db.session.commit()
    return jsonify({
        'id': response.id,
        'status': response.status,
        'start_date': response.start_date.isoformat() if response.start_date else None,
        'end_date': response.end_date.isoformat() if response.end_date else None
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
        "survey_code": response.survey_code,
        "start_date": response.start_date.isoformat() if response.start_date else None,
        "end_date": response.end_date.isoformat() if response.end_date else None,
        "created_at": response.created_at,
        "updated_at": response.updated_at
    }), 200


@app.route('/api/responses/<int:response_id>', methods=['PUT'])
def update_response(response_id):
    response = SurveyResponse.query.get_or_404(response_id)
    data = request.get_json() or {}
    
    for field in ['answers', 'status', 'start_date', 'end_date']:
        if field in data:
            if field in ['start_date', 'end_date'] and data[field]:
                # Parse datetime string to datetime object
                try:
                    setattr(response, field, datetime.fromisoformat(data[field].replace('Z', '+00:00')))
                except ValueError:
                    try:
                        setattr(response, field, datetime.strptime(data[field], '%Y-%m-%d'))
                    except ValueError:
                        return jsonify({'error': f'Invalid date format for {field}'}), 400
            else:
                setattr(response, field, data[field])
    
    db.session.commit()
    return jsonify({'updated': True}), 200

@app.route('/api/responses/<int:response_id>/dates', methods=['PUT'])
def update_response_dates(response_id):
    """Update start_date and end_date for a survey response"""
    try:
        response = SurveyResponse.query.get_or_404(response_id)
        data = request.get_json() or {}
        
        updated = False
        
        # Update start_date if provided
        if 'start_date' in data:
            if data['start_date']:
                try:
                    response.start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
                except ValueError:
                    try:
                        response.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d')
                    except ValueError:
                        return jsonify({'error': 'Invalid start_date format'}), 400
                updated = True
            else:
                response.start_date = None
                updated = True
        
        # Update end_date if provided
        if 'end_date' in data:
            if data['end_date']:
                try:
                    response.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
                except ValueError:
                    try:
                        response.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d')
                    except ValueError:
                        return jsonify({'error': 'Invalid end_date format'}), 400
                updated = True
            else:
                response.end_date = None
                updated = True
        
        if not updated:
            return jsonify({'error': 'No date fields provided'}), 400
        
        db.session.commit()
        
        return jsonify({
            'updated': True,
            'start_date': response.start_date.isoformat() if response.start_date else None,
            'end_date': response.end_date.isoformat() if response.end_date else None
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating response dates: {str(e)}")
        return jsonify({'error': f'Failed to update dates: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/templates/<int:template_id>/response', methods=['GET'])
def get_user_template_response(user_id, template_id):
    """Get existing survey response for a specific user and template"""
    try:
        response = SurveyResponse.query.filter_by(
            user_id=user_id,
            template_id=template_id
        ).first()
        
        if response:
            return jsonify({
                "id": response.id,
                "template_id": response.template_id,
                "user_id": response.user_id,
                "answers": response.answers,
                "status": response.status,
                "survey_code": response.survey_code,
                "start_date": response.start_date.isoformat() if response.start_date else None,
                "end_date": response.end_date.isoformat() if response.end_date else None,
                "created_at": response.created_at.isoformat() if response.created_at else None,
                "updated_at": response.updated_at.isoformat() if response.updated_at else None
            }), 200
        else:
            return jsonify({'error': 'No survey response found for this user and template'}), 404
            
    except Exception as e:
        logger.error(f"Error getting user template response: {str(e)}")
        return jsonify({'error': f'Failed to get survey response: {str(e)}'}), 500

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
    return jsonify({
        'organization_types': [{
            'id': ot.id,
            'type': ot.type
        } for ot in org_types]
    }), 200

@app.route('/api/organization-types', methods=['POST'])
def add_organization_type():
    try:
        data = request.get_json()
        logger.info(f"Adding organization type with data: {data}")
        
        if 'type' not in data:
            return jsonify({'error': 'type is required'}), 400
        
        type_name = data['type'].strip()  # Keep original case
        
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
        
        # Add the required types with proper capitalization
        types = ['CHURCH', 'School', 'OTHER', 'Institution', 'Non_formal_organizations']
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
            'organization_type': {
                'id': org.organization_type.id,
                'type': org.organization_type.type
            } if org.organization_type else None,
            'geo_location': {
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
            'website': org.website,
            'denomination_affiliation': org.details.get('denomination_affiliation') if org.details else None,
            'accreditation_status_or_body': org.details.get('accreditation_status_or_body') if org.details else None,
            'highest_level_of_education': org.highest_level_of_education,
            'affiliation_validation': org.details.get('affiliation_validation') if org.details else None,
            'umbrella_association_membership': org.details.get('umbrella_association_membership') if org.details else None,

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
        
        # Check if this is a main organization type that should get a survey template
        org_type = None
        if data.get('type_id'):
            org_type = OrganizationType.query.get(data['type_id'])
        create_survey_template = org_type and org_type.type in ['CHURCH', 'Non_formal_organizations', 'Institution']
        
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
            type=data.get('type_id'),  # Using type_id from request
            address=geo_location_id,
            primary_contact=primary_contact_id or existing_primary_contact_id,
            secondary_contact=secondary_contact_id or existing_secondary_contact_id,
            head=lead_id or existing_head_id,
            website=data.get('website'),
            highest_level_of_education=data.get('highest_level_of_education'),
            details=data.get('details', {})  # Using details from request
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
        
        # Create user_organization_titles entries for assigned contacts (renamed from user_organization_roles)
        def add_user_organization_title(user_id, title_name):
            if user_id:
                title = Title.query.filter_by(name=title_name).first()
                if title:
                    # Check if title assignment already exists
                    existing_title = UserOrganizationTitle.query.filter_by(
                        user_id=user_id,
                        organization_id=new_org.id,
                        title_id=title.id
                    ).first()
                    
                    if not existing_title:
                        user_org_title = UserOrganizationTitle(
                            user_id=user_id,
                            organization_id=new_org.id,
                            title_id=title.id
                        )
                        db.session.add(user_org_title)
                        logger.info(f"Added {title_name} title for user {user_id} in organization {new_org.id}")
                else:
                    logger.warning(f"Title {title_name} not found in database")
        
        # Add organizational titles for all contacts (both new and existing)
        final_primary_id = primary_contact_id or existing_primary_contact_id
        final_secondary_id = secondary_contact_id or existing_secondary_contact_id
        final_head_id = lead_id or existing_head_id
        
        add_user_organization_title(final_primary_id, 'Primary Contact')
        add_user_organization_title(final_secondary_id, 'Secondary Contact')
        add_user_organization_title(final_head_id, 'Leader')
        
        # Only create survey template version for main organization types
        if create_survey_template:
            logger.info(f"Creating survey template version for main organization type: {org_type.type}")
            # Create initial survey template version
            template_version = SurveyTemplateVersion(
                name=f"{new_org.name} - Initial Survey",
                description=f"Initial survey template for {new_org.name}",
                organization_id=new_org.id
            )
            db.session.add(template_version)
            db.session.flush()
            
            # Create initial survey template
            template = SurveyTemplate(
                version_id=template_version.id,
                survey_code=str(uuid.uuid4()),
                questions=[],  # Empty questions array to be filled later
                sections=[]    # Empty sections array to be filled later
            )
            db.session.add(template)
            logger.info(f"Created survey template version for organization {new_org.id}")
        
        db.session.commit()
        logger.info(f"Successfully created organization with ID: {new_org.id}")
        
        # Return template version ID only if it was created
        response_data = {
            'message': 'Organization added successfully',
            'id': new_org.id
        }
        if create_survey_template:
            response_data['template_version_id'] = template_version.id
            
        return jsonify(response_data), 201
        
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
    """Delete an organization and all related records"""
    try:
        org = Organization.query.get_or_404(org_id)
        logger.info(f"Deleting organization {org_id} ({org.name})")
        
        # Delete records in the correct order to handle foreign key constraints
        deleted_counts = {
            'survey_responses': 0,
            'survey_templates': 0,
            'template_versions': 0,
            'users': 0,
            'user_details': 0,
            'user_organization_roles': 0,
            'geo_locations': 0,
            'geo_location_references_cleared': 0,
            'organization_references': 0
        }
        
        # 1. Get all template versions for this organization
        template_versions = SurveyTemplateVersion.query.filter_by(organization_id=org_id).all()
        
        for template_version in template_versions:
            # Get all templates for this version
            templates = SurveyTemplate.query.filter_by(version_id=template_version.id).all()
            
            for template in templates:
                # Delete survey responses for this template
                survey_responses = SurveyResponse.query.filter_by(template_id=template.id).all()
                for response in survey_responses:
                    db.session.delete(response)
                deleted_counts['survey_responses'] += len(survey_responses)
                
                # Delete the template
                db.session.delete(template)
                deleted_counts['survey_templates'] += 1
            
            # Delete the template version
            db.session.delete(template_version)
            deleted_counts['template_versions'] += 1
        
        # 2. Handle users associated with this organization
        org_users = User.query.filter_by(organization_id=org_id).all()
        for user in org_users:
            # Delete user details
            user_details = UserDetails.query.filter_by(user_id=user.id).all()
            for detail in user_details:
                db.session.delete(detail)
            deleted_counts['user_details'] += len(user_details)
            
            # Delete user organizational roles
            user_org_roles = UserOrganizationRole.query.filter_by(user_id=user.id).all()
            for role in user_org_roles:
                db.session.delete(role)
            deleted_counts['user_organization_roles'] += len(user_org_roles)
            
            # Delete user's geo location if it exists
            if user.geo_location_id:
                geo_location = GeoLocation.query.get(user.geo_location_id)
                if geo_location:
                    db.session.delete(geo_location)
                    deleted_counts['geo_locations'] += 1
            
            # Set the user's organization_id to NULL instead of deleting the user
            user.organization_id = None
            logger.info(f"Removed organization association for user {user.id} ({user.username})")
        
        # 3. Handle geo location for the organization (save ID for later deletion)
        org_geo_location_id = org.address if org.address else None
        
        # 3.5. Handle ALL geo_locations that reference this organization
        # Set organization_id to NULL for any geo_locations pointing to this org
        geo_locations_referencing_org = GeoLocation.query.filter_by(organization_id=org_id).all()
        for geo_loc in geo_locations_referencing_org:
            geo_loc.organization_id = None
        
        # Update count for geo_location references cleared (not deletions)
        deleted_counts['geo_location_references_cleared'] = len(geo_locations_referencing_org)
        
        # 4. Update other organizations that might reference this one
        # Handle parent_organization references
        child_organizations = Organization.query.filter_by(parent_organization=org_id).all()
        for child_org in child_organizations:
            child_org.parent_organization = None
            deleted_counts['organization_references'] += 1
        
        # 5. Clear the organization's address reference to avoid foreign key constraint
        if org.address:
            org.address = None
        
        # 6. Delete the organization itself first (removes foreign key references)
        db.session.delete(org)
        
        # 7. Now delete the organization's geo location (after removing the reference)
        if org_geo_location_id:
            geo_location = GeoLocation.query.get(org_geo_location_id)
            if geo_location:
                db.session.delete(geo_location)
                deleted_counts['geo_locations'] += 1
        db.session.commit()
        
        logger.info(f"Successfully deleted organization {org_id} and related records: {deleted_counts}")
        
        return jsonify({
            'message': 'Organization and all related data deleted successfully',
            'organization_id': org_id,
            'organization_name': org.name,
            'deleted_counts': deleted_counts,
            'warning': 'All survey templates, responses, and related data for this organization have been permanently deleted.'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting organization {org_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to delete organization: {str(e)}'}), 500

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

# Get user's associated organizations
@app.route('/api/users/<int:user_id>/organizations', methods=['GET'])
def get_user_organizations(user_id):
    """Get organizations associated with a specific user"""
    try:
        # Get the user
        user = User.query.get_or_404(user_id)
        logger.info(f"Fetching organizations for user {user_id}")
        
        # Log user's geographic information
        if user.geo_location_id:
            user_geo = GeoLocation.query.get(user.geo_location_id)
            if user_geo:
                logger.info(f"User {user_id} geographic data: lat={user_geo.latitude}, lng={user_geo.longitude}, city={user_geo.city}, country={user_geo.country}")
            else:
                logger.info(f"User {user_id} has geo_location_id {user.geo_location_id} but no geo location found")
        else:
            logger.info(f"User {user_id} has no geo_location_id")
        
        # Get user's primary organization
        organizations = []
        if user.organization_id:
            primary_org = Organization.query.get(user.organization_id)
            if primary_org:
                # Log organization's geographic information
                if primary_org.geo_location:
                    logger.info(f"Primary organization {primary_org.id} geographic data: lat={primary_org.geo_location.latitude}, lng={primary_org.geo_location.longitude}, city={primary_org.geo_location.city}, country={primary_org.geo_location.country}")
                else:
                    logger.info(f"Primary organization {primary_org.id} has no geo_location")
                
                organizations.append({
                    'id': primary_org.id,
                    'name': primary_org.name,
                    'organization_type': {
                        'type': primary_org.organization_type.type if primary_org.organization_type else None
                    },
                    'geo_location': {
                        'city': primary_org.geo_location.city if primary_org.geo_location else None,
                        'country': primary_org.geo_location.country if primary_org.geo_location else None,
                        'latitude': primary_org.geo_location.latitude if primary_org.geo_location else None,
                        'longitude': primary_org.geo_location.longitude if primary_org.geo_location else None
                    } if primary_org.geo_location else None,
                    'is_primary': True
                })
        
        # Get additional organizations through user_organization_roles
        additional_orgs = db.session.query(Organization).join(
            UserOrganizationRole, Organization.id == UserOrganizationRole.organization_id
        ).filter(
            UserOrganizationRole.user_id == user_id,
            Organization.id != user.organization_id  # Exclude primary org to avoid duplicates
        ).all()
        
        for org in additional_orgs:
            # Log organization's geographic information
            if org.geo_location:
                logger.info(f"Additional organization {org.id} geographic data: lat={org.geo_location.latitude}, lng={org.geo_location.longitude}, city={org.geo_location.city}, country={org.geo_location.country}")
            else:
                logger.info(f"Additional organization {org.id} has no geo_location")
            
            organizations.append({
                'id': org.id,
                'name': org.name,
                'organization_type': {
                    'type': org.organization_type.type if org.organization_type else None
                },
                'geo_location': {
                    'city': org.geo_location.city if org.geo_location else None,
                    'country': org.geo_location.country if org.geo_location else None,
                    'latitude': org.geo_location.latitude if org.geo_location else None,
                    'longitude': org.geo_location.longitude if org.geo_location else None
                } if org.geo_location else None,
                'is_primary': False
            })
        
        logger.info(f"Returning {len(organizations)} organizations for user {user_id}")
        return jsonify({
            'organizations': organizations,
            'count': len(organizations)
        })
        
    except Exception as e:
        logger.error(f"Error fetching organizations for user {user_id}: {str(e)}")
        return jsonify({'error': f'Failed to fetch user organizations: {str(e)}'}), 500

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

# Organization Email Service Configuration Endpoints
@app.route('/api/organizations/<int:org_id>/email-service-status', methods=['GET'])
def get_organization_email_service_status(org_id):
    """Get email service status for an organization"""
    try:
        org = Organization.query.get_or_404(org_id)
        
        # Email service is always active for existing organizations
        return jsonify({
            'success': True,
            'isActive': True,
            'message': "Email service is active",
            'organization_id': org_id
        }), 200
    except Exception as e:
        logger.error(f"Error getting email service status for organization {org_id}: {str(e)}")
        return jsonify({'error': f'Failed to get email service status: {str(e)}'}), 500

@app.route('/api/organizations/<int:org_id>/email-service-config', methods=['GET'])
def get_organization_email_service_config(org_id):
    """Get email service configuration for an organization"""
    try:
        org = Organization.query.get_or_404(org_id)
        
        return jsonify({
            'success': True,
            'organization_id': org_id,
            'organization_name': org.name
        }), 200
    except Exception as e:
        logger.error(f"Error getting email service config for organization {org_id}: {str(e)}")
        return jsonify({'error': f'Failed to get email service config: {str(e)}'}), 500

@app.route('/api/organizations/<int:org_id>/email-service-config', methods=['PUT'])
def update_organization_email_service_config(org_id):
    """Update email service configuration for an organization"""
    try:
        org = Organization.query.get_or_404(org_id)
        
        # Email service is always active, no configuration needed
        return jsonify({
            'success': True,
            'message': 'Email service is always active for organizations',
            'organization_id': org_id
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email service config for organization {org_id}: {str(e)}")
        return jsonify({'error': f'Failed to update email service config: {str(e)}'}), 500

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

@app.route('/api/template-versions/<int:version_id>/copy', methods=['POST'])
def copy_template_version_to_organization(version_id):
    """Copy a template version and all its templates to another organization"""
    try:
        data = request.get_json() or {}
        required_keys = ['target_organization_id']
        
        if not all(k in data for k in required_keys):
            return jsonify({'error': 'Missing required fields: target_organization_id'}), 400
        
        target_organization_id = data['target_organization_id']
        new_version_name = data.get('new_version_name', '')
        
        # Get the source template version
        source_version = SurveyTemplateVersion.query.get_or_404(version_id)
        
        # Verify target organization exists
        target_organization = Organization.query.get(target_organization_id)
        if not target_organization:
            return jsonify({'error': 'Target organization not found'}), 404
        
        # Prevent copying to the same organization
        if source_version.organization_id == target_organization_id:
            return jsonify({'error': 'Cannot copy template version to the same organization'}), 400
        
        # Check if we should update an existing version or create a new one
        existing_version = None
        if new_version_name:
            # If a version name is provided, check if it exists in the target organization
            existing_version = SurveyTemplateVersion.query.filter_by(
                organization_id=target_organization_id,
                name=new_version_name
            ).first()
        
        if existing_version:
            # Use the existing version
            copied_version = existing_version
            version_action = 'updated'
            logger.info(f"Using existing template version {existing_version.id} in organization {target_organization_id}")
        else:
            # Generate new version name if not provided
            if not new_version_name:
                new_version_name = f"{source_version.name}_copy_from_{source_version.organization.name.lower().replace(' ', '_')}"
            
            # Ensure the version name is unique for the target organization
            counter = 1
            original_version_name = new_version_name
            while True:
                existing = SurveyTemplateVersion.query.filter_by(
                    organization_id=target_organization_id,
                    name=new_version_name
                ).first()
                if not existing:
                    break
                new_version_name = f"{original_version_name}_{counter}"
                counter += 1
            
            # Create the copied template version
            copied_version = SurveyTemplateVersion(
                name=new_version_name,
                description=f"Copy of '{source_version.name}' from {source_version.organization.name}",
                organization_id=target_organization_id
            )
            
            db.session.add(copied_version)
            db.session.flush()  # Get the ID
            version_action = 'created'
            logger.info(f"Created new template version {new_version_name} in organization {target_organization_id}")
        
        # Get all templates in the source version
        source_templates = SurveyTemplate.query.filter_by(version_id=version_id).all()
        
        copied_templates = []
        templates_created = 0
        templates_updated = 0
        
        for source_template in source_templates:
            # Use the original survey code to check for existing template in target version
            new_survey_code = source_template.survey_code
            
            # Check if template with this survey code already exists in the target version
            existing_template = SurveyTemplate.query.filter_by(
                version_id=copied_version.id,
                survey_code=new_survey_code
            ).first()
            
            if existing_template:
                # Update existing template
                existing_template.questions = source_template.questions
                existing_template.sections = source_template.sections
                template_action = 'updated'
                templates_updated += 1
                copied_templates.append({
                    'original_id': source_template.id,
                    'original_survey_code': source_template.survey_code,
                    'new_survey_code': new_survey_code,
                    'action': 'updated'
                })
                logger.info(f"Updated existing template {existing_template.id} with survey code {new_survey_code}")
            else:
                # Ensure the survey code is unique across all templates
                template_counter = 1
                original_survey_code = new_survey_code
                while True:
                    existing_any = SurveyTemplate.query.filter_by(survey_code=new_survey_code).first()
                    if not existing_any:
                        break
                    new_survey_code = f"{original_survey_code}_{template_counter}"
                    template_counter += 1
                
                # Create the copied template
                copied_template = SurveyTemplate(
                    version_id=copied_version.id,
                    survey_code=new_survey_code,
                    questions=source_template.questions,  # Deep copy of questions
                    sections=source_template.sections     # Deep copy of sections
                )
                
                db.session.add(copied_template)
                template_action = 'created'
                templates_created += 1
                copied_templates.append({
                    'original_id': source_template.id,
                    'original_survey_code': source_template.survey_code,
                    'new_survey_code': new_survey_code,
                    'action': 'created'
                })
                logger.info(f"Created new template with survey code {new_survey_code}")
        
        db.session.commit()
        
        logger.info(f"Template version {version_id} copied to organization {target_organization_id} as version {copied_version.id} with {len(copied_templates)} templates")
        
        return jsonify({
            'success': True,
            'version_action': version_action,
            'copied_version': {
                'id': copied_version.id,
                'name': copied_version.name,
                'description': copied_version.description,
                'organization_id': target_organization_id,
                'organization_name': target_organization.name,
                'template_count': len(copied_templates),
                'templates_created': templates_created,
                'templates_updated': templates_updated
            },
            'copied_templates': copied_templates,
            'message': f'Template version {version_action} in {target_organization.name}: {templates_created} templates created, {templates_updated} templates updated'
        }), 201 if version_action == 'created' else 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error copying template version {version_id}: {str(e)}")
        return jsonify({'error': f'Failed to copy template version: {str(e)}'}), 500

@app.route('/api/templates/<int:template_id>/sections', methods=['GET'])
def get_template_sections(template_id):
    #Get sections for a template with their order
    template = SurveyTemplate.query.get_or_404(template_id)
    
    # Get sections from template.sections or derive from questions
    if template.sections and isinstance(template.sections, dict) and len(template.sections) > 0:
        sections = template.sections
    else:
        # Derive sections from questions
        sections = {}
        for question in (template.questions or []):
            section_name = question.get('section', 'Uncategorized')
            if section_name and section_name != 'Uncategorized':
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
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'firstname': user.firstname,
            'lastname': user.lastname,
            'organization_id': user.organization_id,
            'phone': user.phone,
            'created_at': user.created_at.isoformat() if user.created_at else None
        }
        
        # Add display role and organizational role info
        if user.role == 'other':
            # Get organizational role for display
            org_role = UserOrganizationRole.query.filter_by(user_id=user.id).first()
            if org_role and org_role.role:
                user_data['display_role'] = org_role.role.name
                user_data['ui_role'] = org_role.role.name  # For frontend compatibility
            else:
                user_data['display_role'] = 'other'
                user_data['ui_role'] = 'other'
        else:
            user_data['display_role'] = user.role
            user_data['ui_role'] = user.role
        
        # Include template_id from survey response if available
        survey_response = SurveyResponse.query.filter_by(user_id=user.id).first()
        user_data['template_id'] = survey_response.template_id if survey_response else None
        
        # Include organization info if available
        if user.organization:
            user_data['organization_name'] = user.organization.name
            user_data['organization'] = {
                'id': user.organization.id,
                'name': user.organization.name,
                'website': user.organization.website,
                'organization_type': {
                    'id': user.organization.organization_type.id,
                    'type': user.organization.organization_type.type
                } if user.organization.organization_type else None
            }
        
        # Include geo location info if available
        if user.geo_location:
            user_data['geo_location'] = {
                'continent': user.geo_location.continent,
                'region': user.geo_location.region,
                'country': user.geo_location.country,
                'province': user.geo_location.province,
                'city': user.geo_location.city,
                'town': user.geo_location.town,
                'address_line1': user.geo_location.address_line1,
                'address_line2': user.geo_location.address_line2,
                'postal_code': user.geo_location.postal_code,
                'latitude': float(user.geo_location.latitude) if user.geo_location.latitude else 0,
                'longitude': float(user.geo_location.longitude) if user.geo_location.longitude else 0
            }
        
        result.append(user_data)
    return jsonify(result)


@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Note: OrganizationUserRole has been removed
    # No roles will be included in the response
    
    # Get the user's survey response to include template_id
    survey_response = SurveyResponse.query.filter_by(user_id=user_id).first()
    template_id = survey_response.template_id if survey_response else None
    
    result = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'firstname': user.firstname,
        'lastname': user.lastname,
        'organization_id': user.organization_id,
        'template_id': template_id  # Include template_id from survey response
    }
    return jsonify(result)

def validate_user_role(role):
    """Validate user role against enum values, return 'other' if invalid"""
    valid_roles = ['admin', 'user', 'manager', 'other', 'primary_contact', 'secondary_contact', 'head']
    return role if role in valid_roles else 'other'

@app.route('/api/users', methods=['POST'])
def add_user():
    data = request.get_json()
    
    # Validate and clean the role
    requested_role = data.get('role', 'user')
    validated_role = validate_user_role(requested_role)
    
    # Generate password if not provided
    user_password = data.get('password')
    if not user_password:
        # Generate a default password (in production, use a secure password generator)
        import string
        import random
        user_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    
    # Generate survey code
    import uuid
    from datetime import datetime, timedelta
    survey_code = str(uuid.uuid4())
    
    # Create geo_location if provided
    geo_location_id = None
    if data.get('geo_location'):
        geo_data = data['geo_location']
        geo_location = GeoLocation(
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
            latitude=float(geo_data.get('latitude', 0)),
            longitude=float(geo_data.get('longitude', 0))
        )
        db.session.add(geo_location)
        db.session.flush()
        geo_location_id = geo_location.id
    
    # Create the user
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=user_password,  # In production, this should be hashed
        role=validated_role,
        firstname=data.get('firstname'),
        lastname=data.get('lastname'),
        organization_id=data.get('organization_id'),
        survey_code=survey_code,
        phone=data.get('phone'),  # Add phone number
        geo_location_id=geo_location_id  # Add geo_location reference
    )
    
    db.session.add(new_user)
    db.session.flush()  # Get the user ID
    
    # Update geo_location with user_id and organization_id after user creation
    if geo_location_id:
        geo_location.user_id = new_user.id
        geo_location.organization_id = data.get('organization_id')
    
    # If role was changed to 'other', create organizational role
    if requested_role != validated_role and data.get('organization_id'):
        # Find or create the role in the Role table
        role_record = Role.query.filter_by(name=requested_role).first()
        if not role_record:
            role_record = Role(name=requested_role, description=f"Custom role: {requested_role}")
            db.session.add(role_record)
            db.session.flush()
        
        # Create the organizational role entry
        user_org_role = UserOrganizationRole(
            user_id=new_user.id,
            organization_id=data.get('organization_id'),
            role_id=role_record.id
        )
        db.session.add(user_org_role)
    
    # Create survey response record automatically - for all roles EXCEPT admin/contact roles
    excluded_roles = ['admin', 'root', 'primary_contact', 'secondary_contact']
    if validated_role.lower() not in [role.lower() for role in excluded_roles]:
        try:
            # Get template_id from request data or use default
            template_id = data.get('template_id')
            
            if not template_id:
                # Try to get the first available template as default
                default_template = SurveyTemplate.query.first()
                if default_template:
                    template_id = default_template.id
                else:
                    # Create a default template if none exists
                    logger.warning("No templates found, creating a default template")
                    
                    # First, ensure there's a template version
                    if new_user.organization_id:
                        org_id = new_user.organization_id
                    else:
                        # Use the first organization or create a default one
                        first_org = Organization.query.first()
                        if first_org:
                            org_id = first_org.id
                        else:
                            # This shouldn't happen in normal operation, but handle gracefully
                            logger.error("No organizations found, cannot create default template")
                            raise Exception("No organizations available for template creation")
                    
                    # Create default template version
                    default_version = SurveyTemplateVersion(
                        name="Default Survey Template",
                        description="Auto-generated default template for new users",
                        organization_id=org_id
                    )
                    db.session.add(default_version)
                    db.session.flush()
                    
                    # Create default template
                    default_template = SurveyTemplate(
                        version_id=default_version.id,
                        survey_code=f"default-template-{str(uuid.uuid4())[:8]}",
                        questions=[{"question": "Welcome survey - please update with real questions"}],
                        sections=["General"]
                    )
                    db.session.add(default_template)
                    db.session.flush()
                    template_id = default_template.id
            
            # Verify template exists
            template = SurveyTemplate.query.get(template_id)
            if not template:
                raise Exception(f"Template with ID {template_id} not found")
            
            # Calculate dates
            current_date = datetime.now()
            start_date = current_date
            end_date = current_date + timedelta(days=15)
            
            # Generate unique survey response code
            response_survey_code = str(uuid.uuid4())
            
            # Create survey response
            survey_response = SurveyResponse(
                template_id=template_id,
                user_id=new_user.id,
                answers={},  # Empty JSON object as required
                status='pending',
                survey_code=response_survey_code,
                start_date=start_date,
                end_date=end_date
            )
            
            db.session.add(survey_response)
            logger.info(f"Created survey response for user {new_user.username} with template_id {template_id}")
            
        except Exception as e:
            logger.error(f"Failed to create survey response for user {new_user.username}: {str(e)}")
            # Don't fail user creation if survey response creation fails
            pass
    else:
        logger.info(f"Skipping survey response creation for user {new_user.username} with role '{validated_role}' - excluded roles (admin, root, primary_contact, secondary_contact) do not get survey assignments")
    
    db.session.commit()
    
    # Send welcome email automatically
    try:
        # Get email template ID from request data
        email_template_id = data.get('email_template_id')
        
        email_result = send_welcome_email(
            to_email=new_user.email,
            username=new_user.username,
            password=user_password,
            firstname=new_user.firstname,
            survey_code=survey_code,
            email_template_id=email_template_id
        )
        logger.info(f"Welcome email sent for new user {new_user.username}: {email_result}")
    except Exception as e:
        logger.error(f"Failed to send welcome email for user {new_user.username}: {str(e)}")
        # Don't fail user creation if email fails
    
    # Prepare response with role validation info
    response_data = {
        'message': 'User added successfully',
        'id': new_user.id,
        'password': user_password,  # Include the password that was stored
        'username': new_user.username,
        'email': new_user.email,
        'firstname': new_user.firstname,
        'lastname': new_user.lastname,
        'phone': new_user.phone,  # Include phone in response
        'survey_code': survey_code,
        'geo_location': data.get('geo_location')  # Include geo_location in response
    }
    
    # Add survey response information if created
    try:
        survey_response = SurveyResponse.query.filter_by(user_id=new_user.id).first()
        if survey_response:
            response_data['survey_response'] = {
                'id': survey_response.id,
                'template_id': survey_response.template_id,
                'status': survey_response.status,
                'survey_code': survey_response.survey_code,
                'start_date': survey_response.start_date.isoformat() if survey_response.start_date else None,
                'end_date': survey_response.end_date.isoformat() if survey_response.end_date else None
            }
    except Exception as e:
        logger.error(f"Error adding survey response info to response: {str(e)}")
        # Don't fail the response if this fails
    
    # Add role validation info if the role was changed
    if requested_role != validated_role:
        response_data['role_info'] = f"Role '{requested_role}' stored as organizational role. User role set to '{validated_role}'."
        response_data['requested_role'] = requested_role
        response_data['actual_role'] = validated_role
        response_data['display_role'] = requested_role  # This is what the UI should display
    
    return jsonify(response_data), 201

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    # Debug logging
    logger.info(f"=== UPDATE USER {user_id} DEBUG ===")
    logger.info(f"Received data keys: {list(data.keys())}")
    logger.info(f"template_id in data: {'template_id' in data}")
    logger.info(f"template_id value: {data.get('template_id')}")
    logger.info(f"Full data: {data}")
    logger.info(f"================================")
    
    # Track role validation
    role_changed = False
    requested_role = None
    validated_role = None
    
    # Update user fields
    if 'username' in data:
        user.username = data['username']
    if 'email' in data:
        user.email = data['email']
    if 'password' in data:
        user.password = data['password']  # In production, this should be hashed
    if 'role' in data:
        requested_role = data['role']
        validated_role = validate_user_role(data['role'])
        role_changed = requested_role != validated_role
        user.role = validated_role
    if 'firstname' in data:
        user.firstname = data['firstname']
    if 'lastname' in data:
        user.lastname = data['lastname']
    if 'phone' in data:
        user.phone = data['phone']
    if 'organization_id' in data:
        user.organization_id = data['organization_id']
    
    # Handle template_id update - update the user's survey response template
    if 'template_id' in data and data['template_id']:
        try:
            template_id = data['template_id']
            
            # Verify template exists
            template = SurveyTemplate.query.get(template_id)
            if not template:
                logger.warning(f"Template with ID {template_id} not found, skipping template update")
            else:
                # Find the most relevant existing survey response for this user
                # Prefer a non-completed (pending/in_progress) response; otherwise fallback to latest by id
                survey_response = None
                try:
                    # Try to find a pending or in_progress response, latest first
                    survey_response = (
                        SurveyResponse.query
                        .filter(SurveyResponse.user_id == user_id, SurveyResponse.status.in_(['pending', 'in_progress']))
                        .order_by(SurveyResponse.id.desc())
                        .first()
                    )
                    if not survey_response:
                        # Fallback to the most recent response by id
                        survey_response = (
                            SurveyResponse.query
                            .filter_by(user_id=user_id)
                            .order_by(SurveyResponse.id.desc())
                            .first()
                        )
                except Exception as qerr:
                    logger.error(f"Error querying survey responses for user {user_id}: {str(qerr)}")
                    survey_response = None

                if survey_response:
                    # Update the chosen survey response with new template
                    old_template_id = survey_response.template_id
                    survey_response.template_id = template_id
                    
                    # Reset answers and status if template changed
                    if old_template_id != template_id:
                        survey_response.answers = {}
                        survey_response.status = 'pending'
                        logger.info(f"Updated survey response {survey_response.id} for user {user_id}: template {old_template_id} -> {template_id} (answers reset)")
                    else:
                        logger.info(f"Survey response {survey_response.id} template unchanged for user {user_id}")
                else:
                    # Create new survey response if none exists
                    excluded_roles = ['admin', 'root', 'primary_contact', 'secondary_contact']
                    current_role = data.get('role', user.role)
                    validated_role = validate_user_role(current_role)
                    
                    if validated_role.lower() not in [role.lower() for role in excluded_roles]:
                        current_date = datetime.now()
                        start_date = current_date
                        end_date = current_date + timedelta(days=15)
                        response_survey_code = str(uuid.uuid4())
                        
                        survey_response = SurveyResponse(
                            template_id=template_id,
                            user_id=user_id,
                            answers={},
                            status='pending',
                            survey_code=response_survey_code,
                            start_date=start_date,
                            end_date=end_date
                        )
                        db.session.add(survey_response)
                        logger.info(f"Created new survey response for user {user_id} with template_id {template_id}")
                    else:
                        logger.info(f"Skipping survey response creation for user {user_id} with role '{validated_role}' - excluded role")
        except Exception as e:
            logger.error(f"Failed to update template for user {user_id}: {str(e)}")
            # Don't fail the entire update if template update fails
    
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
    
    # Handle organizational roles if provided or if role was changed to 'other'
    if 'roles' in data:
        # Remove existing roles for this user
        UserOrganizationRole.query.filter_by(user_id=user_id).delete()
        
        # Add new roles
        if data['roles']:
            for role_data in data['roles']:
                if isinstance(role_data, dict) and 'organization_id' in role_data and 'role_type' in role_data:
                    # Find or create the role in the Role table
                    role_record = Role.query.filter_by(name=role_data['role_type']).first()
                    if not role_record:
                        role_record = Role(name=role_data['role_type'], description=f"Custom role: {role_data['role_type']}")
                        db.session.add(role_record)
                        db.session.flush()
                    
                    user_org_role = UserOrganizationRole(
                        user_id=user_id,
                        organization_id=role_data['organization_id'],
                        role_id=role_record.id
                    )
                    db.session.add(user_org_role)
    elif role_changed and user.organization_id:
        # If role was changed to 'other', create organizational role automatically
        # Remove existing roles for this user first
        UserOrganizationRole.query.filter_by(user_id=user_id).delete()
        
        # Find or create the role in the Role table
        role_record = Role.query.filter_by(name=requested_role).first()
        if not role_record:
            role_record = Role(name=requested_role, description=f"Custom role: {requested_role}")
            db.session.add(role_record)
            db.session.flush()
        
        # Create the organizational role entry
        user_org_role = UserOrganizationRole(
            user_id=user_id,
            organization_id=user.organization_id,
            role_id=role_record.id
        )
        db.session.add(user_org_role)
    
    db.session.commit()
    
    # Prepare response with role validation info
    response_data = {'message': 'User updated successfully'}
    
    # Add role validation info if the role was changed
    if role_changed:
        response_data['role_info'] = f"Role '{requested_role}' stored as organizational role. User role set to '{validated_role}'."
        response_data['requested_role'] = requested_role
        response_data['actual_role'] = validated_role
        response_data['display_role'] = requested_role  # This is what the UI should display
    
    return jsonify(response_data)

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user and all related records"""
    try:
        user = User.query.get_or_404(user_id)
        logger.info(f"Deleting user {user_id} ({user.username})")
        
        # Delete records in the correct order to handle foreign key constraints
        deleted_counts = {
            'user_details': 0,
            'survey_responses': 0,
            'user_organization_roles': 0,
            'geo_locations': 0,
            'organization_contacts': 0
        }
        
        # 1. Delete user details
        user_details = UserDetails.query.filter_by(user_id=user_id).all()
        for detail in user_details:
            db.session.delete(detail)
        deleted_counts['user_details'] = len(user_details)
        
        # 2. Delete survey responses
        survey_responses = SurveyResponse.query.filter_by(user_id=user_id).all()
        for response in survey_responses:
            db.session.delete(response)
        deleted_counts['survey_responses'] = len(survey_responses)
        
        # 3. Delete user organizational roles
        user_org_roles = UserOrganizationRole.query.filter_by(user_id=user_id).all()
        for role in user_org_roles:
            db.session.delete(role)
        deleted_counts['user_organization_roles'] = len(user_org_roles)
        
        # 4. Delete user's geo location if it exists
        if user.geo_location_id:
            geo_location = GeoLocation.query.get(user.geo_location_id)
            if geo_location:
                db.session.delete(geo_location)
                deleted_counts['geo_locations'] = 1
        
        # 5. Update organizations that reference this user as contact or head
        # Set foreign key references to NULL in organizations
        organizations_as_primary = Organization.query.filter_by(primary_contact=user_id).all()
        for org in organizations_as_primary:
            org.primary_contact = None
            deleted_counts['organization_contacts'] += 1
        
        organizations_as_secondary = Organization.query.filter_by(secondary_contact=user_id).all()
        for org in organizations_as_secondary:
            org.secondary_contact = None
            deleted_counts['organization_contacts'] += 1
        
        organizations_as_head = Organization.query.filter_by(head=user_id).all()
        for org in organizations_as_head:
            org.head = None
            deleted_counts['organization_contacts'] += 1
        
        # 6. Update geo_locations that reference this user
        geo_locations_referencing_user = GeoLocation.query.filter_by(user_id=user_id).all()
        for geo_loc in geo_locations_referencing_user:
            geo_loc.user_id = None
        
        # 7. Finally delete the user
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"Successfully deleted user {user_id} and related records: {deleted_counts}")
        
        return jsonify({
            'message': 'User deleted successfully',
            'user_id': user_id,
            'username': user.username,
            'deleted_counts': deleted_counts
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500

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
    
    # Process the file and create users
    created_users = []
    errors = []
    
    try:
        import pandas as pd
        import string
        import random
        
        # Read the file
        if filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        
        # Process each row
        for index, row in df.iterrows():
            try:
                # Generate password for each user
                user_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                
                # Generate survey code
                survey_code = str(uuid.uuid4())
                
                # Validate required fields
                if pd.isna(row.get('username')) or pd.isna(row.get('email')):
                    errors.append(f"Row {index + 1}: Missing username or email")
                    continue
                
                # Create the user
                new_user = User(
                    username=str(row['username']).strip(),
                    email=str(row['email']).strip(),
                    password=user_password,
                    role=str(row.get('role', 'user')).strip(),
                    firstname=str(row.get('firstname', '')).strip() if not pd.isna(row.get('firstname')) else None,
                    lastname=str(row.get('lastname', '')).strip() if not pd.isna(row.get('lastname')) else None,
                    organization_id=int(row['organization_id']) if not pd.isna(row.get('organization_id')) else None,
                    survey_code=survey_code,
                    phone=str(row.get('phone', '')).strip() if not pd.isna(row.get('phone')) else None
                )
                
                db.session.add(new_user)
                db.session.flush()  # Get the user ID
                
                # Send welcome email
                try:
                    email_result = send_welcome_email(
                        to_email=new_user.email,
                        username=new_user.username,
                        password=user_password,
                        firstname=new_user.firstname,
                        survey_code=survey_code
                    )
                    logger.info(f"Welcome email sent for uploaded user {new_user.username}: {email_result}")
                except Exception as email_error:
                    logger.error(f"Failed to send welcome email for user {new_user.username}: {str(email_error)}")
                
                created_users.append({
                    'id': new_user.id,
                    'username': new_user.username,
                    'email': new_user.email,
                    'password': user_password  # Include password in response for debugging
                })
                
            except Exception as user_error:
                errors.append(f"Row {index + 1}: {str(user_error)}")
                continue
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            'message': f'Successfully created {len(created_users)} users',
            'created_users': created_users,
            'errors': errors,
            'total_processed': len(df),
            'successful': len(created_users),
            'failed': len(errors)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'File processing failed: {str(e)}'}), 500
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
                'id': user.geo_location.id if user.geo_location else None,
                'continent': user.geo_location.continent if user.geo_location else None,
                'region': user.geo_location.region if user.geo_location else None,
                'country': user.geo_location.country if user.geo_location else None,
                'province': user.geo_location.province if user.geo_location else None,
                'city': user.geo_location.city if user.geo_location else None,
                'town': user.geo_location.town if user.geo_location else None,
                'address_line1': user.geo_location.address_line1 if user.geo_location else None,
                'address_line2': user.geo_location.address_line2 if user.geo_location else None,
                'postal_code': user.geo_location.postal_code if user.geo_location else None,
                'latitude': float(user.geo_location.latitude) if user.geo_location else 0,
                'longitude': float(user.geo_location.longitude) if user.geo_location else 0
            },
            'survey_code': user.survey_code,  # Include survey code for sharing with respondents
            'organization': {
                'id': user.organization.id,
                'name': user.organization.name,
                'organization_type': {
                    'id': user.organization.organization_type.id,
                    'type': user.organization.organization_type.type
                } if user.organization.organization_type else None,
                'geo_location': {
                    'id': user.organization.geo_location.id if user.organization and user.organization.geo_location else None,
                    'continent': user.organization.geo_location.continent if user.organization and user.organization.geo_location else None,
                    'region': user.organization.geo_location.region if user.organization and user.organization.geo_location else None,
                    'country': user.organization.geo_location.country if user.organization and user.organization.geo_location else None,
                    'province': user.organization.geo_location.province if user.organization and user.organization.geo_location else None,
                    'city': user.organization.geo_location.city if user.organization and user.organization.geo_location else None,
                    'town': user.organization.geo_location.town if user.organization and user.organization.geo_location else None,
                    'address_line1': user.organization.geo_location.address_line1 if user.organization and user.organization.geo_location else None,
                    'address_line2': user.organization.geo_location.address_line2 if user.organization and user.organization.geo_location else None,
                    'postal_code': user.organization.geo_location.postal_code if user.organization and user.organization.geo_location else None,
                    'latitude': float(user.organization.geo_location.latitude) if user.organization and user.organization.geo_location else 0,
                    'longitude': float(user.organization.geo_location.longitude) if user.organization and user.organization.geo_location else 0
                },
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

@app.route('/api/question-types/numeric', methods=['GET'])
def get_numeric_question_types():
    """Get all question types that are always numeric"""
    # Based on QUESTION_TYPE_REFERENCE.md
    # IDs 4, 7, 8, 10 are always numeric
    numeric_type_ids = [4, 7, 8, 10]
    
    question_types = QuestionType.query.filter(
        QuestionType.id.in_(numeric_type_ids),
        QuestionType.is_active == True
    ).all()
    
    return jsonify([{
        'id': qt.id,
        'name': qt.name,
        'display_name': qt.display_name,
        'category': qt.category,
        'description': qt.description,
        'is_always_numeric': True
    } for qt in question_types]), 200

@app.route('/api/question-types/non-numeric', methods=['GET'])
def get_non_numeric_question_types():
    """Get all question types that are always non-numeric"""
    # Based on QUESTION_TYPE_REFERENCE.md
    # IDs 3, 5, 6 are always non-numeric
    non_numeric_type_ids = [3, 5, 6]
    
    question_types = QuestionType.query.filter(
        QuestionType.id.in_(non_numeric_type_ids),
        QuestionType.is_active == True
    ).all()
    
    return jsonify([{
        'id': qt.id,
        'name': qt.name,
        'display_name': qt.display_name,
        'category': qt.category,
        'description': qt.description,
        'is_always_numeric': False
    } for qt in question_types]), 200

@app.route('/api/question-types/conditional', methods=['GET'])
def get_conditional_question_types():
    """Get all question types that may be numeric or non-numeric depending on content"""
    # Based on QUESTION_TYPE_REFERENCE.md
    # IDs 1, 2, 9 are conditional
    conditional_type_ids = [1, 2, 9]
    
    question_types = QuestionType.query.filter(
        QuestionType.id.in_(conditional_type_ids),
        QuestionType.is_active == True
    ).all()
    
    return jsonify([{
        'id': qt.id,
        'name': qt.name,
        'display_name': qt.display_name,
        'category': qt.category,
        'description': qt.description,
        'is_conditional': True
    } for qt in question_types]), 200

@app.route('/api/question-types/classify', methods=['POST'])
def classify_question_endpoint():
    """Classify a question as numeric or non-numeric"""
    from text_analytics import classify_question_type
    
    data = request.get_json()
    question_text = data.get('question_text', '')
    question_metadata = data.get('metadata', {})
    
    if not question_text:
        return jsonify({'error': 'question_text is required'}), 400
    
    classification = classify_question_type(question_text, question_metadata)
    
    return jsonify(classification), 200

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
                'config_schema': {'items': [], 'total_percentage': 100, 'allow_decimals': False, 'required': False}
            },
            {
                'id': 9, 'name': 'flexible_input', 'display_name': 'Flexible Input',
                'category': 'Core Questions', 'description': 'Collect alphanumeric responses across multiple items',
                'config_schema': {'items': [], 'instructions': '', 'placeholder': 'Enter your response', 'required': False}
            },
            {
                'id': 10, 'name': 'year_matrix', 'display_name': 'Year Matrix',
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

# Note: Constant sum is now handled as a simple question type like others

@app.route('/api/initialize-default-email-templates', methods=['POST'])
def initialize_default_email_templates():
    """Initialize default email templates for welcome and reminder emails"""
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
        existing_invitation = EmailTemplate.query.filter_by(
            organization_id=first_org.id, 
            name='Default Invitation Email'
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
                    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 15px 15px 0 0; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3); }
                    .content { background: #ffffff; padding: 40px 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); }
                    .footer { background: #f8fafc; padding: 30px; border-radius: 0 0 15px 15px; border: 1px solid #e2e8f0; border-top: none; text-align: center; }
                    .credentials { background: #e8f5e8; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #10b981; }
                    .guide { background: #fff3cd; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #fbbf24; }
                    .features { background: #e0f2fe; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #0ea5e9; }
                    .highlight { color: #667eea; font-weight: bold; }
                    .emoji { font-size: 1.2em; }
                    .button { display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0; transition: background 0.3s ease; }
                    .button:hover { background: #5a67d8; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 32px;">🎉 Welcome to Saurara!</h1>
                        <p style="margin: 15px 0 0 0; font-size: 18px; opacity: 0.9;">Your Journey Begins Here</p>
                    </div>
                    
                    <div class="content">
                        <p style="font-size: 18px; margin-bottom: 25px;">{{greeting}},</p>
                        
                        <p style="font-size: 16px; margin-bottom: 20px;">🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.</p>
                        
                        <p style="margin-bottom: 20px;">We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.</p>
                        
                        <div class="credentials">
                            <h3 style="margin-top: 0; color: #059669;"><span class="emoji">🔐</span> Your Account Credentials:</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin: 8px 0;"><strong>Username:</strong> {{username}}</li>
                                <li style="margin: 8px 0;"><strong>Email:</strong> {{email}}</li>
                                <li style="margin: 8px 0;"><strong>Temporary Password:</strong> <span class="highlight">{{password}}</span></li>
                                <li style="margin: 8px 0;"><strong>Survey Code:</strong> {{survey_code}}</li>
                                <li style="margin: 8px 0;"><strong>Platform Access:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                            </ul>
                        </div>
                        
                        <div class="guide">
                            <h3 style="margin-top: 0; color: #f59e0b;"><span class="emoji">🚀</span> Quick Start Guide:</h3>
                            <ol style="padding-left: 20px;">
                                <li style="margin: 8px 0;">Visit <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                                <li style="margin: 8px 0;">Click on "Login" or "Survey Access"</li>
                                <li style="margin: 8px 0;">Enter your username and password above</li>
                                <li style="margin: 8px 0;">Complete your profile setup when ready</li>
                                <li style="margin: 8px 0;">Explore survey opportunities and platform features</li>
                                <li style="margin: 8px 0;">Connect with your organization and peers</li>
                            </ol>
                        </div>
                        
                        <div class="features">
                            <h3 style="margin-top: 0; color: #0284c7;"><span class="emoji">📚</span> Platform Features:</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin: 8px 0;">• Personalized survey dashboard</li>
                                <li style="margin: 8px 0;">• Progress tracking and completion status</li>
                                <li style="margin: 8px 0;">• Secure data handling and privacy protection</li>
                                <li style="margin: 8px 0;">• Community insights and research updates</li>
                                <li style="margin: 8px 0;">• Professional networking opportunities</li>
                            </ul>
                        </div>
                        
                        <p style="background: #fef3c7; padding: 20px; border-radius: 8px; border-left: 4px solid #f59e0b; margin: 25px 0;">
                            <strong><span class="emoji">🔒</span> Important Security Information:</strong><br>
                            For your account security, please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals.
                        </p>
                        
                        <p style="margin: 25px 0;">We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.</p>
                        
                        <p style="font-size: 18px; font-weight: bold; color: #667eea; text-align: center; margin: 30px 0;">Welcome aboard! 🌟</p>
                    </div>
                    
                    <div class="footer">
                        <p style="margin: 0; color: #64748b;">Best regards,<br><strong>The Saurara Research Team</strong></p>
                        <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; font-size: 14px; color: #64748b;">
                                <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                                info@saurara.org | 
                                Stay Connected
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            welcome_text = """{{greeting}},

🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

🔐 Your Account Credentials:
• Username: {{username}}
• Email Address: {{email}}
• Temporary Password: {{password}}
• Survey Code: {{survey_code}}
• Platform Access: www.saurara.org

🚀 Quick Start Guide:
1. Visit www.saurara.org
2. Click on "Login" or "Survey Access"
3. Enter your username and password above
4. Complete your profile setup when ready
5. Explore survey opportunities and platform features
6. Connect with your organization and peers

🔒 Important Security Information:
For your account security, please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals.

📚 Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard! 🌟

Best regards,
The Saurara Research Team

---
Platform: www.saurara.org
Support: info@saurara.org
Stay Connected: Follow us for updates and insights"""

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
                    .highlight { background: #f0f8ff; padding: 15px; border-left: 4px solid #667eea; margin: 20px 0; }
                    .survey-details { background: #e8f5e8; padding: 20px; border-radius: 8px; margin: 20px 0; }
                    .button { display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 10px 0; }
                    .steps { background: #fff9e6; padding: 20px; border-radius: 8px; margin: 20px 0; }
                    .reminder-tag { background: #ff6b6b; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 28px;">🔔 Survey Reminder</h1>
                        <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Research Platform</p>
                    </div>
                    
                    <div class="content">
                        <p style="font-size: 18px; margin-bottom: 20px;">{{greeting}},</p>
                        
                        <p>We hope this message finds you well!</p>
                        
                        <p>This is a friendly reminder that you have a pending survey{{org_text}} on the Saurara Platform that requires your attention.{{deadline_text}}</p>
                        
                        <div class="survey-details">
                            <h3 style="margin-top: 0; color: #2d7a2d;">Your Survey Details:</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin: 8px 0;"><strong>Username:</strong> {{username}}</li>
                                <li style="margin: 8px 0;"><strong>Survey Code:</strong> {{survey_code}}</li>
                                <li style="margin: 8px 0;"><strong>Survey Link:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                            </ul>
                        </div>
                        
                        <div class="highlight">
                            <h3 style="margin-top: 0; color: #667eea;">Why Your Response Matters:</h3>
                            <p style="margin-bottom: 0;">Your input is invaluable in helping us understand and improve educational and community initiatives. Every response contributes to meaningful research that can make a real difference in communities like yours.</p>
                        </div>
                        
                        <div class="steps">
                            <h3 style="margin-top: 0; color: #b8860b;">What You Need to Do:</h3>
                            <ol style="margin: 0; padding-left: 20px;">
                                <li style="margin: 8px 0;">Visit <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                                <li style="margin: 8px 0;">Enter your survey code: <strong>{{survey_code}}</strong></li>
                                <li style="margin: 8px 0;">Complete the survey at your convenience</li>
                                <li style="margin: 8px 0;">Submit your responses</li>
                            </ol>
                        </div>
                        
                        <p style="background: #e7f3ff; padding: 15px; border-radius: 8px; margin: 20px 0;">
                            📊 The survey typically takes 15-20 minutes to complete, and you can save your progress and return later if needed.
                        </p>
                        
                        <p style="margin: 25px 0;">We truly appreciate your time and participation. Your voice matters, and we look forward to receiving your valuable insights.</p>
                        
                        <p style="font-weight: bold; color: #667eea;">Thank you for being part of the Saurara community!</p>
                    </div>
                    
                    <div class="footer">
                        <p style="margin: 0;">Best regards,<br><strong>The Saurara Research Team</strong></p>
                        <hr style="margin: 20px 0; border: none; border-top: 1px solid #e0e0e0;">
                        <p style="margin: 0; font-size: 12px; color: #666;">
                            This is an automated reminder. If you have already completed the survey, please disregard this message.<br>
                            Visit: <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | Email: info@saurara.org
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            reminder_text = """{{greeting}},

We hope this message finds you well!

This is a friendly reminder that you have a pending survey{{org_text}} on the Saurara Platform that requires your attention.{{deadline_text}}

Your Survey Details:
• Username: {{username}}
• Survey Code: {{survey_code}}
• Survey Link: www.saurara.org

Why Your Response Matters:
Your input is invaluable in helping us understand and improve educational and community initiatives. Every response contributes to meaningful research that can make a real difference in communities like yours.

What You Need to Do:
1. Visit www.saurara.org
2. Enter your survey code: {{survey_code}}
3. Complete the survey at your convenience
4. Submit your responses

The survey typically takes 15-20 minutes to complete, and you can save your progress and return later if needed.

Need Help?
If you're experiencing any difficulties or have questions about the survey, please don't hesitate to reach out to our support team. We're here to help!

We truly appreciate your time and participation. Your voice matters, and we look forward to receiving your valuable insights.

Thank you for being part of the Saurara community!

Best regards,
The Saurara Research Team

---
This is an automated reminder. If you have already completed the survey, please disregard this message.
Visit: www.saurara.org | Email: info@saurara.org"""

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
        
        # Create Invitation Email Template
        if not existing_invitation:
            invitation_html = """
            <html>
            <head>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
                    .container { max-width: 650px; margin: 0 auto; padding: 20px; background: #f8fafc; }
                    .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 15px 15px 0 0; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3); }
                    .content { background: #ffffff; padding: 40px 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); }
                    .footer { background: #f8fafc; padding: 30px; border-radius: 0 0 15px 15px; border: 1px solid #e2e8f0; border-top: none; text-align: center; }
                    .credentials { background: #e8f5e8; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #10b981; }
                    .steps { background: #fff3cd; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #fbbf24; }
                    .highlight { color: #667eea; font-weight: bold; }
                    .emoji { font-size: 1.2em; }
                    .button { display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0; transition: background 0.3s ease; }
                    .button:hover { background: #5a67d8; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0; font-size: 32px;">Survey Invitation</h1>
                        <p style="margin: 15px 0 0 0; font-size: 18px; opacity: 0.9;">Your Participation Matters</p>
                    </div>
                    
                    <div class="content">
                        <p style="font-size: 18px; margin-bottom: 25px;">{{greeting}},</p>
                        
                        <p style="font-size: 16px; margin-bottom: 20px;">We're excited to invite you to participate in an important research survey{{org_text}} on the Saurara Platform!</p>
                        
                        <p style="margin-bottom: 20px;">Your participation will contribute to valuable research that helps improve educational and community programs. We've created a temporary account for you to access the survey.</p>
                        
                        <div class="credentials">
                            <h3 style="margin-top: 0; color: #059669;"><span class="emoji">🔐</span> Your Temporary Account Credentials:</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin: 8px 0;"><strong>Username:</strong> {{username}}</li>
                                <li style="margin: 8px 0;"><strong>Temporary Password:</strong> <span class="highlight">{{password}}</span></li>
                                <li style="margin: 8px 0;"><strong>Survey Access:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                            </ul>
                        </div>
                        
                        <div class="steps">
                            <h3 style="margin-top: 0; color: #f59e0b;"><span class="emoji">📋</span> What You Need to Do:</h3>
                            <ol style="padding-left: 20px;">
                                <li style="margin: 8px 0;">Visit <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                                <li style="margin: 8px 0;">Click "Login" or "Survey Access"</li>
                                <li style="margin: 8px 0;">Enter your username and temporary password</li>
                                <li style="margin: 8px 0;">Complete the survey (takes about 15-20 minutes)</li>
                                <li style="margin: 8px 0;">Change your password during first login for security</li>
                            </ol>
                        </div>
                        
                        <div style="background: #e0f2fe; padding: 25px; border-radius: 10px; margin: 25px 0; border-left: 5px solid #0ea5e9;">
                            <h3 style="margin-top: 0; color: #0284c7;"><span class="emoji">🎯</span> Why Your Response Matters:</h3>
                            <p style="margin-bottom: 0;">Your insights will help researchers understand and improve programs that benefit communities like yours. Every response makes a difference!</p>
                        </div>
                        
                        <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                            <h3 style="margin-top: 0; color: #0369a1;"><span class="emoji">💡</span> Survey Features:</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin: 8px 0;">• Save progress and return later</li>
                                <li style="margin: 8px 0;">• Mobile-friendly interface</li>
                                <li style="margin: 8px 0;">• Secure data handling</li>
                                <li style="margin: 8px 0;">• Professional insights dashboard</li>
                            </ul>
                        </div>
                        
                        <p style="background: #fef3c7; padding: 20px; border-radius: 8px; border-left: 4px solid #f59e0b; margin: 25px 0;">
                            <strong><span class="emoji">🆘</span> Need Help?</strong><br>
                            Our support team is here to assist you. Contact us at <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a> if you have any questions.
                        </p>
                        
                        <p style="margin: 25px 0;">We look forward to your valuable contribution!</p>
                        
                        <p style="font-size: 18px; font-weight: bold; color: #667eea; text-align: center; margin: 30px 0;">Thank you for participating! 🌟</p>
                    </div>
                    
                    <div class="footer">
                        <p style="margin: 0; color: #64748b;">Best regards,<br><strong>The Saurara Research Team</strong></p>
                        <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0; font-size: 14px; color: #64748b;">
                                <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                                <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a> | 
                                Stay Connected
                            </p>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            
            invitation_text = """{{greeting}},

We're excited to invite you to participate in an important research survey{{org_text}} on the Saurara Platform!

Your participation will contribute to valuable research that helps improve educational and community programs. We've created a temporary account for you to access the survey.

Your Temporary Account Credentials:
• Username: {{username}}
• Temporary Password: {{password}}
• Survey Access: www.saurara.org

What You Need to Do:
1. Visit www.saurara.org
2. Click "Login" or "Survey Access"
3. Enter your username and temporary password
4. Complete the survey (takes about 15-20 minutes)
5. Change your password during first login for security

Why Your Response Matters:
Your insights will help researchers understand and improve programs that benefit communities like yours. Every response makes a difference!

Survey Features:
• Save progress and return later
• Mobile-friendly interface
• Secure data handling
• Professional insights dashboard

🆘 Need Help?
Our support team is here to assist you. Contact us at info@saurara.org if you have any questions.

We look forward to your valuable contribution!

Best regards,
The Saurara Research Team

---
Platform: www.saurara.org
Support: info@saurara.org"""

            invitation_template = EmailTemplate(
                organization_id=first_org.id,
                name='Default Invitation Email',
                subject='You\'re Invited: Complete the Saurara Survey',
                html_body=invitation_html,
                text_body=invitation_text,
                is_public=True
            )
            db.session.add(invitation_template)
            templates_created.append('Default Invitation Email')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully initialized {len(templates_created)} default email templates',
            'templates_created': templates_created
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing default email templates: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to initialize email templates: {str(e)}'}), 500

@app.route('/api/initialize-enhanced-data', methods=['POST'])
def initialize_enhanced_data():
    """Initialize sample data for testing the enhanced organization system"""
    try:
        # Initialize organization types
        OrganizationType.query.delete()
        types = ['CHURCH', 'School', 'OTHER', 'Institution', 'Non_formal_organizations']
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
        church_type = OrganizationType.query.filter_by(type='CHURCH').first()
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
                logger.error(f"Missing or empty field: {field}, value: {data.get(field)}")
                return jsonify({'error': f'{field} is required and cannot be empty'}), 400
        
        # Check if user has an organization and if email service is active
        if data.get('user_id'):
            user = User.query.get(data['user_id'])
            if user and user.organization_id:
                is_active, message = is_email_service_active_for_organization(user.organization_id)
                if not is_active:
                    return jsonify({
                        'error': f'Email service not available for this organization: {message}',
                        'organization_id': user.organization_id
                    }), 403
        elif data.get('organization_id'):
            # If organization_id is provided directly, check its email service status
            is_active, message = is_email_service_active_for_organization(data['organization_id'])
            if not is_active:
                return jsonify({
                    'error': f'Email service not available for this organization: {message}',
                    'organization_id': data['organization_id']
                }), 403
        
        # Log the password being sent (for debugging - remove in production)
        logger.info(f"Password being sent in welcome email: '{data['password']}'")
        
        # Send the email
        result = send_welcome_email(
            to_email=data['to_email'],
            username=data['username'],
            password=data['password'],
            firstname=data.get('firstname'),
            survey_code=data.get('survey_code'),
            email_template_id=data.get('email_template_id')
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


# ============================================================================
# PASSWORD RESET FUNCTIONS AND ROUTES
# ============================================================================

def send_password_reset_email(to_email, username, reset_token, firstname=None):
    """Send password reset email with reset link"""
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_password_reset_email_smtp(to_email, username, reset_token, firstname)
        
        # Create reset link
        reset_link = f"http://www.saurara.org/reset-password?token={reset_token}"
        
        # Email content
        subject = "🔐 Reset Your Saurara Password"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        body_text = f"""{greeting},

We received a request to reset your password for your Saurara account.

🔑 Reset Your Password

Click the link below to reset your password. This link will expire in 1 hour for security reasons.

{reset_link}

⚠️ Security Notice

If you did not request a password reset, please ignore this email and your password will remain unchanged. Your account is secure and no changes have been made.

For security reasons, this password reset link will expire in 1 hour.

If you continue to have problems, please contact our support team at info@saurara.org

Best regards,
The Saurara Team

---
www.saurara.org | info@saurara.org"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .footer {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; text-align: center; }}
                .reset-box {{ background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 15px 0; }}
                .security-note {{ background: #f8d7da; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">🔐 Password Reset Request</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Platform</p>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <p>We received a request to reset your password for your Saurara account.</p>
                    
                    <div class="reset-box">
                        <h3 style="margin-top: 0; color: #856404;">🔑 Reset Your Password</h3>
                        <p>Click the button below to reset your password. This link will expire in <strong>1 hour</strong> for security reasons.</p>
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{reset_link}" class="button" style="color: white; text-decoration: none;">Reset Password</a>
                        </div>
                        <p style="margin-bottom: 0; font-size: 14px;">Or copy and paste this link into your browser:<br>
                        <a href="{reset_link}" style="color: #667eea; word-break: break-all;">{reset_link}</a></p>
                    </div>
                    
                    <div class="security-note">
                        <h3 style="margin-top: 0; color: #721c24;">⚠️ Security Notice</h3>
                        <p style="margin-bottom: 0;">
                            If you did not request a password reset, please ignore this email and your password will remain unchanged. 
                            Your account is secure and no changes have been made.
                        </p>
                    </div>
                    
                    <p style="margin-top: 20px;">For security reasons, this password reset link will expire in 1 hour.</p>
                    
                    <p>If you continue to have problems, please contact our support team at 
                    <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a></p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; color: #666;">Best regards,<br><strong>The Saurara Team</strong></p>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 15px 0;">
                    <p style="margin: 0; font-size: 12px; color: #888;">
                        <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                        <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a>
                    </p>
                </div>
            </div>
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
            Source=source_email,
        )
        
        logger.info(f"Password reset email sent successfully via SES API to {to_email}")
        return {
            'success': True,
            'method': 'SES_API',
            'message_id': response['MessageId'],
            'message': 'Password reset email sent successfully'
        }
        
    except Exception as e:
        logger.error(f"Error sending password reset email via SES API: {str(e)}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_password_reset_email_smtp(to_email, username, reset_token, firstname)


def send_password_reset_email_smtp(to_email, username, reset_token, firstname=None):
    """Send password reset email using SMTP"""
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        
        # Get SMTP credentials from environment
        smtp_username = os.getenv('SES_SMTP_USERNAME')
        smtp_password = os.getenv('SES_SMTP_PASSWORD')
        smtp_host = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
        smtp_port = int(os.getenv('SES_SMTP_PORT', '587'))
        source_email = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')
        
        if not smtp_username or not smtp_password:
            raise Exception("SMTP credentials not found in environment variables")
        
        # Create reset link
        reset_link = f"http://www.saurara.org/reset-password?token={reset_token}"
        
        # Email content
        subject = "🔐 Reset Your Saurara Password"
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        body_text = f"""{greeting},

We received a request to reset your password for your Saurara account.

🔑 Reset Your Password

Click the link below to reset your password. This link will expire in 1 hour for security reasons.

{reset_link}

⚠️ Security Notice

If you did not request a password reset, please ignore this email and your password will remain unchanged. Your account is secure and no changes have been made.

For security reasons, this password reset link will expire in 1 hour.

If you continue to have problems, please contact our support team at ifo@saurara.org

Best regards,
The Saurara Team

---
www.saurara.org | info@saurara.org"""

        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .footer {{ background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none; text-align: center; }}
                .reset-box {{ background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107; }}
                .button {{ display: inline-block; background: #667eea; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 15px 0; }}
                .security-note {{ background: #f8d7da; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">🔐 Password Reset Request</h1>
                    <p style="margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Saurara Platform</p>
                </div>
                
                <div class="content">
                    <p style="font-size: 18px; margin-bottom: 20px;">{greeting},</p>
                    
                    <p>We received a request to reset your password for your Saurara account.</p>
                    
                    <div class="reset-box">
                        <h3 style="margin-top: 0; color: #856404;">🔑 Reset Your Password</h3>
                        <p>Click the button below to reset your password. This link will expire in <strong>1 hour</strong> for security reasons.</p>
                        <div style="text-align: center; margin: 20px 0;">
                            <a href="{reset_link}" class="button" style="color: white; text-decoration: none;">Reset Password</a>
                        </div>
                        <p style="margin-bottom: 0; font-size: 14px;">Or copy and paste this link into your browser:<br>
                        <a href="{reset_link}" style="color: #667eea; word-break: break-all;">{reset_link}</a></p>
                    </div>
                    
                    <div class="security-note">
                        <h3 style="margin-top: 0; color: #721c24;">⚠️ Security Notice</h3>
                        <p style="margin-bottom: 0;">
                            If you did not request a password reset, please ignore this email and your password will remain unchanged. 
                            Your account is secure and no changes have been made.
                        </p>
                    </div>
                    
                    <p style="margin-top: 20px;">For security reasons, this password reset link will expire in 1 hour.</p>
                    
                    <p>If you continue to have problems, please contact our support team at 
                    <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a></p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0; color: #666;">Best regards,<br><strong>The Saurara Team</strong></p>
                    <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 15px 0;">
                    <p style="margin: 0; font-size: 12px; color: #888;">
                        <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                        <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a>
                    </p>
                </div>
            </div>
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
        
        logger.info(f"Password reset email sent successfully via SMTP to {to_email}")
        return {
            'success': True,
            'method': 'SMTP',
            'message': 'Password reset email sent successfully'
        }
        
    except Exception as e:
        logger.error(f"Error sending password reset email via SMTP: {str(e)}")
        return {
            'success': False,
            'error': f"SMTP email sending failed: {str(e)}"
        }


@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    """Request password reset - sends email with reset token"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        # Find user by email or username
        user = db.session.execute(
            text("SELECT * FROM users WHERE email = :email OR username = :email"),
            {'email': email}
        ).fetchone()
        
        if not user:
            # Don't reveal if user exists or not for security
            return jsonify({'message': 'If an account exists with that email, a password reset link has been sent'}), 200
        
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)
        reset_token_expiry = datetime.now() + timedelta(hours=1)
        
        # Update user with reset token
        db.session.execute(
            text("""
                UPDATE users 
                SET reset_token = :token, reset_token_expiry = :expiry 
                WHERE id = :user_id
            """),
            {
                'token': reset_token,
                'expiry': reset_token_expiry,
                'user_id': user.id
            }
        )
        db.session.commit()
        
        # Send password reset email
        email_result = send_password_reset_email(
            to_email=user.email,
            username=user.username,
            reset_token=reset_token,
            firstname=user.firstname
        )
        
        if email_result.get('success'):
            logger.info(f"Password reset email sent to {user.email}")
        else:
            logger.error(f"Failed to send password reset email: {email_result.get('error')}")
        
        return jsonify({'message': 'If an account exists with that email, a password reset link has been sent'}), 200
        
    except Exception as e:
        logger.error(f"Error in forgot_password: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'An error occurred processing your request'}), 500


@app.route('/api/verify-reset-token', methods=['POST'])
def verify_reset_token():
    """Verify if reset token is valid and not expired"""
    try:
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Token is required'}), 400
        
        # Find user with this token
        user = db.session.execute(
            text("""
                SELECT * FROM users 
                WHERE reset_token = :token 
                AND reset_token_expiry > :now
            """),
            {
                'token': token,
                'now': datetime.now()
            }
        ).fetchone()
        
        if not user:
            return jsonify({'error': 'Invalid or expired reset token'}), 400
        
        return jsonify({
            'valid': True,
            'email': user.email
        }), 200
        
    except Exception as e:
        logger.error(f"Error in verify_reset_token: {str(e)}")
        return jsonify({'error': 'An error occurred verifying the token'}), 500


@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    """Reset password using valid token"""
    try:
        data = request.get_json()
        token = data.get('token')
        new_password = data.get('password')
        
        if not token or not new_password:
            return jsonify({'error': 'Token and new password are required'}), 400
        
        # Validate password strength
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        # Find user with this token
        user = db.session.execute(
            text("""
                SELECT * FROM users 
                WHERE reset_token = :token 
                AND reset_token_expiry > :now
            """),
            {
                'token': token,
                'now': datetime.now()
            }
        ).fetchone()
        
        if not user:
            return jsonify({'error': 'Invalid or expired reset token'}), 400
        
        # Update password and clear reset token
        db.session.execute(
            text("""
                UPDATE users 
                SET password = :password, 
                    reset_token = NULL, 
                    reset_token_expiry = NULL 
                WHERE id = :user_id
            """),
            {
                'password': new_password,
                'user_id': user.id
            }
        )
        db.session.commit()
        
        logger.info(f"Password reset successful for user {user.email}")
        return jsonify({'message': 'Password reset successful'}), 200
        
    except Exception as e:
        logger.error(f"Error in reset_password: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'An error occurred resetting your password'}), 500


@app.route('/api/change-password', methods=['POST'])
def change_password():
    """Change password for logged-in user"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not user_id or not current_password or not new_password:
            return jsonify({'error': 'User ID, current password, and new password are required'}), 400
        
        # Validate password strength
        if len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        
        # Verify current password
        user = db.session.execute(
            text("SELECT * FROM users WHERE id = :user_id AND password = :password"),
            {'user_id': user_id, 'password': current_password}
        ).fetchone()
        
        if not user:
            return jsonify({'error': 'Current password is incorrect'}), 401
        
        # Update password
        db.session.execute(
            text("UPDATE users SET password = :password WHERE id = :user_id"),
            {'password': new_password, 'user_id': user_id}
        )
        db.session.commit()
        
        logger.info(f"Password changed successfully for user {user_id}")
        return jsonify({'message': 'Password changed successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error in change_password: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'An error occurred changing your password'}), 500


# Reminder Email API Endpoints
@app.route('/api/send-reminder-email', methods=['POST'])
def send_reminder_email_endpoint():
    """Send reminder email to a user about their pending survey"""
    try:
        data = request.get_json()
        logger.info(f"Sending reminder email with data: {data}")
        
        # Validate required fields
        required_fields = ['to_email', 'username', 'survey_code']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        # Send the reminder email
        result = send_reminder_email(
            to_email=data['to_email'],
            username=data['username'],
            survey_code=data['survey_code'],
            firstname=data.get('firstname'),
            organization_name=data.get('organization_name'),
            days_remaining=data.get('days_remaining'),
            organization_id=data.get('organization_id'),
            template_id=data.get('template_id')
        )
        
        if result['success']:
            return jsonify({
                'message': 'Reminder email sent successfully',
                'method': result.get('method'),
                'message_id': result.get('message_id'),
                'to_email': data['to_email']
            }), 200
        else:
            return jsonify({
                'error': result['error']
            }), 500
            
    except Exception as e:
        logger.error(f"Error in send reminder email endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to send reminder email: {str(e)}'}), 500

@app.route('/api/send-bulk-reminder-emails', methods=['POST'])
def send_bulk_reminder_emails():
    """Send reminder emails to multiple users at once"""
    try:
        data = request.get_json()
        logger.info(f"Sending bulk reminder emails to {len(data.get('users', []))} users")
        
        # Validate required fields
        if 'users' not in data or not isinstance(data['users'], list):
            return jsonify({'error': 'users list is required'}), 400
        
        if len(data['users']) == 0:
            return jsonify({'error': 'users list cannot be empty'}), 400
        
        results = {
            'total_users': len(data['users']),
            'successful_sends': 0,
            'failed_sends': 0,
            'results': []
        }
        
        # Send reminder emails to each user
        for user_data in data['users']:
            try:
                # Validate user data
                required_user_fields = ['to_email', 'username', 'survey_code']
                for field in required_user_fields:
                    if field not in user_data or not user_data[field]:
                        results['results'].append({
                            'user': user_data.get('username', 'Unknown'),
                            'email': user_data.get('to_email', 'Unknown'),
                            'success': False,
                            'error': f'{field} is required'
                        })
                        results['failed_sends'] += 1
                        continue
                
                # Send reminder email
                result = send_reminder_email(
                    to_email=user_data['to_email'],
                    username=user_data['username'],
                    survey_code=user_data['survey_code'],
                    firstname=user_data.get('firstname'),
                    organization_name=user_data.get('organization_name'),
                    days_remaining=user_data.get('days_remaining'),
                    organization_id=user_data.get('organization_id')
                )
                
                if result['success']:
                    results['successful_sends'] += 1
                    results['results'].append({
                        'user': user_data['username'],
                        'email': user_data['to_email'],
                        'success': True,
                        'method': result.get('method'),
                        'message_id': result.get('message_id')
                    })
                else:
                    results['failed_sends'] += 1
                    results['results'].append({
                        'user': user_data['username'],
                        'email': user_data['to_email'],
                        'success': False,
                        'error': result['error']
                    })
                    
            except Exception as e:
                logger.error(f"Error sending reminder to {user_data.get('username', 'Unknown')}: {str(e)}")
                results['failed_sends'] += 1
                results['results'].append({
                    'user': user_data.get('username', 'Unknown'),
                    'email': user_data.get('to_email', 'Unknown'),
                    'success': False,
                    'error': str(e)
                })
        
        # Calculate success rate
        success_rate = (results['successful_sends'] / results['total_users'] * 100) if results['total_users'] > 0 else 0
        
        logger.info(f"Bulk reminder email results: {results['successful_sends']}/{results['total_users']} successful")
        
        return jsonify({
            'message': f'Bulk reminder emails processed: {results["successful_sends"]} successful, {results["failed_sends"]} failed',
            'success_rate': round(success_rate, 1),
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error in bulk reminder email endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to send bulk reminder emails: {str(e)}'}), 500

@app.route('/api/users/pending-surveys', methods=['GET'])
def get_users_with_pending_surveys():
    """Get all users who have not completed their surveys yet (for reminder emails)"""
    try:
        # Get users with role 'user' who have survey codes but haven't submitted user details
        users_query = db.session.query(User).filter(
            User.role == 'user',
            User.survey_code.isnot(None)
        ).outerjoin(UserDetails, User.id == UserDetails.user_id).filter(
            db.or_(
                UserDetails.id.is_(None),  # No user details record
                UserDetails.is_submitted == False  # User details exist but not submitted
            )
        )
        
        users = users_query.all()
        
        result = []
        for user in users:
            # Get user details if they exist to check last activity
            user_details = UserDetails.query.filter_by(user_id=user.id).first()
            
            # Calculate days since user creation
            days_since_creation = (datetime.utcnow() - user.created_at).days if user.created_at else 0
            
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'firstname': user.firstname,
                'lastname': user.lastname,
                'survey_code': user.survey_code,
                'organization_id': user.organization_id,
                'organization_name': user.organization.name if user.organization else None,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'days_since_creation': days_since_creation,
                'has_started_survey': bool(user_details),
                'last_page': user_details.last_page if user_details else 0,
                'last_activity': user_details.updated_at.isoformat() if user_details and user_details.updated_at else None
            }
            result.append(user_data)
        
        logger.info(f"Found {len(result)} users with pending surveys")
        
        return jsonify({
            'total_pending': len(result),
            'users': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching users with pending surveys: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch users with pending surveys: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/reminder-email', methods=['POST'])
def send_user_reminder_email(user_id):
    """Send reminder email to a specific user by user ID"""
    try:
        # Get the user
        user = User.query.get_or_404(user_id)
        
        if not user.survey_code:
            return jsonify({'error': 'User does not have a survey code'}), 400
        
        # Check if user has already completed the survey
        user_details = UserDetails.query.filter_by(user_id=user_id, is_submitted=True).first()
        if user_details:
            return jsonify({'error': 'User has already completed the survey'}), 400
        
        # Calculate days since user creation for deadline text
        days_since_creation = (datetime.utcnow() - user.created_at).days if user.created_at else 0
        suggested_deadline = max(30 - days_since_creation, 0) if days_since_creation < 30 else None
        
        # Send reminder email
        result = send_reminder_email(
            to_email=user.email,
            username=user.username,
            survey_code=user.survey_code,
            firstname=user.firstname,
            organization_name=user.organization.name if user.organization else None,
            days_remaining=suggested_deadline,
            organization_id=user.organization_id
        )
        
        if result['success']:
            return jsonify({
                'message': 'Reminder email sent successfully',
                'method': result.get('method'),
                'message_id': result.get('message_id'),
                'user_id': user_id,
                'to_email': user.email
            }), 200
        else:
            return jsonify({
                'error': result['error']
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending reminder email to user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to send reminder email: {str(e)}'}), 500

@app.route('/api/debug/database-state', methods=['GET'])
def check_database_state():
    """Check the current state of templates, responses, and related data"""
    try:
        state = {
            'organizations': Organization.query.count(),
            'template_versions': SurveyTemplateVersion.query.count(),
            'templates': SurveyTemplate.query.count(),
            'survey_responses': SurveyResponse.query.count(),
            'users': User.query.count(),
            'first_template_id': None,
            'template_details': []
        }
        
        # Get first template ID if any exist
        first_template = SurveyTemplate.query.first()
        if first_template:
            state['first_template_id'] = first_template.id
        
        # Get template details
        templates = SurveyTemplate.query.all()
        for template in templates:
            state['template_details'].append({
                'id': template.id,
                'survey_code': template.survey_code,
                'version_id': template.version_id,
                'version_name': template.version.name if template.version else 'No Version'
            })
        
        return jsonify(state), 200
        
    except Exception as e:
        logger.error(f"Error checking database state: {str(e)}")
        return jsonify({'error': f'Failed to check database state: {str(e)}'}), 500

@app.route('/api/generate-welcome-email-preview', methods=['POST'])
def generate_welcome_email_preview():
    """Generate welcome email preview with both text and HTML versions"""
    try:
        data = request.get_json()
        
        # Required fields
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        username = data['username']
        email = data['email']
        password = data['password']
        firstname = data.get('firstname', '')
        survey_code = data.get('survey_code', str(uuid.uuid4()))
        
        # Create personalized greeting
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        # Generate text version
        text_content = f"""{greeting},

Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

Your Account Credentials:
• Username: {username}
• Email Address: {email}
• Temporary Password: {password}
• Survey Code: {survey_code}
• Platform Access: www.saurara.org

Quick Start Guide:
1. Visit www.saurara.org
2. Click on "Login" or "Survey Access"
3. Enter your username and password above
4. Complete your profile setup when ready
5. Explore survey opportunities and platform features
6. Connect with your organization and peers

Important Security Information:
For your account security, please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals.

What Awaits You:
As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. Every response makes a difference!

Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

Getting the Most Out of Saurara:
- Complete your profile for better survey matching
- Respond to surveys thoughtfully and thoroughly
- Stay engaged with platform updates and announcements
- Reach out for support whenever needed

Need Assistance?
Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard!

Best regards,
The Saurara Research Team

---
Platform: www.saurara.org
Support: info@saurara.org
Stay Connected: Follow us for updates and insights"""

        # Generate HTML version
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
        .container {{ max-width: 650px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 15px 15px 0 0; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3); }}
        .content {{ background: #ffffff; padding: 40px 30px; border: 1px solid #e2e8f0; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); }}
        .footer {{ background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); padding: 30px; border-radius: 0 0 15px 15px; border: 1px solid #e2e8f0; border-top: none; }}
        .welcome-banner {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 20px; border-radius: 12px; margin: 25px 0; text-align: center; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }}
        .credentials-box {{ background: linear-gradient(135deg, #e8f5e8 0%, #dcf4dc 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #10b981; box-shadow: 0 2px 10px rgba(16, 185, 129, 0.1); }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; margin: 15px 0; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3); transition: transform 0.2s; }}
        .button:hover {{ transform: translateY(-2px); }}
        .quick-start {{ background: linear-gradient(135deg, #fff9e6 0%, #fef3c7 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #f59e0b; }}
        .security-alert {{ background: linear-gradient(135deg, #fef7e0 0%, #fed7aa 100%); padding: 20px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #f97316; }}
        .features-grid {{ background: linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #8b5cf6; }}
        .tips-section {{ background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #10b981; }}
        .support-box {{ background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #3b82f6; }}
        .welcome-tag {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 6px 15px; border-radius: 25px; font-size: 12px; font-weight: bold; display: inline-block; }}
        .credential-item {{ background: white; padding: 12px; margin: 8px 0; border-radius: 8px; border-left: 3px solid #10b981; }}
        .feature-item {{ margin: 10px 0; padding: 8px 0; }}
        .tip-item {{ margin: 8px 0; padding: 5px 0; }}
        ol {{ padding-left: 25px; }}
        ol li {{ margin: 10px 0; padding: 5px 0; }}
        .sparkle {{ color: #f59e0b; }}
        .heart {{ color: #ef4444; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0; font-size: 32px; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">🎉 Welcome to Saurara!</h1>
            <p style="margin: 15px 0 0 0; font-size: 18px; opacity: 0.95; font-weight: 300;">Research & Community Excellence Platform</p>
            <div style="margin-top: 20px;">
                <span style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px; font-size: 14px;">✨ Your Journey Begins Now ✨</span>
            </div>
        </div>
        
        <div class="content">
            <p style="font-size: 19px; margin-bottom: 25px; color: #374151;">{greeting},</p>
            
            <div class="welcome-banner">
                <h2 style="margin: 0 0 10px 0; font-size: 24px;">Welcome to Our Community!</h2>
                <p style="margin: 0; font-size: 16px; opacity: 0.95;">We are thrilled to have you join our growing community of researchers, educators, and community leaders. Your account has been successfully created and you're ready to embark on your journey with us!</p>
            </div>
            
            <div class="credentials-box">
                <h3 style="color: #065f46; margin-top: 0; font-size: 20px;">Your Account Credentials</h3>
                <div class="credential-item">
                    <strong> Username:</strong> <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #374151; font-weight: bold;">{username}</code>
                </div>
                <div class="credential-item">
                    <strong>Email Address:</strong> <span style="color: #3b82f6; font-weight: 500;">{email}</span>
                </div>
                <div class="credential-item">
                    <strong>Temporary Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #92400e; font-weight: bold; border: 1px solid #f59e0b;">{password}</code>
                </div>
                <div class="credential-item">
                    <strong>Survey Code:</strong> <code style="background: #f0f9ff; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #1e40af; font-weight: bold; border: 1px solid #3b82f6;">{survey_code}</code>
                </div>
                <div class="credential-item">
                    <strong>Platform Access:</strong> <a href="http://www.saurara.org" style="color: #667eea; font-weight: 600; text-decoration: none;">www.saurara.org</a>
                </div>
            </div>
            
            <div style="text-align: center; margin: 35px 0;">
                <a href="http://www.saurara.org" class="button" style="font-size: 16px;">Access Platform Now</a>
            </div>
            
            <div class="quick-start">
                <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">Quick Start Guide</h3>
                <ol style="color: #374151;">
                    <li><strong>Visit</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                    <li><strong>Click</strong> on "Login" or "Survey Access"</li>
                    <li><strong>Enter</strong> your username and password above</li>
                    <li><strong>Complete</strong> your profile setup when ready</li>
                    <li><strong>Explore</strong> survey opportunities and platform features</li>
                    <li><strong>Connect</strong> with your organization and peers</li>
                </ol>
            </div>
            
            <div class="security-alert">
                <h3 style="color: #c2410c; margin-top: 0; font-size: 18px;"> Important Security Information</h3>
                <p style="margin-bottom: 0; color: #374151;"><strong>For your account security:</strong> Please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals. Your data privacy and security are our top priorities.</p>
            </div>
            
            <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #0ea5e9;">
                <h3 style="color: #0c4a6e; margin-top: 0; font-size: 18px;"> What Awaits You</h3>
                <p style="color: #374151; margin-bottom: 0;">As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. <strong>Every response makes a difference!</strong></p>
            </div>
            
            <div class="features-grid">
                <h3 style="color: #5b21b6; margin-top: 0; font-size: 18px;"> Platform Features</h3>
                <div class="feature-item">• <strong>Personalized survey dashboard</strong> - Tailored to your profile</div>
                <div class="feature-item">• <strong>Progress tracking</strong> - Monitor your completion status</div>
                <div class="feature-item">• <strong>Secure data handling</strong> - Privacy protection guaranteed</div>
                <div class="feature-item">• <strong>Community insights</strong> - Access research updates</div>
                <div class="feature-item">• <strong>Professional networking</strong> - Connect with peers</div>
            </div>
            
            <div class="tips-section">
                <h3 style="color: #065f46; margin-top: 0; font-size: 18px;">Getting the Most Out of Saurara</h3>
                <div class="tip-item">Complete your profile for better survey matching</div>
                <div class="tip-item">Respond to surveys thoughtfully and thoroughly</div>
                <div class="tip-item">Stay engaged with platform updates and announcements</div>
                <div class="tip-item">Reach out for support whenever needed</div>
            </div>
            
            <div class="support-box">
                <h3 style="color: #1d4ed8; margin-top: 0; font-size: 18px;">Need Assistance?</h3>
                <p style="margin-bottom: 15px; color: #374151;">Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!</p>
                <p style="margin-bottom: 0; color: #374151;"><strong>We're honored to have you as part of the Saurara family.</strong> Together, we're building a better understanding of education and community development globally.</p>
            </div>
            
            <div style="text-align: center; margin: 35px 0; padding: 25px; background: linear-gradient(135deg, #fef7e0 0%, #fed7aa 100%); border-radius: 12px;">
                <h2 style="color: #c2410c; margin: 0 0 15px 0; font-size: 22px;">Welcome Aboard! <span class="sparkle">✨</span></h2>
                <p style="color: #374151; margin: 0; font-size: 16px; font-weight: 500;">Thank you for joining the Saurara community! <span class="heart">❤️</span></p>
            </div>
        </div>
        
        <div class="footer">
            <p style="margin: 0; text-align: center; color: #4b5563; font-size: 16px;">
                <strong>Best regards,<br>The Saurara Research Team</strong>
            </p>
            <hr style="border: none; border-top: 2px solid #d1d5db; margin: 20px 0;">
            <div style="text-align: center;">
                <span class="welcome-tag">WELCOME</span>
            </div>
            <p style="margin: 15px 0 0 0; text-align: center; color: #6b7280; font-size: 14px;">
                Platform: <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                Support: <a href="mailto:info@saurara.org" style="color: #667eea;">info@saurara.org</a><br>
                Stay Connected: Follow us for updates and insights
            </p>
        </div>
    </div>
</body>
</html>"""

        return jsonify({
            'success': True,
            'preview': {
                'subject': 'Welcome to Saurara Platform',
                'recipient': email,
                'text': text_content,
                'html': html_content
            }
        })

    except Exception as e:
        logger.error(f"Error generating welcome email preview: {str(e)}")
        return jsonify({'error': 'Failed to generate email preview'}), 500

@app.route('/api/initialize-survey-data', methods=['POST'])
def initialize_survey_data():
    """Initialize test survey data including organization types, organizations, and survey templates"""
    try:
        # Check if we already have survey templates
        existing_templates = SurveyTemplate.query.count()
        if existing_templates > 0:
            return jsonify({
                'message': f'Survey data already exists ({existing_templates} templates found)',
                'existing_templates': existing_templates
            }), 200
        
        # 1. Create organization types if they don't exist
        church_type = OrganizationType.query.filter_by(type='CHURCH').first()
        if not church_type:
            church_type = OrganizationType(type='CHURCH')
            db.session.add(church_type)
            db.session.flush()
        
        # 2. Create a sample organization
        sample_org = Organization.query.filter_by(name='Sample Church Organization').first()
        if not sample_org:
            sample_org = Organization(
                name='Sample Church Organization',
                type=church_type.id,
                website='https://samplechurch.org',
                highest_level_of_education='Seminary'
            )
            db.session.add(sample_org)
            db.session.flush()
        
        # 3. Create a survey template version
        template_version = SurveyTemplateVersion(
            name='2024.11.03 Health of Theol Edu',
            description='Assessing the effectiveness of Theological institutions in Africa through the lens of African churches.',
            organization_id=sample_org.id
        )
        db.session.add(template_version)
        db.session.flush()
        
        # 4. Create sample questions data
        sample_questions = [
            {
                "id": 1,
                "question_text": "What is the name of your church?",
                "question_type_id": 1,  # Short text
                "section": "Church Information",
                "order": 1,
                "is_required": True,
                "config": {"placeholder": "Enter your church name"}
            },
            {
                "id": 2,
                "question_text": "How long has your church been established?",
                "question_type_id": 2,  # Single choice
                "section": "Church Information",
                "order": 2,
                "is_required": True,
                "config": {
                    "options": [
                        {"value": "less_than_5", "label": "Less than 5 years"},
                        {"value": "5_to_10", "label": "5-10 years"},
                        {"value": "10_to_25", "label": "10-25 years"},
                        {"value": "more_than_25", "label": "More than 25 years"}
                    ]
                }
            },
            {
                "id": 3,
                "question_text": "Does your church have a formal theological education program?",
                "question_type_id": 3,  # Yes/No
                "section": "Theological Education",
                "order": 3,
                "is_required": True,
                "config": {"yes_label": "Yes", "no_label": "No"}
            },
            {
                "id": 4,
                "question_text": "What are the main challenges your church faces in theological education?",
                "question_type_id": 6,  # Long text/paragraph
                "section": "Theological Education",
                "order": 4,
                "is_required": False,
                "config": {"placeholder": "Please describe the main challenges..."}
            }
        ]
        
        # Add more questions to reach 47 total
        for i in range(5, 48):
            sample_questions.append({
                "id": i,
                "question_text": f"Sample question {i} about theological education and church effectiveness?",
                "question_type_id": 1,  # Short text
                "section": "Additional Questions" if i > 25 else "Theological Education",
                "order": i,
                "is_required": False,
                "config": {"placeholder": f"Answer for question {i}"}
            })
        
        # 5. Create sample sections
        sample_sections = {
            "Church Information": 0,
            "Theological Education": 1,
            "Additional Questions": 2
        }
        
        # 6. Create the survey template
        survey_template = SurveyTemplate(
            version_id=template_version.id,
            survey_code=str(uuid.uuid4()),
            questions=sample_questions,
            sections=sample_sections
        )
        db.session.add(survey_template)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Survey data initialized successfully',
            'organization_type_id': church_type.id,
            'organization_id': sample_org.id,
            'template_version_id': template_version.id,
            'survey_template_id': survey_template.id,
            'questions_count': len(sample_questions),
            'sections_count': len(sample_sections),
            'survey_code': survey_template.survey_code
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing survey data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to initialize survey data: {str(e)}'}), 500

# Add Report Builder endpoints before the main execution block

@app.route('/api/reports/data', methods=['POST'])
def generate_report_data():
    """Generate report data based on configuration"""
    try:
        config = request.get_json() or {}
        data_scope = config.get('dataScope', {})
        metrics = config.get('metrics', [])
        dimensions = config.get('dimensions', [])
        chart_config = config.get('chartConfig', {})
        
        # Build base query
        query = db.session.query(SurveyResponse).join(User).join(Organization, isouter=True).join(GeoLocation, isouter=True)
        
        # Apply data scope filters
        if data_scope.get('surveys'):
            query = query.filter(SurveyResponse.template_id.in_(data_scope['surveys']))
        
        if data_scope.get('dateRange', {}).get('start'):
            start_date = datetime.strptime(data_scope['dateRange']['start'], '%Y-%m-%d')
            query = query.filter(SurveyResponse.created_at >= start_date)
            
        if data_scope.get('dateRange', {}).get('end'):
            end_date = datetime.strptime(data_scope['dateRange']['end'], '%Y-%m-%d')
            query = query.filter(SurveyResponse.created_at <= end_date)
        
        # Get the responses
        responses = query.all()
        
        # Process data based on metrics and dimensions
        results = []
        
        if 'response_count' in metrics:
            if 'organization' in dimensions:
                # Group by organization
                org_counts = {}
                for response in responses:
                    org_name = response.user.organization.name if response.user.organization else 'Unknown'
                    org_counts[org_name] = org_counts.get(org_name, 0) + 1
                
                for org_name, count in org_counts.items():
                    results.append({
                        'name': org_name,
                        'value': count,
                        'metric': 'response_count',
                        'dimension': 'organization'
                    })
            
            elif 'geographic_location' in dimensions:
                # Group by country
                geo_counts = {}
                for response in responses:
                    if response.user.organization and response.user.organization.geo_location:
                        country = response.user.organization.geo_location.country or 'Unknown'
                    else:
                        country = 'Unknown'
                    geo_counts[country] = geo_counts.get(country, 0) + 1
                
                for country, count in geo_counts.items():
                    results.append({
                        'name': country,
                        'value': count,
                        'metric': 'response_count',
                        'dimension': 'geographic_location'
                    })
            
            elif 'survey_section' in dimensions:
                # Group by survey section (analyze answers)
                section_counts = {}
                for response in responses:
                    if response.answers:
                        for answer_key, answer_value in response.answers.items():
                            # Extract section from question structure
                            section = extract_section_from_answer_key(answer_key)
                            section_counts[section] = section_counts.get(section, 0) + 1
                
                for section, count in section_counts.items():
                    results.append({
                        'name': section,
                        'value': count,
                        'metric': 'response_count',
                        'dimension': 'survey_section'
                    })
            
            else:
                # Overall response count
                results.append({
                    'name': 'Total Responses',
                    'value': len(responses),
                    'metric': 'response_count',
                    'dimension': 'total'
                })
        
        if 'completion_rate' in metrics:
            completed_responses = len([r for r in responses if r.status == 'completed'])
            total_responses = len(responses)
            completion_rate = (completed_responses / total_responses * 100) if total_responses > 0 else 0
            
            results.append({
                'name': 'Completion Rate',
                'value': round(completion_rate, 2),
                'metric': 'completion_rate',
                'dimension': 'percentage'
            })
        
        if 'unique_respondents' in metrics:
            unique_users = len(set([r.user_id for r in responses]))
            results.append({
                'name': 'Unique Respondents',
                'value': unique_users,
                'metric': 'unique_respondents',
                'dimension': 'count'
            })
        
        return jsonify({
            'success': True,
            'results': results,
            'total_records': len(responses),
            'config': config
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating report data: {str(e)}")
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500

def extract_section_from_answer_key(answer_key):
    """Extract section name from answer key - this depends on your answer structure"""
    # Assuming answer keys are structured like "section_name_question_id" or similar
    # Adjust this based on your actual answer structure
    if '_' in answer_key:
        parts = answer_key.split('_')
        return parts[0] if len(parts) > 1 else 'Unknown Section'
    return 'General'

@app.route('/api/reports/templates', methods=['GET'])
def get_report_templates():
    """Get saved report templates"""
    try:
        # Get all public templates and templates created by current user
        user_id = request.args.get('user_id')  # Pass user_id as query parameter
        
        if user_id:
            templates = ReportTemplate.query.filter(
                db.or_(
                    ReportTemplate.is_public == True,
                    ReportTemplate.created_by == user_id
                )
            ).order_by(ReportTemplate.created_at.desc()).all()
        else:
            # If no user_id provided, return only public templates
            templates = ReportTemplate.query.filter_by(is_public=True).order_by(ReportTemplate.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'templates': [template.to_dict() for template in templates]
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching report templates: {str(e)}")
        return jsonify({'error': f'Failed to fetch templates: {str(e)}'}), 500

@app.route('/api/reports/templates', methods=['POST'])
def save_report_template():
    """Save a report template"""
    try:
        data = request.get_json() or {}
        name = data.get('name')
        description = data.get('description', '')
        config = data.get('config', {})
        created_by = data.get('created_by')  # User ID of the creator
        is_public = data.get('is_public', False)
        
        if not name:
            return jsonify({'error': 'Template name is required'}), 400
            
        if not created_by:
            return jsonify({'error': 'Creator user ID is required'}), 400
        
        # Create new report template
        template = ReportTemplate(
            name=name,
            description=description,
            config=config,
            created_by=created_by,
            is_public=is_public
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Template saved successfully',
            'template': template.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving report template: {str(e)}")
        return jsonify({'error': f'Failed to save template: {str(e)}'}), 500

@app.route('/api/reports/templates/<int:template_id>', methods=['DELETE'])
def delete_report_template(template_id):
    """Delete a report template"""
    try:
        template = ReportTemplate.query.get_or_404(template_id)
        
        # Check if user has permission to delete (creator or admin)
        user_id = request.args.get('user_id')
        if user_id and str(template.created_by) != str(user_id):
            # For now, allow deletion. In a full implementation, check admin role
            pass
        
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Template deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting report template: {str(e)}")
        return jsonify({'error': f'Failed to delete template: {str(e)}'}), 500


# ---------- Email Templates CRUD Endpoints ----------
def render_email_template(template_content, **kwargs):
    """Render email template with provided variables"""
    if not template_content:
        return template_content
    
    try:
        # Simple template variable replacement using {{variable}} syntax
        rendered = template_content
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            rendered = rendered.replace(placeholder, str(value) if value is not None else '')
        return rendered
    except Exception as e:
        logger.error(f"Error rendering email template: {str(e)}")
        return template_content

def get_email_template_by_type_and_organization(template_type, organization_id=None):
    """Get email template by type; prefer org-specific when org id is provided."""
    try:
        name_map = {
            'welcome':  'Default Welcome Email',
            'reminder': 'Default Reminder Email',
            'invitation': 'Default Invitation Email',
        }
        key = (template_type or '').lower()
        if key not in name_map:
            return None, 400, f'Unknown template type: {template_type}'
        template_name = name_map[key]

        template = None

        # 1) If org provided, try org-specific matches first
        if organization_id is not None:
            conds = [EmailTemplate.name.ilike(f'%{key}%')]
            # Optional synonyms
            if key == 'reminder':
                conds.append(EmailTemplate.name.ilike('%reminder%'))
            if key == 'welcome':
                conds.append(EmailTemplate.name.ilike('%welcome%'))

            template = (EmailTemplate.query
                        .filter(EmailTemplate.organization_id == organization_id)
                        .filter(or_(*conds))
                        .order_by(EmailTemplate.id.desc())
                        .first())

            # If an exact name exists for the org, prefer it
            if not template:
                template = (EmailTemplate.query
                            .filter(EmailTemplate.organization_id == organization_id,
                                    EmailTemplate.name == template_name)
                            .first())

        # 2) Public template with exact canonical name
        if not template:
            template = EmailTemplate.query.filter_by(name=template_name, is_public=True).first()

        # 3) Global (NULL org) exact canonical name
        if not template:
            template = (EmailTemplate.query
                        .filter(EmailTemplate.name == template_name,
                                EmailTemplate.organization_id.is_(None))
                        .first())

        # 4) Last resort: any template with canonical name
        if not template:
            template = EmailTemplate.query.filter_by(name=template_name).first()

        if not template:
            return None, 404, f'Template not found for type: {template_type}'

        return template, 200, 'success'
    except Exception as e:
        logger.error(f"Error getting email template by type and organization: {e}")
        return None, 500, f'Failed to get email template: {e}'

@app.route('/api/email-templates/by-type/<template_type>', methods=['GET'])
def get_email_template_by_type(template_type):
    """Get email template by type (welcome, reminder, etc.)"""
    try:
        org_id = request.args.get('organization_id', type=int)
        template, status, msg = get_email_template_by_type_and_organization(template_type, org_id)
        if status != 200:
            return jsonify({'error': msg}), status
        return jsonify({
            'id': template.id,
            'name': template.name,
            'subject': template.subject,
            'html_body': template.html_body,
            'text_body': template.text_body,
            'organization_id': template.organization_id,
            'is_public': getattr(template, 'is_public', False)
        }), 200
    except Exception as e:
        logger.error(f"Error fetching template by type: {e}")
        return jsonify({'error': f'Failed to fetch template: {e}'}), 500

@app.route('/api/email-templates/public-reminder-templates', methods=['GET'])
def get_public_reminder_templates():
    """Get all public email templates that can be used for reminders"""
    try:
        # Get all public templates that could be used for reminders
        templates = EmailTemplate.query.filter(
            EmailTemplate.is_public == True,
            db.or_(
                EmailTemplate.name.ilike('%reminder%'),
                EmailTemplate.name.ilike('%notification%'),
                EmailTemplate.name.ilike('%survey%')
            )
        ).order_by(EmailTemplate.name).all()
        
        template_list = []
        for template in templates:
            template_list.append({
                'id': template.id,
                'name': template.name,
                'subject': template.subject,
                'organization_id': template.organization_id,
                'organization_name': template.organization.name if template.organization else 'System Default'
            })
        
        return jsonify({
            'success': True,
            'templates': template_list
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting public reminder templates: {str(e)}")
        return jsonify({'error': f'Failed to get public reminder templates: {str(e)}'}), 500

@app.route('/api/email-templates/public-welcome-templates', methods=['GET'])
def get_public_welcome_templates():
    """Get all public email templates that can be used for welcome emails"""
    try:
        # Get all public templates that could be used for welcome emails
        templates = EmailTemplate.query.filter(
            EmailTemplate.is_public == True,
            db.or_(
                EmailTemplate.name.ilike('%welcome%'),
                EmailTemplate.name.ilike('%greeting%'),
                EmailTemplate.name.ilike('%onboard%')
            )
        ).order_by(EmailTemplate.name).all()
        
        template_list = []
        for template in templates:
            template_list.append({
                'id': template.id,
                'name': template.name,
                'subject': template.subject,
                'organization_id': template.organization_id,
                'organization_name': template.organization.name if template.organization else 'System Default'
            })
        
        return jsonify({
            'success': True,
            'templates': template_list
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting public welcome templates: {str(e)}")
        return jsonify({'error': f'Failed to get public welcome templates: {str(e)}'}), 500

@app.route('/api/email-templates/render-preview', methods=['POST'])
def render_email_template_preview():
    """Render email template preview with provided variables"""
    try:
        data = request.get_json(silent=True) or {}
        template_type = data.get('template_type')
        template_id   = data.get('template_id')

        if not template_type and not template_id:
            return jsonify({'error': 'Either template_type or template_id is required'}), 400

        # Accept org id from JSON or ?organization_id=...
        organization_id = data.get('organization_id')
        if organization_id is None:
            organization_id = request.args.get('organization_id', type=int)

        variables = data.get('variables', {}) or {}

        # Fetch template by id or by type (org-aware if provided)
        if template_id:
            template = EmailTemplate.query.get(template_id)
            if not template:
                return jsonify({'error': f'Template with ID {template_id} not found'}), 404
        else:
            template, status_code, message = get_email_template_by_type_and_organization(
                template_type, organization_id
            )
            if status_code != 200:
                return jsonify({'error': message}), status_code

        # Render
        rendered_subject = render_email_template(template.subject or '', **variables)
        rendered_html    = render_email_template(template.html_body or '', **variables)
        rendered_text    = render_email_template(template.text_body or '', **variables)

        return jsonify({
            'subject': rendered_subject,
            'html_body': rendered_html,
            'text_body': rendered_text,
            'template_name': template.name,
            'organization_id_used': template.organization_id  # helpful for debugging
        }), 200
    except Exception as e:
        logger.error(f"Error rendering email template preview: {e}")
        return jsonify({'error': f'Failed to render template preview: {e}'}), 500

@app.route('/api/email-templates', methods=['GET'])
def get_email_templates():
    """Get email templates, optionally filtered by organization"""
    try:
        organization_id = request.args.get('organization_id')
        filter_organization_id = request.args.get('filter_organization_id')
        
        logger.info(f"[EMAIL_TEMPLATES] Fetching templates - organization_id: {organization_id}, filter_organization_id: {filter_organization_id}")
        
        # Start with base query, include organization relationship for organization name
        query = EmailTemplate.query.options(joinedload(EmailTemplate.organization))
        
        # Apply organization filter
        if organization_id:
            # Show public templates OR templates from the specified organization
            query = query.filter(
                db.or_(EmailTemplate.is_public == True, EmailTemplate.organization_id == organization_id)
            )
        elif filter_organization_id:
            # Filter by specific organization (for admin filtering)
            query = query.filter(EmailTemplate.organization_id == filter_organization_id)
        # If no filters specified, show all templates (for admin inventory view)
        
        templates = query.order_by(EmailTemplate.created_at.desc()).all()
        logger.info(f"[EMAIL_TEMPLATES] Found {len(templates)} templates")
        
        template_dicts = []
        for template in templates:
            try:
                template_dict = template.to_dict()
                template_dicts.append(template_dict)
            except Exception as template_error:
                logger.error(f"[EMAIL_TEMPLATES] Error converting template {template.id} to dict: {str(template_error)}")
                continue
        
        logger.info(f"[EMAIL_TEMPLATES] Successfully converted {len(template_dicts)} templates to dict")
        return jsonify({'success': True, 'templates': template_dicts}), 200
        
    except Exception as e:
        logger.error(f"[EMAIL_TEMPLATES] Error fetching email templates: {str(e)}")
        logger.error(f"[EMAIL_TEMPLATES] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"[EMAIL_TEMPLATES] Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Failed to fetch templates: {str(e)}'}), 500

@app.route('/api/email-templates/all', methods=['GET'])
def get_all_email_templates():
    """Dedicated endpoint to fetch all email templates with enhanced debugging"""
    try:
        logger.info("[EMAIL_TEMPLATES_ALL] Starting to fetch all email templates")
        
        # Check database connection
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            logger.info("[EMAIL_TEMPLATES_ALL] Database connection verified")
        except Exception as db_error:
            logger.error(f"[EMAIL_TEMPLATES_ALL] Database connection error: {str(db_error)}")
            return jsonify({'error': 'Database connection failed', 'details': str(db_error)}), 500
        
        # Check if EmailTemplate table exists and has data
        try:
            template_count = EmailTemplate.query.count()
            logger.info(f"[EMAIL_TEMPLATES_ALL] Total templates in database: {template_count}")
        except Exception as count_error:
            logger.error(f"[EMAIL_TEMPLATES_ALL] Error counting templates: {str(count_error)}")
            return jsonify({'error': 'Failed to access email templates table', 'details': str(count_error)}), 500
        
        if template_count == 0:
            logger.info("[EMAIL_TEMPLATES_ALL] No templates found in database")
            return jsonify({
                'success': True, 
                'templates': [], 
                'message': 'No email templates found in database',
                'count': 0
            }), 200
        
        # Fetch templates with organization data
        try:
            query = EmailTemplate.query.options(joinedload(EmailTemplate.organization))
            templates = query.order_by(EmailTemplate.created_at.desc()).all()
            logger.info(f"[EMAIL_TEMPLATES_ALL] Successfully fetched {len(templates)} templates from database")
        except Exception as fetch_error:
            logger.error(f"[EMAIL_TEMPLATES_ALL] Error fetching templates: {str(fetch_error)}")
            return jsonify({'error': 'Failed to fetch templates from database', 'details': str(fetch_error)}), 500
        
        # Convert templates to dictionaries
        template_dicts = []
        conversion_errors = []
        
        for i, template in enumerate(templates):
            try:
                template_dict = {
                    'id': template.id,
                    'organization_id': template.organization_id,
                    'organization_name': template.organization.name if template.organization else f'Unknown (ID: {template.organization_id})',
                    'name': template.name or 'Unnamed Template',
                    'subject': template.subject or '',
                    'html_body': template.html_body or '',
                    'text_body': template.text_body or '',
                    'is_public': bool(template.is_public),
                    'created_at': template.created_at.isoformat() if template.created_at else None,
                    'updated_at': template.updated_at.isoformat() if template.updated_at else None,
                }
                template_dicts.append(template_dict)
                logger.debug(f"[EMAIL_TEMPLATES_ALL] Converted template {i+1}/{len(templates)}: {template.name}")
                
            except Exception as template_error:
                error_msg = f"Template ID {template.id}: {str(template_error)}"
                conversion_errors.append(error_msg)
                logger.error(f"[EMAIL_TEMPLATES_ALL] Error converting template {template.id} to dict: {str(template_error)}")
                continue
        
        logger.info(f"[EMAIL_TEMPLATES_ALL] Successfully converted {len(template_dicts)} templates, {len(conversion_errors)} errors")
        
        response_data = {
            'success': True,
            'templates': template_dicts,
            'count': len(template_dicts),
            'total_in_db': template_count,
            'conversion_errors': conversion_errors if conversion_errors else None
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"[EMAIL_TEMPLATES_ALL] Unexpected error: {str(e)}")
        logger.error(f"[EMAIL_TEMPLATES_ALL] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"[EMAIL_TEMPLATES_ALL] Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'error': 'Unexpected error occurred while fetching email templates',
            'details': str(e),
            'type': type(e).__name__
        }), 500


@app.route('/api/email-templates', methods=['POST'])
def save_email_template():
    """Create a new email template"""
    try:
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        subject = data.get('subject', '').strip()
        html_body = data.get('html_body', '').strip()
        text_body = data.get('text_body', '').strip()
        organization_id = data.get('organization_id')
        is_public = data.get('is_public', False)

        # Validation
        if not all([name, subject, html_body, organization_id]):
            return jsonify({'error': 'name, subject, html_body and organization_id are required'}), 400

        # Validate organization exists
        organization = Organization.query.get(organization_id)
        if not organization:
            return jsonify({'error': f'Organization with ID {organization_id} does not exist'}), 400

        # Check for duplicate name within organization
        existing = EmailTemplate.query.filter_by(
            organization_id=organization_id, 
            name=name
        ).first()
        if existing:
            return jsonify({'error': f'Email template with name "{name}" already exists for this organization'}), 400

        template = EmailTemplate(
            name=name,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            organization_id=organization_id,
            is_public=is_public
        )
        db.session.add(template)
        db.session.commit()
        
        logger.info(f"Created email template: {template.name} for organization {organization.name}")
        return jsonify({'success': True, 'template': template.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving email template: {str(e)}")
        return jsonify({'error': f'Failed to save template: {str(e)}'}), 500


@app.route('/api/email-templates/<int:template_id>', methods=['PUT'])
def update_email_template(template_id):
    """Update an existing email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        data = request.get_json() or {}

        # Update fields with validation
        if 'name' in data:
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'error': 'Template name cannot be empty'}), 400
            
            # Check for duplicate name within organization (excluding current template)
            existing = EmailTemplate.query.filter_by(
                organization_id=template.organization_id, 
                name=new_name
            ).filter(EmailTemplate.id != template_id).first()
            if existing:
                return jsonify({'error': f'Email template with name "{new_name}" already exists for this organization'}), 400
            
            template.name = new_name

        if 'subject' in data:
            new_subject = data.get('subject', '').strip()
            if not new_subject:
                return jsonify({'error': 'Subject cannot be empty'}), 400
            template.subject = new_subject

        if 'html_body' in data:
            new_html_body = data.get('html_body', '').strip()
            if not new_html_body:
                return jsonify({'error': 'HTML body cannot be empty'}), 400
            template.html_body = new_html_body

        if 'text_body' in data:
            template.text_body = data.get('text_body', '').strip()

        if 'is_public' in data:
            template.is_public = data.get('is_public', False)

        if 'organization_id' in data and data.get('organization_id'):
            new_org_id = data.get('organization_id')
            # Validate new organization exists
            organization = Organization.query.get(new_org_id)
            if not organization:
                return jsonify({'error': f'Organization with ID {new_org_id} does not exist'}), 400
            template.organization_id = new_org_id

        db.session.commit()
        logger.info(f"Updated email template: {template.name} for organization {template.organization_id}")
        return jsonify({'success': True, 'template': template.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email template: {str(e)}")
        return jsonify({'error': f'Failed to update template: {str(e)}'}), 500


@app.route('/api/email-templates/<int:template_id>', methods=['DELETE'])
def delete_email_template(template_id):
    """Delete an email template"""
    try:
        template = EmailTemplate.query.get_or_404(template_id)
        template_name = template.name
        organization_name = template.organization.name if template.organization else 'Unknown'
        
        # Delete the template itself
        db.session.delete(template)
        db.session.commit()
        
        logger.info(f"Deleted email template '{template_name}' from organization '{organization_name}'")
        return jsonify({'success': True, 'message': 'Template deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting email template: {str(e)}")
        return jsonify({'error': f'Failed to delete template: {str(e)}'}), 500


@app.route('/api/reports/export', methods=['POST'])
def export_report():
    """Export report data in various formats"""
    try:
        config = request.get_json() or {}
        format_type = config.get('format', 'json')  # json, csv, xlsx
        data = config.get('data', [])
        
        if format_type == 'csv':
            # Generate CSV
            import csv
            import io
            
            output = io.StringIO()
            if data:
                fieldnames = data[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            response = app.response_class(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=report.csv'}
            )
            return response
        
        else:
            # Default to JSON
            return jsonify({
                'success': True,
                'data': data,
                'format': format_type
            }), 200
            
    except Exception as e:
        logger.error(f"Error exporting report: {str(e)}")
        return jsonify({'error': f'Failed to export report: {str(e)}'}), 500

@app.route('/api/reports/analytics/overview', methods=['GET'])
def get_analytics_overview():
    """Get overview analytics for the report builder"""
    try:
        # Get basic statistics
        total_responses = SurveyResponse.query.count()
        completed_responses = SurveyResponse.query.filter_by(status='completed').count()
        total_organizations = Organization.query.count()
        total_users = User.query.count()
        
        # Geographic distribution
        geo_query = db.session.query(
            GeoLocation.country, 
            db.func.count(Organization.id).label('org_count')
        ).join(Organization, GeoLocation.id == Organization.address).group_by(GeoLocation.country).all()
        
        geographic_data = [{'country': row.country or 'Unknown', 'count': row.org_count} for row in geo_query]
        
        # Organization types
        org_type_query = db.session.query(
            OrganizationType.type,
            db.func.count(Organization.id).label('org_count')
        ).join(Organization, OrganizationType.id == Organization.type).group_by(OrganizationType.type).all()
        
        org_type_data = [{'type': row.type, 'count': row.org_count} for row in org_type_query]
        
        return jsonify({
            'success': True,
            'overview': {
                'total_responses': total_responses,
                'completed_responses': completed_responses,
                'completion_rate': round((completed_responses / total_responses * 100) if total_responses > 0 else 0, 2),
                'total_organizations': total_organizations,
                'total_users': total_users
            },
            'geographic_distribution': geographic_data,
            'organization_types': org_type_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching analytics overview: {str(e)}")
        return jsonify({'error': f'Failed to fetch analytics overview: {str(e)}'}), 500

# ---------- Textual Analytics (Qualitative) ----------

def create_sample_dataframe_for_analytics(survey_type, response_id, selected_surveys):
    """Create a pandas DataFrame from sample data that mimics the database structure for text analytics."""
    import json
    import os
    import pandas as pd
    
    # Define the sample data directory path
    sample_data_dir = os.path.join(os.path.dirname(__file__), '..', 'BoskoPartnersFrontend', 'public', 'sample-data')
    
    # Define text fields to analyze by survey type
    text_fields_map = {
        'church': [
            'other_training_areas',
            'why_choose_institution', 
            'expectations_met_explanation',
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ],
        'institution': [
            'other_training_areas',
            'why_choose_institution',
            'expectations_met_explanation', 
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ],
        'non_formal': [
            'why_choose_non_formal',
            'better_preparation_areas',
            'different_preparation_explanation',
            'ongoing_support_description',
            'better_ongoing_support'
        ]
    }
    
    # Map survey types to file names
    file_map = {
        'church': 'church-survey-responses.json',
        'institution': 'institution-survey-responses.json', 
        'non_formal': 'non-formal-survey-responses.json'
    }
    
    # Determine which files to load
    files_to_load = []
    if survey_type and survey_type in file_map:
        files_to_load = [survey_type]
    else:
        files_to_load = ['church', 'institution', 'non_formal']
    
    rows = []
    question_id_counter = 1
    
    for survey_key in files_to_load:
        file_path = os.path.join(sample_data_dir, file_map[survey_key])
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            text_fields = text_fields_map.get(survey_key, [])
            
            for response in data.get('responses', []):
                response_id_val = response.get('id', 0)
                
                # Extract text responses from this survey response
                for field in text_fields:
                    text_value = response.get(field, '').strip()
                    if text_value and len(text_value) > 5:  # Only include meaningful text
                        rows.append({
                            "response_id": response_id_val,
                            "question_id": question_id_counter,
                            "question_type": "paragraph" if len(text_value) > 100 else "short_text",
                            "answer": text_value
                        })
                        question_id_counter += 1
    
    df = pd.DataFrame(rows)
    
    # Apply filters if needed
    if selected_surveys:
        try:
            selected_ids = [int(id.strip()) for id in selected_surveys.split(',')]
            df = df[df['response_id'].isin(selected_ids)]
        except (ValueError, AttributeError):
            pass
    
    if response_id:
        try:
            target_id = int(response_id)
            df = df[df['response_id'] == target_id]
        except (ValueError, TypeError):
            pass
    
    return df

def get_sample_text_analytics(survey_type, response_id, selected_surveys):
    """Return sample text analytics using proper NLP analysis from text_analytics.py module."""
    try:
        # Create a DataFrame from sample data that mimics the database structure
        df = create_sample_dataframe_for_analytics(survey_type, response_id, selected_surveys)
        
        if df.empty:
            return jsonify({'success': True, 'results': []}), 200
        
        # Import text analytics module
        # Use the same NLP analysis as production route - handles all dataset sizes
        try:
            from text_analytics import run_full_analysis
            
            # Create a temporary DataFrame with the required structure for run_full_analysis
            temp_df = df.copy()
            
            # Run full NLP analysis (handles small datasets properly)
            analyzed_df = run_full_analysis(db.session, SurveyResponse, Question)
            
            # Filter to only the responses we have in our sample data
            response_ids = df['response_id'].unique()
            analyzed_df = analyzed_df[analyzed_df['response_id'].isin(response_ids)]
            
            # Merge the analysis results back to our original DataFrame
            df = df.merge(
                analyzed_df[['response_id', 'question_id', 'sentiment', 'topic', 'cluster']], 
                on=['response_id', 'question_id'], 
                how='left',
                suffixes=('', '_analyzed')
            )
            
            # Use analyzed values where available, keep original sentiment if already computed
            df['sentiment'] = df['sentiment_analyzed'].fillna(df.get('sentiment', 'neutral'))
            df['topic'] = df['topic'].fillna(0).astype(int)
            df['cluster'] = df['cluster'].fillna(0).astype(int)
            
            # Add meaningful labels (simplified for sample data)
            df['topic_label'] = df['topic'].apply(lambda x: f"Topic {x}" if x != -1 else "Outlier Topic")
            df['topic_description'] = df['topic'].apply(lambda x: f"Topic {x} responses" if x != -1 else "Outlier responses")
            df['cluster_label'] = df['cluster'].apply(lambda x: f"Cluster {x}")
            df['cluster_description'] = df['cluster'].apply(lambda x: f"Cluster {x} responses")
            
            # Clean up temporary columns
            df = df.drop(columns=[col for col in df.columns if col.endswith('_analyzed')], errors='ignore')
            
        except Exception as nlp_error:
            logger.warning(f"NLP analysis failed, falling back to simple analysis: {str(nlp_error)}")
            # Fallback to simple analysis if NLP fails
            from text_analytics import _clean_text, _sentiment_label
            
            df["clean_text"] = df["answer"].apply(_clean_text)
            df["sentiment"] = df["clean_text"].apply(_sentiment_label)
            df["topic"] = 0
            df["topic_label"] = "General Ministry"
            df["topic_description"] = "General ministry-related responses"
            df["cluster"] = 0
            df["cluster_label"] = "All Responses"
            df["cluster_description"] = "All responses grouped together"
        
        # Convert to the format expected by the frontend
        results = df.drop(columns=['clean_text'], errors='ignore').to_dict(orient='records')
        
        return jsonify({'success': True, 'results': results}), 200
        
    except Exception as e:
        logger.error(f"Error running sample text analytics: {str(e)}")
        return jsonify({'success': False, 'error': str(e), 'results': []}), 500

@app.route('/api/reports/analytics/text', methods=['GET'])
def get_textual_analytics():
    """Return sentiment, topic and cluster labels for open-ended answers."""
    try:
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        survey_type = request.args.get('survey_type')
        response_id = request.args.get('response_id')
        user_id = request.args.get('user_id')
        selected_surveys = request.args.get('selected_surveys')
        test_mode = request.args.get('test_mode', 'false').lower() == 'true'
        
        logger.info(f"Text analytics request - refresh: {refresh}, survey_type: {survey_type}, response_id: {response_id}, user_id: {user_id}, selected_surveys: {selected_surveys}, test_mode: {test_mode}")
        
        if test_mode:
            # Return sample/mock data for test mode
            logger.info("Returning sample text analytics for test mode")
            return get_sample_text_analytics(survey_type, response_id, selected_surveys)
        
        # Check if we have open-ended answers in the database before running analysis
        from text_analytics import fetch_open_ended_answers
        logger.info("Checking for open-ended answers in database...")
        open_ended_df = fetch_open_ended_answers(db.session, SurveyResponse, Question)
        logger.info(f"Found {len(open_ended_df)} open-ended answers in database")
        
        if open_ended_df.empty:
            logger.warning("No open-ended answers found in database. Returning empty results.")
            return jsonify({'success': True, 'results': [], 'message': 'No open-ended answers found in database'}), 200
        
        if refresh or not hasattr(g, 'text_analysis_df'):
            logger.info("Running full text analysis...")
            from text_analytics import run_full_analysis  # local heavy import
            try:
                g.text_analysis_df = run_full_analysis(db.session, SurveyResponse, Question)
                logger.info(f"Text analysis completed successfully. Results shape: {g.text_analysis_df.shape}")
            except ValueError as ve:
                if "No open-ended answers found in database" in str(ve):
                    logger.warning("No open-ended answers found during analysis. Returning empty results.")
                    return jsonify({'success': True, 'results': [], 'message': 'No open-ended answers found in database'}), 200
                else:
                    raise ve

        df = g.text_analysis_df.copy()
        logger.info(f"Using cached text analysis data. Shape: {df.shape}")
        
        # Apply filters if provided
        original_count = len(df)
        if survey_type:
            # Get survey responses of the specified type
            survey_responses = SurveyResponse.query.filter(
                SurveyResponse.survey_type == survey_type,
                SurveyResponse.status == 'completed'
            ).all()
            response_ids = [sr.id for sr in survey_responses]
            df = df[df['response_id'].isin(response_ids)]
            logger.info(f"Filtered by survey_type '{survey_type}'. Reduced from {original_count} to {len(df)} records.")
        
        if user_id:
            # Get user's survey responses
            user_responses = SurveyResponse.query.filter(
                SurveyResponse.user_id == user_id,
                SurveyResponse.status == 'completed'
            ).all()
            user_response_ids = [ur.id for ur in user_responses]
            df = df[df['response_id'].isin(user_response_ids)]
            logger.info(f"Filtered by user_id '{user_id}'. Reduced from {original_count} to {len(df)} records.")
        
        if selected_surveys:
            # Filter by selected survey IDs
            selected_ids = [int(id.strip()) for id in selected_surveys.split(',') if id.strip().isdigit()]
            if selected_ids:
                original_count = len(df)
                df = df[df['response_id'].isin(selected_ids)]
                logger.info(f"Filtered by selected_surveys. Reduced from {original_count} to {len(df)} records.")
        
        # Drop clean_text column and convert to records
        payload = df.drop(columns=['clean_text'], errors='ignore').to_dict(orient='records')
        logger.info(f"Returning {len(payload)} text analytics results")
        return jsonify({'success': True, 'results': payload}), 200
    except Exception as e:
        logger.error(f"Error generating text analytics: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to generate text analytics: {str(e)}', 'success': False}), 500

# Survey Assignment API Endpoints
@app.route('/api/assign-survey', methods=['POST'])
def assign_survey_to_user():
    """Assign a survey to existing user(s) and send email notifications"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Required fields
        user_ids = data.get('user_ids', [])
        template_id = data.get('template_id')
        
        if not user_ids or not template_id:
            return jsonify({'error': 'user_ids and template_id are required'}), 400
        
        # Validate template exists
        template = SurveyTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': 'Survey template not found'}), 404
        
        # Get admin info for email
        admin_user = None
        admin_name = "Administrator"
        if 'admin_id' in data:
            admin_user = User.query.get(data['admin_id'])
            if admin_user:
                admin_name = f"{admin_user.firstname} {admin_user.lastname}".strip() or admin_user.username
        
        results = {
            'total_users': len(user_ids),
            'successful_assignments': 0,
            'failed_assignments': 0,
            'successful_emails': 0,
            'failed_emails': 0,
            'details': []
        }
        
        for user_id in user_ids:
            user_result = {
                'user_id': user_id,
                'assignment_success': False,
                'email_success': False,
                'assignment_error': None,
                'email_error': None
            }
            
            try:
                # Get user
                user = User.query.get(user_id)
                if not user:
                    user_result['assignment_error'] = 'User not found'
                    results['details'].append(user_result)
                    results['failed_assignments'] += 1
                    continue
                
                # Check if email service is active for user's organization
                if user.organization_id:
                    is_active, message = is_email_service_active_for_organization(user.organization_id)
                    if not is_active:
                        user_result['assignment_error'] = f'Email service not available for organization: {message}'
                        results['details'].append(user_result)
                        results['failed_assignments'] += 1
                        continue
                
                # Use existing user survey code if available; otherwise, generate one and save to user
                survey_code = user.survey_code or str(uuid.uuid4())
                if not user.survey_code:
                    user.survey_code = survey_code
                
                # Create survey response record
                survey_response = SurveyResponse(
                    template_id=template_id,
                    user_id=user_id,
                    answers={},
                    status='pending',
                    survey_code=survey_code,
                    start_date=None,
                    end_date=None
                )
                
                db.session.add(survey_response)
                db.session.flush()  # Get the ID but don't commit yet
                
                user_result['assignment_success'] = True
                user_result['survey_response_id'] = survey_response.id
                user_result['survey_code'] = survey_code
                results['successful_assignments'] += 1
                
                # Send assignment email
                try:
                    email_result = send_survey_assignment_email(
                        to_email=user.email,
                        username=user.username,
                        password=user.password,
                        survey_code=survey_code,
                        firstname=user.firstname,
                        organization_name=user.organization.name if user.organization else None,
                        survey_name=template.version.name if template.version else "Survey",
                        assigned_by=admin_name
                    )
                    
                    if email_result.get('success'):
                        user_result['email_success'] = True
                        results['successful_emails'] += 1
                        logger.info(f"Survey assignment email sent to user {user_id}: {user.email}")
                    else:
                        user_result['email_error'] = email_result.get('error', 'Unknown email error')
                        results['failed_emails'] += 1
                        logger.error(f"Failed to send assignment email to user {user_id}: {user_result['email_error']}")
                
                except Exception as email_error:
                    user_result['email_error'] = str(email_error)
                    results['failed_emails'] += 1
                    logger.error(f"Exception sending assignment email to user {user_id}: {str(email_error)}")
                
            except Exception as assignment_error:
                user_result['assignment_error'] = str(assignment_error)
                results['failed_assignments'] += 1
                logger.error(f"Exception assigning survey to user {user_id}: {str(assignment_error)}")
                db.session.rollback()
                continue
            
            results['details'].append(user_result)
        
        # Commit all successful assignments
        try:
            db.session.commit()
            logger.info(f"Survey assignment completed: {results['successful_assignments']} assignments, {results['successful_emails']} emails sent")
        except Exception as commit_error:
            db.session.rollback()
            logger.error(f"Failed to commit survey assignments: {str(commit_error)}")
            return jsonify({'error': f'Failed to save assignments: {str(commit_error)}'}), 500
        
        # Calculate success rates
        assignment_success_rate = (results['successful_assignments'] / results['total_users'] * 100) if results['total_users'] > 0 else 0
        email_success_rate = (results['successful_emails'] / results['total_users'] * 100) if results['total_users'] > 0 else 0
        
        return jsonify({
            'message': f'Survey assignment completed: {results["successful_assignments"]}/{results["total_users"]} assignments, {results["successful_emails"]}/{results["total_users"]} emails sent',
            'assignment_success_rate': round(assignment_success_rate, 1),
            'email_success_rate': round(email_success_rate, 1),
            'template_name': template.version.name if template.version else "Survey",
            'assigned_by': admin_name,
            'results': results
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in survey assignment endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to assign survey: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/survey-assignments', methods=['GET'])
def get_user_survey_assignments(user_id):
    """Get all survey assignments for a specific user"""
    try:
        # Verify user exists and get organization information
        user = User.query.get_or_404(user_id)
        
        # Get organization name if user has an organization
        organization_type = "Survey"  # Default
        if user.organization_id:
            organization = Organization.query.filter_by(id=user.organization_id).first()
            if organization:
                organization_type = organization.name
        
        # Get all survey responses for this user with eager loading of relationships
        assignments = db.session.query(SurveyResponse)\
            .options(db.joinedload(SurveyResponse.template)\
                      .joinedload(SurveyTemplate.version))\
            .filter_by(user_id=user_id).all()
        logger.info(f"orgniazation_type: {organization_type}")
        logger.info(f"Found {len(assignments)} assignments for user {user_id}")
        
        result = []
        for assignment in assignments:
            try:
                template_name = "Survey"  # Default name
                survey_code = None
                
                if assignment.template:
                    # Get survey_code from SurveyTemplate table
                    survey_code = assignment.template.survey_code
                    
                    if assignment.template.version:
                        template_name = assignment.template.version.name
                    else:
                        template_name = f"Template {assignment.template.id}"
                        logger.warning(f"Template {assignment.template.id} has no version")
                else:
                    logger.warning(f"Assignment {assignment.id} has no template")
                
                assignment_data = {
                    'id': assignment.id,
                    'template_id': assignment.template_id,
                    'template_name': template_name,
                    'survey_code': survey_code,  # Now from SurveyTemplate table
                    'organization_type': organization_type,  # Add organization type
                    'status': assignment.status,
                    'created_at': assignment.created_at.isoformat() if assignment.created_at else None,
                    'start_date': assignment.start_date.isoformat() if assignment.start_date else None,
                    'end_date': assignment.end_date.isoformat() if assignment.end_date else None,
                    'updated_at': assignment.updated_at.isoformat() if assignment.updated_at else None
                }
                result.append(assignment_data)
                logger.info(f"Added assignment {assignment.id} with template name: {template_name}")
            except Exception as inner_e:
                logger.error(f"Error processing assignment {assignment.id}: {str(inner_e)}")
                continue
        
        response_data = {
            'user_id': user_id,
            'username': user.username,
            'email': user.email,
            'organization_type': organization_type,  # Add to response data as well
            'total_assignments': len(result),
            'assignments': result
        }
        
        logger.info(f"Returning {len(result)} assignments for user {user_id} with organization type: {organization_type}")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error getting user survey assignments: {str(e)}")
        return jsonify({'error': f'Failed to get user survey assignments: {str(e)}'}), 500

@app.route('/api/users/<int:user_id>/survey-assignments/<int:assignment_id>', methods=['DELETE', 'OPTIONS'])
def remove_survey_assignment(user_id, assignment_id):
    """Remove a survey assignment and its associated survey response"""
    if request.method == 'OPTIONS':
        response = jsonify({'message': 'CORS preflight successful'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
        response.headers.add('Access-Control-Allow-Methods', 'DELETE, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        return response, 200
    
    try:
        # Verify user exists
        user = User.query.get_or_404(user_id)
        
        # Find the survey response (assignment) for this user and assignment ID
        assignment = SurveyResponse.query.filter_by(
            id=assignment_id,
            user_id=user_id
        ).first()
        
        if not assignment:
            return jsonify({'error': 'Survey assignment not found for this user'}), 404
        
        # Get assignment details for logging before deletion
        template_name = "Unknown"
        if assignment.template and assignment.template.version:
            template_name = assignment.template.version.name
        
        logger.info(f"Removing survey assignment {assignment_id} (template: {template_name}) for user {user_id}")
        
        # Delete the survey response record
        db.session.delete(assignment)
        db.session.commit()
        
        logger.info(f"Successfully removed survey assignment {assignment_id} for user {user_id}")
        
        return jsonify({
            'success': True,
            'message': f'Survey assignment removed successfully',
            'removed_assignment': {
                'id': assignment_id,
                'template_name': template_name,
                'user_id': user_id
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error removing survey assignment {assignment_id} for user {user_id}: {str(e)}")
        return jsonify({'error': f'Failed to remove survey assignment: {str(e)}'}), 500

@app.route('/api/email-templates/debug', methods=['GET'])
def debug_email_templates():
    """Debug endpoint to check email templates table and data integrity"""
    try:
        debug_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'database_connection': False,
            'table_exists': False,
            'template_count': 0,
            'organization_count': 0,
            'sample_templates': [],
            'errors': []
        }
        
        # Test database connection
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            debug_info['database_connection'] = True
            logger.info("[EMAIL_DEBUG] Database connection successful")
        except Exception as db_error:
            debug_info['errors'].append(f"Database connection failed: {str(db_error)}")
            logger.error(f"[EMAIL_DEBUG] Database connection failed: {str(db_error)}")
            return jsonify(debug_info), 500
        
        # Check if email_templates table exists
        try:
            from sqlalchemy import text
            result = db.session.execute(text("SHOW TABLES LIKE 'email_templates'"))
            if result.fetchone():
                debug_info['table_exists'] = True
                logger.info("[EMAIL_DEBUG] email_templates table exists")
            else:
                debug_info['errors'].append("email_templates table does not exist")
                logger.error("[EMAIL_DEBUG] email_templates table does not exist")
                return jsonify(debug_info), 500
        except Exception as table_error:
            debug_info['errors'].append(f"Error checking table existence: {str(table_error)}")
            logger.error(f"[EMAIL_DEBUG] Error checking table existence: {str(table_error)}")
        
        # Count templates
        try:
            template_count = EmailTemplate.query.count()
            debug_info['template_count'] = template_count
            logger.info(f"[EMAIL_DEBUG] Found {template_count} email templates")
        except Exception as count_error:
            debug_info['errors'].append(f"Error counting templates: {str(count_error)}")
            logger.error(f"[EMAIL_DEBUG] Error counting templates: {str(count_error)}")
        
        # Count organizations
        try:
            org_count = Organization.query.count()
            debug_info['organization_count'] = org_count
            logger.info(f"[EMAIL_DEBUG] Found {org_count} organizations")
        except Exception as org_error:
            debug_info['errors'].append(f"Error counting organizations: {str(org_error)}")
            logger.error(f"[EMAIL_DEBUG] Error counting organizations: {str(org_error)}")
        
        # Get sample templates (first 3)
        try:
            sample_templates = EmailTemplate.query.limit(3).all()
            for template in sample_templates:
                debug_info['sample_templates'].append({
                    'id': template.id,
                    'name': template.name,
                    'organization_id': template.organization_id,
                    'is_public': template.is_public,
                    'has_html_body': bool(template.html_body and template.html_body.strip()),
                    'has_text_body': bool(template.text_body and template.text_body.strip()),
                    'created_at': template.created_at.isoformat() if template.created_at else None
                })
            logger.info(f"[EMAIL_DEBUG] Retrieved {len(sample_templates)} sample templates")
        except Exception as sample_error:
            debug_info['errors'].append(f"Error getting sample templates: {str(sample_error)}")
            logger.error(f"[EMAIL_DEBUG] Error getting sample templates: {str(sample_error)}")
        
        return jsonify(debug_info), 200
        
    except Exception as e:
        logger.error(f"[EMAIL_DEBUG] Unexpected error in debug endpoint: {str(e)}")
        return jsonify({
            'error': 'Debug endpoint failed',
            'details': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/api/test/email-templates-integration', methods=['GET'])
def test_email_templates_integration():
    """Test endpoint to verify email template integration"""
    try:
        # Test 1: Check if default templates exist
        welcome_template = EmailTemplate.query.filter_by(name='Default Welcome Email').first()
        reminder_template = EmailTemplate.query.filter_by(name='Default Reminder Email').first()
        
        # Test 2: Try to render a sample welcome email
        sample_variables = {
            'greeting': 'Dear Test User',
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'test123',
            'survey_code': 'TEST123'
        }
        
        welcome_rendered = None
        if welcome_template:
            welcome_rendered = {
                'subject': render_email_template(welcome_template.subject, **sample_variables),
                'text_preview': render_email_template(welcome_template.text_body, **sample_variables)[:200] + "..."
            }
        
        # Test 3: Check if email functions can access templates
        template_response = get_email_template_by_type('welcome')
        template_accessible = template_response[1] == 200
        
        return jsonify({
            'integration_status': 'success',
            'tests': {
                'default_templates_exist': {
                    'welcome_template': welcome_template is not None,
                    'reminder_template': reminder_template is not None
                },
                'template_rendering': {
                    'welcome_rendered': welcome_rendered is not None,
                    'sample_output': welcome_rendered
                },
                'api_access': {
                    'template_accessible_via_api': template_accessible
                }
            },
            'templates_count': EmailTemplate.query.count(),
            'message': 'Email template integration is working properly'
        }), 200
        
    except Exception as e:
        logger.error(f"Error testing email template integration: {str(e)}")
        return jsonify({
            'integration_status': 'error',
            'error': str(e),
            'message': 'Email template integration test failed'
        }), 500

@app.route('/api/test/survey-assignments', methods=['GET'])
def test_survey_assignments():
    """Test endpoint to check survey assignments in database"""
    try:
        # Get all survey responses
        all_assignments = SurveyResponse.query.all()
        
        # Get all users
        all_users = User.query.all()
        
        # Get all templates
        all_templates = SurveyTemplate.query.all()
        
        result = {
            'total_assignments': len(all_assignments),
            'total_users': len(all_users),
            'total_templates': len(all_templates),
            'assignments': [],
            'users_sample': [],
            'templates_sample': []
        }
        
        # Add sample assignments
        for assignment in all_assignments[:5]:  # First 5
            result['assignments'].append({
                'id': assignment.id,
                'user_id': assignment.user_id,
                'template_id': assignment.template_id,
                'status': assignment.status,
                'created_at': assignment.created_at.isoformat() if assignment.created_at else None
            })
        
        # Add sample users
        for user in all_users[:5]:  # First 5
            result['users_sample'].append({
                'id': user.id,
                'username': user.username,
                'email': user.email
            })
        
        # Add sample templates
        for template in all_templates[:5]:  # First 5
            result['templates_sample'].append({
                'id': template.id,
                'survey_code': template.survey_code
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error in test endpoint: {str(e)}")
        return jsonify({'error': f'Test failed: {str(e)}'}), 500

@app.route('/api/survey-templates/by-organization/<int:org_id>', methods=['GET'])
def get_survey_templates_by_organization(org_id):
    """Get survey templates for a specific organization for dropdown population"""
    try:
        logger.info(f"Fetching survey templates for organization {org_id}")
        
        # Verify organization exists
        organization = Organization.query.get(org_id)
        if not organization:
            logger.warning(f"Organization with ID {org_id} not found")
            return jsonify({'error': 'Organization not found'}), 404
        
        # Get survey templates for the organization through template versions
        # Join SurveyTemplate -> SurveyTemplateVersion -> Organization
        survey_templates = db.session.query(SurveyTemplate)\
            .join(SurveyTemplateVersion, SurveyTemplate.version_id == SurveyTemplateVersion.id)\
            .filter(SurveyTemplateVersion.organization_id == org_id)\
            .options(joinedload(SurveyTemplate.version))\
            .all()
        
        logger.info(f"Found {len(survey_templates)} survey templates for organization {org_id}")
        
        # Format response with id, survey_code, and version information
        result = []
        for template in survey_templates:
            template_data = {
                'id': template.id,
                'survey_code': template.survey_code,
                'version_name': template.version.name if template.version else f'Version {template.version_id}',
                'version_id': template.version_id,
                'created_at': template.created_at.isoformat() if template.created_at else None
            }
            result.append(template_data)
            logger.debug(f"Added template: {template.survey_code} (ID: {template.id})")
        
        response_data = {
            'organization_id': org_id,
            'organization_name': organization.name,
            'total_templates': len(result),
            'survey_templates': result
        }
        
        logger.info(f"Returning {len(result)} survey templates for organization {org_id}")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error fetching survey templates for organization {org_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch survey templates: {str(e)}'}), 500


# User Reports API endpoints for analytics
@app.route('/api/survey-responses/admin/test', methods=['GET'])
def test_admin_endpoint():
    """Test endpoint to verify admin routes are working"""
    logger.info("Test admin endpoint called")
    return jsonify({'status': 'success', 'message': 'Admin endpoint is working'}), 200

@app.route('/api/survey-responses/admin/geo', methods=['GET', 'OPTIONS'])
def get_admin_survey_responses_with_geo():
    """Get all survey responses with geographic data from geo_locations table"""
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response
    
    logger.info("Admin survey responses with geo data endpoint called")
    try:
        # Get optional survey type filter from query parameters
        survey_type_filter = request.args.get('survey_type')
        
        # Query all survey responses with user, organization, and geo location information
        logger.info("Querying survey responses with geo location data")
        responses = db.session.query(SurveyResponse)\
            .join(User, SurveyResponse.user_id == User.id)\
            .outerjoin(Organization, User.organization_id == Organization.id)\
            .outerjoin(OrganizationType, Organization.type == OrganizationType.id)\
            .outerjoin(GeoLocation, User.geo_location_id == GeoLocation.id)\
            .all()
        
        logger.info(f"Found {len(responses)} total survey responses to process")
        
        result = {
            'church': [],
            'institution': [],
            'nonFormal': [],
            'other': []
        }
        
        for response in responses:
            # Determine survey type based on user's organization type
            survey_type = 'other'  # Default
            org_type_name = None
            
            if response.user and response.user.organization and response.user.organization.organization_type:
                org_type_name = response.user.organization.organization_type.type
                logger.debug(f"Processing organization type: '{org_type_name}'")
                # Normalize organization type name for comparison
                org_type_normalized = org_type_name.lower().strip()
                
                if org_type_normalized == 'church':
                    survey_type = 'church'
                elif org_type_normalized == 'institution':
                    survey_type = 'institution'
                elif org_type_normalized in ['non_formal_organizations', 'non-formal', 'non_formal']:
                    survey_type = 'nonFormal'
                else:
                    logger.warning(f"Unknown organization type: '{org_type_name}' (normalized: '{org_type_normalized}') - assigning to 'other'")
            
            # Skip if survey type filter is applied and doesn't match
            if survey_type_filter and survey_type != survey_type_filter:
                continue
            
            # Build response data
            response_data = {
                'id': response.id,
                'survey_type': survey_type,
                'response_date': response.created_at.isoformat() if response.created_at else None,
                'template_id': response.template_id,
                'user_id': response.user_id,
                'status': response.status,
                'answers': response.answers,
                'organization_type_name': org_type_name
            }
            
            # Extract user and organization information
            if response.user:
                user = response.user
                response_data.update({
                    'user_name': f"{user.firstname or ''} {user.lastname or ''}".strip(),
                    'user_email': user.email,
                })
                
                # Get organization information
                if user.organization:
                    org = user.organization
                    response_data.update({
                        'organization_id': org.id,
                        'organization_name': org.name,
                        'organization_type_id': org.type,
                    })
                
                # Extract user details if available
                user_details_list = user.user_details
                if user_details_list and len(user_details_list) > 0:
                    user_details = user_details_list[0]
                    form_data = user_details.form_data or {}
                    
                    # Add common fields
                    response_data.update({
                        'city': form_data.get('city'),
                        'country': form_data.get('country'),
                        'physical_address': form_data.get('address'),
                        'town': form_data.get('town'),
                        'age_group': form_data.get('age_group'),
                        'education_level': form_data.get('education_level'),
                    })
                    
                    # Add survey-type specific fields
                    if survey_type == 'church':
                        response_data.update({
                            'church_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'pastor_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
                    elif survey_type == 'institution':
                        response_data.update({
                            'institution_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'president_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
                    elif survey_type == 'nonFormal':
                        response_data.update({
                            'ministry_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'leader_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
            
            # Add geographic location data from geo_locations table
            if response.user and response.user.geo_location:
                geo = response.user.geo_location
                logger.info(f"Response {response.id} geo data: lat={geo.latitude}, lng={geo.longitude}, city={geo.city}, country={geo.country}")
                response_data.update({
                    'physical_address': geo.address_line1 or response_data.get('physical_address'),
                    'city': geo.city or response_data.get('city'),
                    'town': geo.town or response_data.get('town'),
                    'country': geo.country or response_data.get('country'),
                    'state': geo.province,  # Using province as state
                    'postal_code': geo.postal_code,
                    'latitude': geo.latitude,
                    'longitude': geo.longitude,
                    'timezone': None  # GeoLocation model doesn't have timezone field
                })
            
            # Add to appropriate survey type group
            result[survey_type].append(response_data)
        
        # Apply geocoding to responses with zero coordinates
        logger.info("Applying geocoding to responses with zero coordinates...")
        for survey_type in result:
            if result[survey_type]:
                result[survey_type] = geocode_survey_response_locations(result[survey_type])
        
        # If survey type filter is applied, return only that type
        if survey_type_filter:
            logger.info(f"Found {len(result[survey_type_filter])} {survey_type_filter} survey responses")
            return jsonify(result[survey_type_filter]), 200
        
        # Return all grouped by survey type
        total_responses = sum(len(responses) for responses in result.values())
        logger.info(f"Found {total_responses} total survey responses: Church({len(result['church'])}), Institution({len(result['institution'])}), Non-Formal Organizations({len(result['nonFormal'])}), Other({len(result['other'])})")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error fetching admin survey responses with geo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch survey responses: {str(e)}'}), 500

@app.route('/api/survey-responses/admin', methods=['GET', 'OPTIONS'])
def get_admin_survey_responses():
    """Get all survey responses for admin reports - automatically determines survey type from user's organization type"""
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response
    
    logger.info("Admin survey responses endpoint called")
    try:
        # Get optional survey type filter from query parameters
        survey_type_filter = request.args.get('survey_type')
        
        # Query all survey responses with user and organization information
        logger.info("Querying survey responses with organization data")
        responses = db.session.query(SurveyResponse)\
            .join(User, SurveyResponse.user_id == User.id)\
            .outerjoin(Organization, User.organization_id == Organization.id)\
            .outerjoin(OrganizationType, Organization.type == OrganizationType.id)\
            .all()
        
        logger.info(f"Found {len(responses)} total survey responses to process")
        
        result = {
            'church': [],
            'institution': [],
            'nonFormal': [],
            'other': []
        }
        
        for response in responses:
            # Determine survey type based on user's organization type
            survey_type = 'other'  # Default
            org_type_name = None
            
            if response.user and response.user.organization and response.user.organization.organization_type:
                org_type_name = response.user.organization.organization_type.type
                logger.debug(f"Processing organization type: '{org_type_name}'")
                # Normalize organization type name for comparison
                org_type_normalized = org_type_name.lower().strip()
                
                if org_type_normalized == 'church':
                    survey_type = 'church'
                elif org_type_normalized == 'institution':
                    survey_type = 'institution'
                elif org_type_normalized in ['non_formal_organizations', 'non-formal', 'non_formal']:
                    survey_type = 'nonFormal'
                else:
                    logger.warning(f"Unknown organization type: '{org_type_name}' (normalized: '{org_type_normalized}') - assigning to 'other'")
            
            # Skip if survey type filter is applied and doesn't match
            if survey_type_filter and survey_type != survey_type_filter:
                continue
            
            # Build response data
            response_data = {
                'id': response.id,
                'survey_type': survey_type,
                'response_date': response.created_at.isoformat() if response.created_at else None,
                'template_id': response.template_id,
                'user_id': response.user_id,
                'status': response.status,
                'answers': response.answers
            }
            
            # Extract user and organization information
            if response.user:
                user = response.user
                response_data.update({
                    'user_name': f"{user.firstname or ''} {user.lastname or ''}".strip(),
                    'user_email': user.email,
                })
                
                # Get organization information
                if user.organization:
                    org = user.organization
                    response_data.update({
                        'organization_id': org.id,
                        'organization_name': org.name,
                        'organization_type_id': org.type,
                        'organization_type_name': org_type_name
                    })
                
                # Extract user details if available
                user_details_list = user.user_details
                if user_details_list and len(user_details_list) > 0:
                    user_details = user_details_list[0]
                    form_data = user_details.form_data or {}
                    
                    # Add common fields
                    response_data.update({
                        'city': form_data.get('city'),
                        'country': form_data.get('country'),
                        'physical_address': form_data.get('address'),
                        'town': form_data.get('town'),
                        'age_group': form_data.get('age_group'),
                        'education_level': form_data.get('education_level'),
                    })
                    
                    # Add survey-type specific fields
                    if survey_type == 'church':
                        response_data.update({
                            'church_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'pastor_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
                    elif survey_type == 'institution':
                        response_data.update({
                            'institution_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'president_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
                    elif survey_type == 'nonFormal':
                        response_data.update({
                            'ministry_name': form_data.get('organization_name') or response_data.get('organization_name'),
                            'leader_name': f"{form_data.get('first_name', '')} {form_data.get('last_name', '')}".strip() or response_data.get('user_name'),
                        })
            
            # Log geographic data for debugging
            if 'latitude' in response_data and 'longitude' in response_data:
                logger.info(f"Response {response.id} - Survey Type: {survey_type}, Lat: {response_data['latitude']}, Lng: {response_data['longitude']}")
            
            # Add to appropriate survey type group
            result[survey_type].append(response_data)
        
        # Apply geocoding to responses with zero coordinates
        logger.info("Applying geocoding to responses with zero coordinates...")
        for survey_type in result:
            if result[survey_type]:
                result[survey_type] = geocode_survey_response_locations(result[survey_type])
        
        # If survey type filter is applied, return only that type
        if survey_type_filter:
            logger.info(f"Found {len(result[survey_type_filter])} {survey_type_filter} survey responses")
            return jsonify(result[survey_type_filter]), 200
        
        # Return all grouped by survey type
        total_responses = sum(len(responses) for responses in result.values())
        logger.info(f"Found {total_responses} total survey responses: Church({len(result['church'])}), Institution({len(result['institution'])}), Non-Formal Organizations({len(result['nonFormal'])}), Other({len(result['other'])})")
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error fetching admin survey responses with geo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch survey responses: {str(e)}'}), 500

@app.route('/api/geocode/batch-update', methods=['POST', 'OPTIONS'])
def batch_update_coordinates():
    """Batch update coordinates for GeoLocation records with zero lat/lng"""
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        # Get optional limit parameter
        data = request.get_json() or {}
        limit = data.get('limit', 50)  # Default to 50 records to avoid overwhelming the geocoding service
        
        logger.info(f"Starting batch geocoding update for up to {limit} records")
        
        # Find GeoLocation records with zero coordinates
        geo_locations = db.session.query(GeoLocation)\
            .filter(
                (GeoLocation.latitude == 0) | (GeoLocation.latitude == None),
                (GeoLocation.longitude == 0) | (GeoLocation.longitude == None)
            )\
            .limit(limit)\
            .all()
        
        logger.info(f"Found {len(geo_locations)} GeoLocation records with zero coordinates")
        
        updated_count = 0
        failed_count = 0
        results = []
        
        for geo_location in geo_locations:
            try:
                success = update_geo_location_coordinates(geo_location.id)
                if success:
                    updated_count += 1
                    results.append({
                        'id': geo_location.id,
                        'status': 'updated',
                        'address': f"{geo_location.address_line1 or ''}, {geo_location.city or ''}, {geo_location.country or ''}".strip(', ')
                    })
                else:
                    failed_count += 1
                    results.append({
                        'id': geo_location.id,
                        'status': 'failed',
                        'address': f"{geo_location.address_line1 or ''}, {geo_location.city or ''}, {geo_location.country or ''}".strip(', ')
                    })
                
                # Add a small delay to be respectful to the geocoding service
                time_module.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error updating GeoLocation {geo_location.id}: {str(e)}")
                failed_count += 1
                results.append({
                    'id': geo_location.id,
                    'status': 'error',
                    'error': str(e),
                    'address': f"{geo_location.address_line1 or ''}, {geo_location.city or ''}, {geo_location.country or ''}".strip(', ')
                })
        
        logger.info(f"Batch geocoding completed: {updated_count} updated, {failed_count} failed")
        
        return jsonify({
            'success': True,
            'message': f'Batch geocoding completed',
            'summary': {
                'total_processed': len(geo_locations),
                'updated': updated_count,
                'failed': failed_count
            },
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error in batch geocoding update: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to perform batch geocoding: {str(e)}'}), 500

def geocode_address_google(address):
    """Geocode an address using Google Maps API from environment variable"""
    if not address or not address.strip():
        return None
        
    try:
        api_key = os.getenv('REACT_APP_GOOGLE_MAPS_API_KEY')
        if not api_key:
            logger.error("❌ REACT_APP_GOOGLE_MAPS_API_KEY not found in environment variables")
            return None
            
        logger.info(f"🔍 Geocoding address: {address}")
        
        params = {
            'address': address.strip(),
            'key': api_key
        }
        
        response = requests.get(
            'https://maps.googleapis.com/maps/api/geocode/json', 
            params=params, 
            timeout=10
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data['status'] == 'OK' and data['results']:
            result = data['results'][0]
            location = result['geometry']['location']
            
            geocoded_data = {
                'latitude': location['lat'],
                'longitude': location['lng'],
                'formatted_address': result['formatted_address'],
                'success': True
            }
            
            logger.info(f"✅ Successfully geocoded: {geocoded_data['formatted_address']} -> {location['lat']}, {location['lng']}")
            return geocoded_data
            
        else:
            logger.warning(f"⚠️ Geocoding failed for '{address}': {data['status']}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error geocoding '{address}': {str(e)}")
        return None

def build_address_string(city=None, state=None, country=None, address=None, town=None):
    """Build a complete address string from components for geocoding"""
    address_parts = []
    
    if address and address.strip():
        address_parts.append(address.strip())
    if town and town.strip():
        address_parts.append(town.strip())
    if city and city.strip():
        address_parts.append(city.strip())
    if state and state.strip():
        address_parts.append(state.strip())
    if country and country.strip():
        address_parts.append(country.strip())
        
    return ', '.join(address_parts)

@app.route('/api/geocode', methods=['POST'])
def geocode_endpoint():
    """Geocode an address to get latitude/longitude coordinates"""
    try:
        data = request.get_json()
        address = data.get('address', '').strip()
        city = data.get('city', '').strip()
        state = data.get('state', '').strip()
        country = data.get('country', '').strip()
        
        # Build full address from components
        full_address = build_address_string(city, state, country, address)
        
        if not full_address:
            return jsonify({'success': False, 'error': 'Address is required'}), 400
        
        result = geocode_address_google(full_address)
        
        if result and result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify({'success': False, 'error': 'Geocoding failed'}), 400
            
    except Exception as e:
        logger.error(f"Error in geocode endpoint: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/survey-questions', methods=['GET'])
def get_survey_questions():
    """Get survey questions structure for analytics"""
    try:
        # Return the structure of survey questions
        # This might come from your SurveyTemplate and Question models
        
        templates = SurveyTemplate.query.all()
        result = {}
        
        for template in templates:
            # Get name and description from the version relationship
            template_name = template.version.name if template.version else f"Template {template.id}"
            template_description = template.version.description if template.version else "No description available"
            
            template_data = {
                'id': template.id,
                'name': template_name,
                'description': template_description,
                'questions': []
            }
            
            # Add questions from the template (questions is a JSON field)
            if template.questions:
                # template.questions is a JSON field, so it's already a list/dict
                if isinstance(template.questions, list):
                    for i, question in enumerate(template.questions):
                        question_data = {
                            'id': i,  # Use index as ID since questions are stored as JSON
                            'text': question.get('question_text', question.get('text', '')),
                            'type': question.get('question_type', question.get('type', 'text')),
                            'required': question.get('required', False)
                        }
                        if 'options' in question:
                            question_data['options'] = question['options']
                        template_data['questions'].append(question_data)
            
            # Categorize by survey type (you'll need to implement this logic)
            survey_type = 'general'  # Default
            if 'church' in template_name.lower():
                survey_type = 'church_survey'
            elif 'institution' in template_name.lower():
                survey_type = 'institution_survey'
            elif 'non-formal' in template_name.lower():
                survey_type = 'non_formal_survey'
            
            result[survey_type] = template_data
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error fetching survey questions: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch survey questions: {str(e)}'}), 500

@app.route('/api/survey-questions/with-types', methods=['GET', 'OPTIONS'])
def get_survey_questions_with_types():
    """Get survey questions with their question types for Custom Chart Builder"""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = make_response('', 200)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    try:
        survey_type = request.args.get('survey_type', None)
        template_id = request.args.get('template_id', None)
        
        logger.info(f"Fetching questions with types - survey_type: {survey_type}, template_id: {template_id}")
        
        # Build query for templates using proper joins through the relationships:
        # SurveyTemplate -> SurveyTemplateVersion -> Organization -> OrganizationType
        query = db.session.query(SurveyTemplate, OrganizationType)\
            .join(SurveyTemplateVersion, SurveyTemplate.version_id == SurveyTemplateVersion.id)\
            .join(Organization, SurveyTemplateVersion.organization_id == Organization.id)\
            .join(OrganizationType, Organization.type == OrganizationType.id)
        
        if template_id:
            query = query.filter(SurveyTemplate.id == template_id)
        elif survey_type:
            # Filter by organization type
            # Normalize the survey_type parameter to match organization_types.type values
            type_mapping = {
                'church': 'church',
                'institution': 'institution', 
                'nonFormal': 'non_formal_organizations',
                'non_formal': 'non_formal_organizations'
            }
            org_type_filter = type_mapping.get(survey_type.lower(), survey_type)
            query = query.filter(OrganizationType.type == org_type_filter)
        
        templates_with_types = query.all()
        
        result = []
        
        for template, org_type in templates_with_types:
            # Try to get questions from the Questions table first
            questions_query = Question.query.filter_by(template_id=template.id).order_by(Question.order).all()
            
            template_questions = []
            
            # If questions table is empty, fallback to questions JSON field
            if not questions_query and template.questions:
                try:
                    json_questions = json.loads(template.questions) if isinstance(template.questions, str) else template.questions
                    
                    for idx, q in enumerate(json_questions):
                        # Map question type from JSON to question_type_id
                        question_type_id = q.get('question_type_id') or q.get('type')
                        
                        # Try to get question type, default to short_text (id=1) if not found
                        if isinstance(question_type_id, str):
                            # Map string types to IDs
                            type_mapping = {
                                'short_text': 1, 'single_choice': 2, 'yes_no': 3,
                                'likert5': 4, 'multi_select': 5, 'paragraph': 6,
                                'numeric': 7, 'percentage': 8, 'flexible_input': 9,
                                'year_matrix': 10
                            }
                            question_type_id = type_mapping.get(question_type_id.lower(), 1)
                        
                        question_type = QuestionType.query.get(question_type_id) if question_type_id else None
                        if not question_type:
                            question_type = QuestionType.query.get(1)  # Default to short_text
                        
                        # Determine if question is numeric based on question type
                        is_numeric = False
                        recommended_chart = 'bar'
                        
                        if question_type.id in [4, 7, 8, 10]:  # likert5, numeric, percentage, year_matrix
                            is_numeric = True
                            if question_type.id == 4:
                                recommended_chart = 'diverging_stacked_bar'
                            elif question_type.id == 7:
                                recommended_chart = 'histogram'
                            elif question_type.id == 8:
                                recommended_chart = 'sunburst'
                            elif question_type.id == 10:
                                recommended_chart = 'heatmap'
                        elif question_type.id in [3, 5, 6]:
                            is_numeric = False
                            if question_type.id == 3:
                                recommended_chart = 'pie'
                            elif question_type.id == 5:
                                recommended_chart = 'horizontal_bar'
                            elif question_type.id == 6:
                                recommended_chart = 'word_cloud'
                        elif question_type.id in [1, 2, 9]:
                            if question_type.id == 1:
                                recommended_chart = 'word_cloud'
                            elif question_type.id == 2:
                                recommended_chart = 'bar'
                            elif question_type.id == 9:
                                recommended_chart = 'table'
                        
                        # Use the actual order from the question data, not the loop index
                        actual_order = q.get('order', idx)
                        
                        question_data = {
                            'id': f"{template.id}_q_{actual_order}",  # Generate unique ID based on actual order
                            'text': q.get('text') or q.get('question_text') or q.get('question') or 'Untitled Question',
                            'section': q.get('section') or 'General',
                            'order': actual_order,  # Use actual order from question data
                            'is_required': q.get('is_required', False),
                            'question_type_id': question_type.id,
                            'question_type_name': question_type.name,
                            'question_type_display': question_type.display_name,
                            'question_type_category': question_type.category,
                            'is_numeric': is_numeric,
                            'recommended_chart': recommended_chart,
                            'config': q.get('config') or {}
                        }
                        template_questions.append(question_data)
                        
                except Exception as json_error:
                    logger.error(f"Error parsing questions_json for template {template.id}: {str(json_error)}")
            else:
                # Use questions from Questions table
                for question in questions_query:
                    # Get question type details
                    question_type = QuestionType.query.get(question.question_type_id)
                    
                    if not question_type:
                        logger.warning(f"Question {question.id} has invalid question_type_id: {question.question_type_id}")
                        continue
                    
                    # Determine if question is numeric based on question type
                    is_numeric = False
                    recommended_chart = 'bar'
                    
                    # Based on QUESTION_TYPE_REFERENCE.md
                    if question_type.id in [4, 7, 8, 10]:  # likert5, numeric, percentage, year_matrix
                        is_numeric = True
                        if question_type.id == 4:  # likert5
                            recommended_chart = 'diverging_stacked_bar'
                        elif question_type.id == 7:  # numeric
                            recommended_chart = 'histogram'
                        elif question_type.id == 8:  # percentage
                            recommended_chart = 'sunburst'
                        elif question_type.id == 10:  # year_matrix
                            recommended_chart = 'heatmap'
                    elif question_type.id in [3, 5, 6]:  # yes_no, multi_select, paragraph
                        is_numeric = False
                        if question_type.id == 3:  # yes_no
                            recommended_chart = 'pie'
                        elif question_type.id == 5:  # multi_select
                            recommended_chart = 'horizontal_bar'
                        elif question_type.id == 6:  # paragraph
                            recommended_chart = 'word_cloud'
                    elif question_type.id in [1, 2, 9]:  # short_text, single_choice, flexible_input
                        # Conditional - need to check content
                        if question_type.id == 1:  # short_text
                            recommended_chart = 'word_cloud'
                        elif question_type.id == 2:  # single_choice
                            recommended_chart = 'bar'
                        elif question_type.id == 9:  # flexible_input
                            recommended_chart = 'table'
                    
                    question_data = {
                        'id': question.id,
                        'text': question.question_text,
                        'section': question.section,
                        'order': question.order,
                        'is_required': question.is_required,
                        'question_type_id': question.question_type_id,
                        'question_type_name': question_type.name,
                        'question_type_display': question_type.display_name,
                        'question_type_category': question_type.category,
                        'is_numeric': is_numeric,
                        'recommended_chart': recommended_chart,
                        'config': question.config or {}
                    }
                    
                    template_questions.append(question_data)
            
            # Determine survey type from organization type
            survey_type_name = 'general'
            if org_type and org_type.type:
                # Map organization_types.type to frontend survey type names
                type_to_survey_type = {
                    'church': 'church',
                    'institution': 'institution',
                    'non_formal_organizations': 'nonFormal'
                }
                survey_type_name = type_to_survey_type.get(org_type.type.lower(), 'general')
            
            template_data = {
                'template_id': template.id,
                'template_name': template.survey_code or f"Template {template.id}",
                'survey_type': survey_type_name,
                'organization_type': org_type.type if org_type else None,
                'questions': template_questions,
                'total_questions': len(template_questions)
            }
            
            result.append(template_data)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error fetching questions with types: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch questions with types: {str(e)}'}), 500


# User-specific survey response endpoints
@app.route('/api/survey-responses/user/<int:user_id>', methods=['GET'])
def get_user_survey_responses(user_id):
    """Get all survey responses for a specific user"""
    try:
        logger.info(f"Fetching survey responses for user_id: {user_id}")
        
        # First, get user info for location data
        user = db.session.query(User).filter_by(id=user_id).first()
        if not user:
            logger.warning(f"User not found: {user_id}")
            return jsonify({'error': 'User not found'}), 404
        
        logger.info(f"Found user: {user.email}")
        
        # Log user's geographic information
        if user.geo_location_id:
            geo_location = GeoLocation.query.get(user.geo_location_id)
            if geo_location:
                logger.info(f"User {user_id} geographic data: lat={geo_location.latitude}, lng={geo_location.longitude}, city={geo_location.city}, country={geo_location.country}")
            else:
                logger.info(f"User {user_id} has geo_location_id {user.geo_location_id} but no geo location found")
        else:
            logger.info(f"User {user_id} has no geo_location_id")
        
        # Get all survey responses directly from survey_responses table for this user
        survey_responses = db.session.query(SurveyResponse)\
            .filter(SurveyResponse.user_id == user_id)\
            .all()
        
        logger.info(f"Found {len(survey_responses)} survey responses")
        
        responses = []
        for survey_response in survey_responses:
            # Get the template info directly
            template = db.session.query(SurveyTemplate).filter_by(
                id=survey_response.template_id
            ).first()
            
            # Determine survey type from template survey_code since survey_type field doesn't exist
            survey_type = 'general'
            if template and template.survey_code:
                code_lower = template.survey_code.lower()
                if 'church' in code_lower:
                    survey_type = 'church'
                elif 'institution' in code_lower:
                    survey_type = 'institution'
                elif 'non-formal' in code_lower or 'nonformal' in code_lower:
                    survey_type = 'nonFormal'
                else:
                    # Default classification based on template ID or other logic
                    survey_type = 'church'  # Default to church for now
            
            # Get user location data from geo_locations table
            geo_location = db.session.query(GeoLocation).filter_by(
                user_id=user_id, which='user'
            ).first()
            
            # Log geo location data for this response
            if geo_location:
                logger.info(f"Response {survey_response.id} geo data: lat={geo_location.latitude}, lng={geo_location.longitude}, city={geo_location.city}, country={geo_location.country}")
            else:
                logger.info(f"No geo location data found for response {survey_response.id}")
            
            response_data = {
                'id': survey_response.id,
                'template_id': survey_response.template_id,
                'template_name': template.survey_code if template else 'Unknown Survey',
                'survey_type': survey_type,
                'responses': survey_response.answers,  # Use 'answers' field from SurveyResponse model
                'submitted_at': survey_response.updated_at.isoformat() if survey_response.updated_at else None,
                'created_at': survey_response.created_at.isoformat() if survey_response.created_at else None,
                'city': geo_location.city if geo_location else None,
                'country': geo_location.country if geo_location else None,
                'latitude': geo_location.latitude if geo_location else None,
                'longitude': geo_location.longitude if geo_location else None,
                'education_level': None,  # Not available in current schema
                'age_group': None  # Not available in current schema
            }
            responses.append(response_data)
            logger.info(f"Added response {survey_response.id} with type {survey_type}, lat={response_data['latitude']}, lng={response_data['longitude']}")
        
        # Apply geocoding to responses with zero coordinates
        logger.info("Applying geocoding to user responses with zero coordinates...")
        responses = geocode_survey_response_locations(responses)
        
        logger.info(f"Returning {len(responses)} responses")
        return jsonify({'responses': responses}), 200
        
    except Exception as e:
        logger.error(f"Error fetching user survey responses: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to fetch user survey responses: {str(e)}'}), 500


@app.route('/api/survey-responses/similar', methods=['POST'])
def get_similar_survey_comparison():
    """Get comparison data for similar surveys"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        response_id = data.get('response_id')
        survey_type = data.get('survey_type')
        selected_surveys = data.get('selected_surveys', [])
        
        logger.info(f"Generating similar survey comparison for user_id: {user_id}, response_id: {response_id}, survey_type: {survey_type}")
        
        # Get the target response
        target_response = db.session.query(SurveyResponse).filter_by(id=response_id).first()
        if not target_response:
            return jsonify({'error': 'Target response not found'}), 404
        
        # Get the target template directly
        target_template = db.session.query(SurveyTemplate).filter_by(
            id=target_response.template_id
        ).first()
        
        # Find similar surveys based on survey type
        query = db.session.query(SurveyResponse).join(SurveyTemplate)
        
        # Filter by survey type using survey_code since survey_type field doesn't exist
        if survey_type == 'church':
            query = query.filter(SurveyTemplate.survey_code.like('%church%'))
        elif survey_type == 'institution':
            query = query.filter(SurveyTemplate.survey_code.like('%institution%'))
        elif survey_type == 'nonFormal':
            query = query.filter(or_(
                SurveyTemplate.survey_code.like('%non-formal%'),
                SurveyTemplate.survey_code.like('%nonformal%')
            ))
        
        # If specific surveys are selected, filter by those
        if selected_surveys:
            query = query.filter(SurveyResponse.id.in_(selected_surveys))
        
        similar_responses = query.all()
        logger.info(f"Found {len(similar_responses)} similar responses for comparison")
        
        # Calculate comparison statistics
        target_scores = {}
        all_scores = {}
        
        if target_response.answers:
            # Extract scores from target response
            for question_id, answer in target_response.answers.items():
                if isinstance(answer, (int, float)) and 1 <= answer <= 5:
                    target_scores[question_id] = answer
        
        # Extract scores from similar responses
        for response in similar_responses:
            if response.answers:
                for question_id, answer in response.answers.items():
                    if isinstance(answer, (int, float)) and 1 <= answer <= 5:
                        if question_id not in all_scores:
                            all_scores[question_id] = []
                        all_scores[question_id].append(answer)
        
        # Calculate averages
        averages = {}
        for question_id, scores in all_scores.items():
            if scores:
                averages[question_id] = sum(scores) / len(scores)
        
        # Calculate comparison stats
        stats = {
            'total_comparisons': len(similar_responses),
            'questions_compared': len(target_scores),
            'average_difference': 0,
            'higher_than_average': 0,
            'lower_than_average': 0
        }
        
        if target_scores and averages:
            differences = []
            for question_id in target_scores:
                if question_id in averages:
                    diff = target_scores[question_id] - averages[question_id]
                    differences.append(diff)
                    if diff > 0:
                        stats['higher_than_average'] += 1
                    elif diff < 0:
                        stats['lower_than_average'] += 1
            
            if differences:
                stats['average_difference'] = sum(differences) / len(differences)
        
        # Get target user info from geo_locations table
        target_user = db.session.query(User).filter_by(id=user_id).first()
        target_geo = db.session.query(GeoLocation).filter_by(
            user_id=user_id, which='user'
        ).first()
        
        # Log target user's geographic information
        if target_user:
            if target_user.geo_location_id:
                user_geo = GeoLocation.query.get(target_user.geo_location_id)
                if user_geo:
                    logger.info(f"Target user {user_id} geographic data: lat={user_geo.latitude}, lng={user_geo.longitude}, city={user_geo.city}, country={user_geo.country}")
                else:
                    logger.info(f"Target user {user_id} has geo_location_id {target_user.geo_location_id} but no geo location found")
            else:
                logger.info(f"Target user {user_id} has no geo_location_id")
        
        # Log target geo information
        if target_geo:
            logger.info(f"Target response geo data: lat={target_geo.latitude}, lng={target_geo.longitude}, city={target_geo.city}, country={target_geo.country}")
        else:
            logger.info(f"No geo location data found for target response")
        
        target_info = {
            'id': target_response.id,
            'city': target_geo.city if target_geo else None,
            'country': target_geo.country if target_geo else None,
            'latitude': target_geo.latitude if target_geo else None,
            'longitude': target_geo.longitude if target_geo else None,
            'template_name': target_template.survey_code if target_template else 'Unknown'
        }
        
        logger.info(f"Target info: {target_info}")
        
        return jsonify({
            'target': target_info,
            'targetScores': target_scores,
            'averages': averages,
            'stats': stats,
            'comparison_count': len(similar_responses)
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating similar survey comparison: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to generate comparison: {str(e)}'}), 500


@app.route('/api/survey-responses/template-info', methods=['GET', 'OPTIONS'])
def get_template_info():
    """
    Diagnostic endpoint to show which templates are being used by surveys.
    Helps debug why surveys aren't matching.
    """
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response
    
    try:
        organization_type = request.args.get('organization_type', 'institution')
        
        # Map frontend org type to database org type
        org_type_map = {
            'church': 'church',
            'institution': 'Institution',
            'nonFormal': 'Non_formal_organizations'
        }
        db_org_type = org_type_map.get(organization_type, 'Institution')
        
        # Get all survey responses with template info
        responses = db.session.query(SurveyResponse)\
            .join(SurveyTemplate, SurveyResponse.template_id == SurveyTemplate.id)\
            .join(User, SurveyResponse.user_id == User.id)\
            .outerjoin(Organization, User.organization_id == Organization.id)\
            .outerjoin(OrganizationType, Organization.type == OrganizationType.id)\
            .filter(SurveyResponse.status == 'completed')\
            .filter(OrganizationType.type == db_org_type)\
            .all()
        
        # Group by template
        template_groups = {}
        for resp in responses:
            template_id = resp.template_id
            template = resp.template
            
            if template_id not in template_groups:
                template_groups[template_id] = {
                    'template_id': template_id,
                    'template_code': template.survey_code if template else 'Unknown',
                    'survey_responses': []
                }
            
            template_groups[template_id]['survey_responses'].append({
                'response_id': resp.id,
                'user_id': resp.user_id,
                'organization_name': resp.user.organization.name if resp.user and resp.user.organization else None,
                'created_at': resp.created_at.isoformat() if resp.created_at else None
            })
        
        # Convert to list and add counts
        result = []
        for template_id, group in template_groups.items():
            group['response_count'] = len(group['survey_responses'])
            result.append(group)
        
        # Sort by response count (descending)
        result.sort(key=lambda x: x['response_count'], reverse=True)
        
        return jsonify({
            'organization_type': organization_type,
            'total_responses': len(responses),
            'template_groups': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting template info: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/survey-responses/compare-by-template/debug/<int:response_id>', methods=['GET', 'OPTIONS'])
def debug_template_questions(response_id):
    """Debug endpoint to check template question structure"""
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response
    
    try:
        # Get the response and template
        target_response = db.session.query(SurveyResponse)\
            .join(SurveyTemplate, SurveyResponse.template_id == SurveyTemplate.id)\
            .filter(SurveyResponse.id == response_id)\
            .first()
        
        if not target_response:
            return jsonify({'error': 'Response not found'}), 404
        
        target_template = target_response.template
        if not target_template:
            return jsonify({'error': 'Template not found'}), 404
        
        # Parse questions
        target_questions = target_template.questions
        if isinstance(target_questions, str):
            target_questions = json.loads(target_questions)
        
        # Analyze structure
        sample_question = target_questions[0] if target_questions else None
        
        return jsonify({
            'response_id': response_id,
            'template_id': target_template.id,
            'template_code': target_template.survey_code,
            'questions_count': len(target_questions),
            'questions_type': type(target_questions).__name__,
            'sample_question': sample_question,
            'sample_question_keys': list(sample_question.keys()) if sample_question else [],
            'all_questions': target_questions[:3]  # First 3 questions for inspection
        }), 200
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/survey-responses/compare-by-template', methods=['POST', 'OPTIONS'])
def compare_surveys_by_template():
    """
    Compare surveys based on matching questions from survey_templates.
    Only compares surveys that share the same template (same questions).
    Filters by organization type (church, institution, non-formal).
    Includes qualitative text analysis using text_analytics module.
    """
    # Handle CORS preflight request
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response
    
    try:
        data = request.get_json()
        target_response_id = data.get('target_response_id')
        organization_type = data.get('organization_type')  # 'church', 'institution', 'nonFormal'
        include_text_analysis = data.get('include_text_analysis', True)
        
        if not target_response_id:
            return jsonify({'error': 'target_response_id is required'}), 400
        
        logger.info(f"Comparing surveys by template for response {target_response_id}, org type: {organization_type}, include_text_analysis: {include_text_analysis}")
        
        # Get the target response with its template
        target_response = db.session.query(SurveyResponse)\
            .join(SurveyTemplate, SurveyResponse.template_id == SurveyTemplate.id)\
            .join(User, SurveyResponse.user_id == User.id)\
            .outerjoin(Organization, User.organization_id == Organization.id)\
            .outerjoin(OrganizationType, Organization.type == OrganizationType.id)\
            .filter(SurveyResponse.id == target_response_id)\
            .first()
        
        if not target_response:
            return jsonify({'error': 'Target response not found'}), 404
        
        target_template = target_response.template
        if not target_template:
            return jsonify({'error': 'Target response has no template'}), 404
        
        logger.info(f"Target response uses template: {target_template.survey_code} (ID: {target_template.id})")
        
        # Parse target template questions
        target_questions = target_template.questions
        if isinstance(target_questions, str):
            target_questions = json.loads(target_questions)
        
        # Handle empty or null questions
        if not target_questions:
            target_questions = []
        
        logger.info(f"Target template has {len(target_questions)} questions")
        
        # If template has no questions, return early with helpful error
        if len(target_questions) == 0:
            logger.warning(f"Template {target_template.survey_code} (ID: {target_template.id}) has no questions defined")
            return jsonify({
                'error': 'empty_template',
                'message': f'This survey template ({target_template.survey_code}) has no questions defined. Please contact an administrator to fix this template.',
                'target': {
                    'id': target_response.id,
                    'template_id': target_template.id,
                    'template_code': target_template.survey_code,
                    'template_questions_count': 0
                },
                'targetScores': {},
                'averages': {},
                'stats': {
                    'total_comparisons': 0,
                    'questions_compared': 0,
                    'questions_with_data': 0,
                    'higher_than_average': 0,
                    'lower_than_average': 0,
                    'average_difference': 0,
                    'section_summary': 'No questions available'
                },
                'question_labels': {},
                'question_details': {},
                'question_meta': {}
            }), 200
        
        # DEBUG: Log the structure of questions
        if target_questions:
            sample_q = target_questions[0]
            logger.info(f"Sample question keys: {list(sample_q.keys())}")
            logger.info(f"Sample question: {json.dumps(sample_q, indent=2)}")
        
        # Get all templates and find those with matching questions
        all_templates = db.session.query(SurveyTemplate).all()
        
        # Build a map of template_id -> set of question identifiers
        template_question_map = {}
        
        # Add target template
        # Match based on question_text and question_type_id only (exclude question ID which is template-specific)
        target_q_ids = set()
        for q in target_questions:
            # Create identifier without question ID for cross-template matching
            q_id = str(q.get('question_text', '')) + '|' + str(q.get('question_type_id', ''))
            target_q_ids.add(q_id)
        
        template_question_map[target_template.id] = {
            'template': target_template,
            'question_ids': target_q_ids,
            'matching_count': len(target_q_ids)
        }
        
        # Process all other templates
        for template in all_templates:
            if template.id == target_template.id:
                continue
            
            # Parse template questions
            template_questions = template.questions
            if isinstance(template_questions, str):
                template_questions = json.loads(template_questions)
            
            # Extract question identifiers (match by text and type only)
            template_q_ids = set()
            for q in template_questions:
                # Create identifier without question ID for cross-template matching
                q_id = str(q.get('question_text', '')) + '|' + str(q.get('question_type_id', ''))
                template_q_ids.add(q_id)
            
            # Find matching questions (intersection)
            matching_questions = target_q_ids & template_q_ids
            
            # Only include templates that have at least some matching questions
            if matching_questions:
                template_question_map[template.id] = {
                    'template': template,
                    'question_ids': template_q_ids,
                    'matching_count': len(matching_questions)
                }
                logger.info(f"Template {template.survey_code} (ID: {template.id}) has {len(matching_questions)} matching questions out of {len(target_q_ids)}")
            else:
                logger.debug(f"Template {template.survey_code} (ID: {template.id}) has no matching questions")
        
        # Get all template IDs that have matching questions
        matching_template_ids = list(template_question_map.keys())
        
        logger.info(f"Found {len(matching_template_ids)} templates with matching questions: {matching_template_ids}")
        
        # Get all responses with matching templates
        query = db.session.query(SurveyResponse)\
            .join(User, SurveyResponse.user_id == User.id)\
            .outerjoin(Organization, User.organization_id == Organization.id)\
            .outerjoin(OrganizationType, Organization.type == OrganizationType.id)\
            .filter(SurveyResponse.template_id.in_(matching_template_ids))\
            .filter(SurveyResponse.id != target_response_id)\
            .filter(SurveyResponse.status == 'completed')
        
        # Filter by organization type if specified
        if organization_type:
            org_type_map = {
                'church': 'church',
                'institution': 'Institution',
                'nonFormal': 'Non_formal_organizations'
            }
            db_org_type = org_type_map.get(organization_type)
            if db_org_type:
                query = query.filter(OrganizationType.type == db_org_type)
                logger.info(f"Filtering by organization type: {db_org_type}")
        
        similar_responses = query.all()
        logger.info(f"Found {len(similar_responses)} similar responses with matching questions")
        
        # Parse target response answers
        target_answers = target_response.answers
        if isinstance(target_answers, str):
            target_answers = json.loads(target_answers)
        
        # Get template questions to know which fields to compare
        template_questions = target_template.questions
        if isinstance(template_questions, str):
            template_questions = json.loads(template_questions)
        
        logger.info(f"Template has {len(template_questions)} questions")
        
        # Build a set of question IDs that we should compare (only matching questions)
        # We need to map question identifiers back to question IDs
        comparable_question_ids = set()
        for q in target_questions:
            comparable_question_ids.add(str(q.get('id', '')))
        
        logger.info(f"Will compare {len(comparable_question_ids)} questions: {comparable_question_ids}")
        
        # Build question meta: detect numeric questions using transformer-based classification
        from text_analytics import classify_question_type
        
        question_meta = {}
        for q in target_questions:
            qid = str(q.get('id', ''))
            if not qid:
                continue
            
            qtext = q.get('question_text', '')
            if not qtext:
                question_meta[qid] = {'is_numeric': False, 'confidence': 1.0, 'reasoning': 'No question text', 'method': 'skip'}
                continue
            
            # Prepare metadata for classifier
            metadata = {
                'question_type': q.get('question_type', ''),
                'question_type_id': q.get('question_type_id', ''),
                'input_type': q.get('input_type', ''),
                'answer_type': q.get('answer_type', ''),
                'options': q.get('options') or q.get('choices') or []
            }
            
            # Use transformer-based classification (falls back to heuristics if transformer unavailable)
            classification = classify_question_type(qtext, metadata)
            question_meta[qid] = classification
            
            logger.info(f"Question {qid} ({qtext[:50]}...): {classification['method']} -> is_numeric={classification['is_numeric']} (confidence={classification['confidence']:.2%}, reason={classification['reasoning']})")
        
        # Extract numeric scores from target response (only for comparable questions and numeric questions)
        target_scores = {}
        for question_id, answer in target_answers.items():
            # Only process questions that are in the comparable set
            if str(question_id) not in comparable_question_ids:
                continue
            # Only process questions deemed numeric by template heuristics
            if not question_meta.get(str(question_id), {}).get('is_numeric', False):
                continue
            # Try to convert to numeric
            numeric_value = None
            if isinstance(answer, (int, float)):
                numeric_value = float(answer)
            elif isinstance(answer, str):
                # Try to parse numeric strings
                try:
                    numeric_value = float(answer)
                except:
                    # Try to extract number from range (e.g., "41-50")
                    import re
                    range_match = re.match(r'(\d+)\s*-\s*(\d+)', answer)
                    if range_match:
                        min_val = float(range_match.group(1))
                        max_val = float(range_match.group(2))
                        numeric_value = (min_val + max_val) / 2
                    else:
                        # Try to extract first number
                        number_match = re.search(r'\d+', answer)
                        if number_match:
                            numeric_value = float(number_match.group())
            
            if numeric_value is not None:
                target_scores[question_id] = numeric_value
        
        logger.info(f"Extracted {len(target_scores)} numeric scores from target response")
        
        # Extract scores from similar responses
        all_scores = {}
        for response in similar_responses:
            response_answers = response.answers
            if isinstance(response_answers, str):
                response_answers = json.loads(response_answers)
            
            for question_id, answer in response_answers.items():
                # Only process questions that are in the comparable set
                if str(question_id) not in comparable_question_ids:
                    continue
                # Only process numeric questions per template metadata
                if not question_meta.get(str(question_id), {}).get('is_numeric', False):
                    continue
                
                # Try to convert to numeric
                numeric_value = None
                if isinstance(answer, (int, float)):
                    numeric_value = float(answer)
                elif isinstance(answer, str):
                    try:
                        numeric_value = float(answer)
                    except:
                        import re
                        range_match = re.match(r'(\d+)\s*-\s*(\d+)', answer)
                        if range_match:
                            min_val = float(range_match.group(1))
                            max_val = float(range_match.group(2))
                            numeric_value = (min_val + max_val) / 2
                        else:
                            number_match = re.search(r'\d+', answer)
                            if number_match:
                                numeric_value = float(number_match.group())
                
                if numeric_value is not None:
                    if question_id not in all_scores:
                        all_scores[question_id] = []
                    all_scores[question_id].append(numeric_value)

        # Post-validate numeric meta: if marked numeric but no numeric values present anywhere, demote to non-numeric
        for qid, meta in list(question_meta.items()):
            if not meta.get('is_numeric', False):
                continue
            if qid not in target_scores and qid not in all_scores:
                question_meta[qid]['is_numeric'] = False
        
        # Generate question labels using NLP
        from text_analytics import generate_question_label, generate_section_summary
        
        question_labels = {}
        question_details = {}
        for q in target_questions:
            q_id = str(q.get('id', ''))
            q_text = q.get('question_text', '')
            if q_id and q_text:
                question_labels[q_id] = generate_question_label(q_text, max_words=3)
                question_details[q_id] = {
                    'label': question_labels[q_id],
                    'full_text': q_text,
                    'section': q.get('section', 'General')
                }
        
        logger.info(f"Generated labels for {len(question_labels)} questions")
        
        # Generate section summary
        section_summary = generate_section_summary(target_questions)
        logger.info(f"Section summary: {section_summary}")
        
        # Calculate averages for each question
        averages = {}
        for question_id, scores in all_scores.items():
            if scores:
                averages[question_id] = sum(scores) / len(scores)
        
        logger.info(f"Calculated averages for {len(averages)} questions")
        
        # Calculate comparison statistics
        stats = {
            'total_comparisons': len(similar_responses),
            'questions_compared': len(target_scores),
            'questions_with_data': len(averages),
            'higher_than_average': 0,
            'lower_than_average': 0,
            'average_difference': 0,
            'section_summary': section_summary
        }
        
        if target_scores and averages:
            differences = []
            for question_id in target_scores:
                if question_id in averages:
                    diff = target_scores[question_id] - averages[question_id]
                    differences.append(diff)
                    if diff > 0:
                        stats['higher_than_average'] += 1
                    elif diff < 0:
                        stats['lower_than_average'] += 1
            
            if differences:
                stats['average_difference'] = sum(differences) / len(differences)
        
        # Get target response info
        target_info = {
            'id': target_response.id,
            'template_id': target_template.id,
            'template_code': target_template.survey_code,
            'template_questions_count': len(target_questions),
            'user_id': target_response.user_id,
            'user_name': f"{target_response.user.firstname or ''} {target_response.user.lastname or ''}".strip() if target_response.user else None,
            'user_email': target_response.user.email if target_response.user else None,
            'organization_id': target_response.user.organization_id if target_response.user else None,
            'organization_name': target_response.user.organization.name if target_response.user and target_response.user.organization else None,
            'organization_type': target_response.user.organization.organization_type.type if target_response.user and target_response.user.organization and target_response.user.organization.organization_type else None
        }
        
        # Add text analytics if requested
        text_analytics_data = None
        if include_text_analysis:
            try:
                logger.info("Running text analytics for target response and similar responses...")
                
                # Custom text extraction for your data structure
                # Your answers are stored as JSON in survey_responses.answers
                # Questions are stored in survey_templates.questions
                
                def extract_text_responses(response, template):
                    """Extract text responses from a survey response"""
                    text_responses = []
                    
                    # Parse answers
                    answers = response.answers
                    if isinstance(answers, str):
                        answers = json.loads(answers)
                    
                    # Parse template questions
                    questions = template.questions
                    if isinstance(questions, str):
                        questions = json.loads(questions)
                    
                    # Extract text answers (long strings, typically > 50 chars)
                    for key, value in answers.items():
                        if isinstance(value, str) and len(value.strip()) > 20:
                            # Find the question text
                            question_text = None
                            for q in questions:
                                if str(q.get('id')) == str(key) or q.get('name') == key:
                                    question_text = q.get('question') or q.get('label') or q.get('text')
                                    break
                            
                            text_responses.append({
                                'question_key': key,
                                'question_text': question_text,
                                'answer': value.strip()
                            })
                    
                    return text_responses
                
                # Extract text from target response
                target_texts = extract_text_responses(target_response, target_template)
                logger.info(f"Found {len(target_texts)} text responses in target survey")
                
                # Extract text from similar responses
                comparison_texts = []
                for resp in similar_responses:
                    texts = extract_text_responses(resp, target_template)
                    comparison_texts.extend(texts)
                logger.info(f"Found {len(comparison_texts)} text responses in comparison group")
                
                if target_texts or comparison_texts:
                    # Simple sentiment analysis using basic keyword matching
                    def simple_sentiment(text):
                        text_lower = text.lower()
                        positive_words = ['good', 'great', 'excellent', 'yes', 'strong', 'effective', 'successful', 'positive', 'well', 'better', 'best', 'improved', 'growing']
                        negative_words = ['no', 'not', 'poor', 'weak', 'limited', 'lack', 'insufficient', 'problem', 'issue', 'difficult', 'challenge', 'negative', 'worse', 'worst']
                        
                        pos_count = sum(1 for word in positive_words if word in text_lower)
                        neg_count = sum(1 for word in negative_words if word in text_lower)
                        
                        if pos_count > neg_count:
                            return 'positive'
                        elif neg_count > pos_count:
                            return 'negative'
                        else:
                            return 'neutral'
                    
                    # Analyze target responses
                    target_sentiments = {'positive': 0, 'neutral': 0, 'negative': 0}
                    for text_resp in target_texts:
                        sentiment = simple_sentiment(text_resp['answer'])
                        text_resp['sentiment'] = sentiment
                        target_sentiments[sentiment] += 1
                    
                    # Analyze comparison responses
                    comparison_sentiments = {'positive': 0, 'neutral': 0, 'negative': 0}
                    for text_resp in comparison_texts:
                        sentiment = simple_sentiment(text_resp['answer'])
                        text_resp['sentiment'] = sentiment
                        comparison_sentiments[sentiment] += 1
                    
                    text_analytics_data = {
                        'target': {
                            'total_text_responses': len(target_texts),
                            'sentiment_distribution': target_sentiments,
                            'responses': [{
                                'question_id': t['question_key'],
                                'question_text': t['question_text'],
                                'answer': t['answer'],
                                'sentiment': t['sentiment']
                            } for t in target_texts]
                        },
                        'comparison_group': {
                            'total_text_responses': len(comparison_texts),
                            'sentiment_distribution': comparison_sentiments,
                            'average_sentiment': max(comparison_sentiments, key=comparison_sentiments.get) if comparison_texts else None
                        }
                    }
                    
                    logger.info(f"Text analytics completed: {len(target_texts)} target responses, {len(comparison_texts)} comparison responses")
                else:
                    logger.info("No text responses found (all answers are short or numeric)")
                    
            except Exception as e:
                logger.error(f"Error running text analytics: {str(e)}")
                logger.error(traceback.format_exc())
                # Don't fail the whole request if text analytics fails
                text_analytics_data = {'error': str(e)}
        
        result = {
            'target': target_info,
            'targetScores': target_scores,
            'averages': averages,
            'stats': stats,
            'comparison_count': len(similar_responses),
            'template_questions_count': len(template_questions),
            'question_labels': question_labels,
            'question_details': question_details,
            'question_meta': question_meta
        }
        
        if text_analytics_data:
            result['text_analytics'] = text_analytics_data
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error comparing surveys by template: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': f'Failed to compare surveys: {str(e)}'}), 500


# ==================== Contact Referral API ====================

@app.route('/api/contact-referrals', methods=['POST', 'OPTIONS'])
def create_contact_referral():
    """
    Create a new contact referral submission.
    Accepts primary contact and optional referrals.
    """
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        logger.info(f"Received contact referral data: {data}")
        
        # Extract primary contact data
        primary_data = data.get('primary_contact', {})
        referrals_data = data.get('referrals', [])
        
        # Get metadata from request
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        # Create primary contact
        primary_contact = ContactReferral(
            first_name=primary_data.get('firstName', ''),
            last_name=primary_data.get('lastName', ''),
            email=primary_data.get('email', ''),
            full_phone=primary_data.get('fullPhone', ''),
            whatsapp=primary_data.get('whatsapp', ''),
            preferred_contact=primary_data.get('preferredContact', ''),
            type_of_institution=primary_data.get('typeOfInstitution', ''),
            institution_name=primary_data.get('institutionName', ''),
            title=primary_data.get('title', ''),
            physical_address=primary_data.get('physicalAddress', ''),
            country=primary_data.get('country', ''),
            is_primary=True,
            device_info=user_agent,
            ip_address=ip_address
        )
        
        db.session.add(primary_contact)
        db.session.flush()  # Get the primary contact ID
        
        # Create referral contacts
        referral_contacts = []
        for referral_data in referrals_data:
            referral_email = referral_data.get('email', '').strip().lower()
            
            # Check if this email already exists in contact_referrals
            existing_contact = None
            if referral_email:
                existing_contact = ContactReferral.query.filter(
                    db.func.lower(ContactReferral.email) == referral_email
                ).first()
            
            # Determine who should be the referrer
            # If the email exists, the original person who entered it becomes the referrer
            # Otherwise, the current primary contact is the referrer
            referred_by_id = existing_contact.id if existing_contact else primary_contact.id
            
            referral = ContactReferral(
                first_name=referral_data.get('firstName', ''),
                last_name=referral_data.get('lastName', ''),
                email=referral_data.get('email', ''),
                full_phone=referral_data.get('fullPhone', ''),
                whatsapp=referral_data.get('whatsapp', ''),
                preferred_contact=referral_data.get('preferredContact', ''),
                type_of_institution=referral_data.get('typeOfInstitution', ''),
                institution_name=referral_data.get('institutionName', ''),
                title=referral_data.get('title', ''),
                physical_address=referral_data.get('physicalAddress', ''),
                country=referral_data.get('country', ''),
                is_primary=False,
                referred_by_id=referred_by_id,  # Link to original person if duplicate
                device_info=user_agent,
                ip_address=ip_address
            )
            db.session.add(referral)
            referral_contacts.append(referral)
            
            # Log if this is a duplicate referral
            if existing_contact:
                logger.info(f"Duplicate email detected: {referral_email}. Linking to original contact ID: {existing_contact.id}")
        
        db.session.commit()
        
        logger.info(f"Successfully created contact referral. Primary ID: {primary_contact.id}, Referrals: {len(referral_contacts)}")
        
        return jsonify({
            'success': True,
            'message': 'Contact referral submitted successfully',
            'primary_contact_id': primary_contact.id,
            'referral_count': len(referral_contacts)
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating contact referral: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': 'Failed to submit contact referral',
            'details': str(e)
        }), 500


@app.route('/api/contact-referrals', methods=['GET'])
def get_contact_referrals():
    """
    Get all contact referrals (admin endpoint).
    """
    try:
        # Get all primary contacts
        primary_contacts = ContactReferral.query.filter_by(is_primary=True).all()
        
        result = []
        for contact in primary_contacts:
            contact_dict = contact.to_dict()
            # Get referrals for this contact
            referrals = ContactReferral.query.filter_by(referred_by_id=contact.id).all()
            contact_dict['referrals'] = [ref.to_dict() for ref in referrals]
            result.append(contact_dict)
        
        return jsonify({
            'success': True,
            'contacts': result,
            'total': len(result)
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching contact referrals: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch contact referrals'
        }), 500


@app.route('/api/contact-referrals/<int:referral_id>/approve', methods=['POST'])
def approve_contact_referral(referral_id):
    """
    Approve a contact referral and create user/organization if needed.
    
    Request body:
    {
        "create_organization": true/false,
        "organization_id": <existing_org_id> (if create_organization is false),
        "organization_name": "<name>" (if create_organization is true),
        "organization_type_id": <type_id> (if create_organization is true),
        "ui_role": "user/manager/head/etc",
        "template_id": <template_id>,
        "send_welcome_email": true/false
    }
    """
    try:
        data = request.get_json()
        
        # Get the contact referral
        referral = ContactReferral.query.get(referral_id)
        if not referral:
            return jsonify({
                'success': False,
                'error': 'Contact referral not found'
            }), 404
        
        # Check if user already exists with this email
        existing_user = User.query.filter_by(email=referral.email).first()
        if existing_user:
            return jsonify({
                'success': False,
                'error': f'User with email {referral.email} already exists'
            }), 400
        
        organization_id = None
        
        # Handle organization creation or selection
        if data.get('create_organization', False):
            # Create new organization
            org_name = data.get('organization_name') or referral.institution_name
            org_type_id = data.get('organization_type_id')
            
            if not org_name:
                return jsonify({
                    'success': False,
                    'error': 'Organization name is required'
                }), 400
            
            # Check if organization already exists
            existing_org = Organization.query.filter_by(name=org_name).first()
            if existing_org:
                organization_id = existing_org.id
                logger.info(f"Using existing organization: {org_name} (ID: {organization_id})")
            else:
                # Create geo_location if address provided
                geo_location_id = None
                if referral.physical_address or referral.country:
                    geo_location = GeoLocation(
                        country=referral.country,
                        address_line1=referral.physical_address
                    )
                    db.session.add(geo_location)
                    db.session.flush()
                    geo_location_id = geo_location.id
                
                # Create new organization
                new_org = Organization(
                    name=org_name,
                    type=org_type_id,
                    address=geo_location_id
                )
                db.session.add(new_org)
                db.session.flush()
                organization_id = new_org.id
                logger.info(f"Created new organization: {org_name} (ID: {organization_id})")
        else:
            # Use existing organization
            organization_id = data.get('organization_id')
            if not organization_id:
                return jsonify({
                    'success': False,
                    'error': 'Organization ID is required when not creating new organization'
                }), 400
        
        # Generate username from email
        username = referral.email.split('@')[0]
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Generate random password
        import random
        import string
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        # Create user
        new_user = User(
            username=username,
            email=referral.email,
            ui_role=data.get('ui_role', 'user'),
            firstname=referral.first_name,
            lastname=referral.last_name,
            phone=referral.full_phone,
            organization_id=organization_id
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.flush()
        
        # Create survey response if template provided
        template_id = data.get('template_id')
        if template_id:
            survey_response = SurveyResponse(
                user_id=new_user.id,
                template_id=template_id,
                status='pending'
            )
            db.session.add(survey_response)
        
        # Delete the contact referral after successful user creation
        db.session.delete(referral)
        
        # Commit all changes
        db.session.commit()
        
        # Send welcome email if requested
        if data.get('send_welcome_email', False):
            try:
                # TODO: Implement email sending logic here
                logger.info(f"Welcome email would be sent to {new_user.email}")
            except Exception as email_error:
                logger.error(f"Error sending welcome email: {str(email_error)}")
        
        return jsonify({
            'success': True,
            'message': 'Contact referral approved and user created successfully',
            'user': {
                'id': new_user.id,
                'username': new_user.username,
                'email': new_user.email,
                'organization_id': organization_id
            },
            'password': password  # Return password for admin to share with user
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving contact referral: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': f'Failed to approve contact referral: {str(e)}'
        }), 500


@app.route('/api/contact-referrals/<int:referral_id>', methods=['PUT'])
def update_contact_referral(referral_id):
    """
    Update an existing contact referral.
    """
    logger.info(f"=== UPDATE REQUEST RECEIVED for referral_id: {referral_id} ===")
    try:
        data = request.json
        logger.info(f"Update data: {data}")
        
        referral = ContactReferral.query.get(referral_id)
        if not referral:
            return jsonify({
                'success': False,
                'error': 'Contact referral not found'
            }), 404
        
        # Update fields if provided
        if 'firstName' in data:
            referral.first_name = data['firstName']
        if 'lastName' in data:
            referral.last_name = data['lastName']
        if 'email' in data:
            referral.email = data['email'].strip().lower()
        if 'fullPhone' in data:
            referral.full_phone = data['fullPhone']
        if 'whatsapp' in data:
            referral.whatsapp = data['whatsapp']
        if 'preferredContact' in data:
            referral.preferred_contact = data['preferredContact']
        if 'typeOfInstitution' in data:
            referral.type_of_institution = data['typeOfInstitution']
        if 'institutionName' in data:
            referral.institution_name = data['institutionName']
        if 'title' in data:
            referral.title = data['title']
        if 'physicalAddress' in data:
            referral.physical_address = data['physicalAddress']
        if 'country' in data:
            referral.country = data['country']
        
        db.session.commit()
        logger.info(f"Successfully updated referral {referral_id}")
        
        return jsonify({
            'success': True,
            'message': 'Contact referral updated successfully',
            'referral': referral.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating contact referral: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': 'Failed to update contact referral',
            'details': str(e)
        }), 500


@app.route('/api/contact-referrals/<int:referral_id>/reject', methods=['DELETE'])
def reject_contact_referral(referral_id):
    """
    Reject and delete a contact referral.
    If it's a primary contact, also deletes all associated sub-referrals.
    """
    logger.info(f"=== REJECT REQUEST RECEIVED for referral_id: {referral_id} ===")
    try:
        referral = ContactReferral.query.get(referral_id)
        logger.info(f"Referral found: {referral is not None}")
        if not referral:
            return jsonify({
                'success': False,
                'error': 'Contact referral not found'
            }), 404
        
        # Store info for response
        referral_info = {
            'name': f"{referral.first_name} {referral.last_name}",
            'email': referral.email
        }
        
        # If this is a primary contact, delete all sub-referrals first
        sub_referrals_count = 0
        if referral.is_primary:
            sub_referrals = ContactReferral.query.filter_by(
                referred_by_id=referral.id,
                is_primary=False
            ).all()
            
            sub_referrals_count = len(sub_referrals)
            
            # Delete all sub-referrals
            for sub_ref in sub_referrals:
                db.session.delete(sub_ref)
            
            # Flush to ensure sub-referrals are deleted before parent
            db.session.flush()
            
            logger.info(f"Deleted {sub_referrals_count} sub-referrals for contact {referral.id}")
        
        # Delete the primary referral
        logger.info(f"About to delete primary referral {referral.id}")
        db.session.delete(referral)
        logger.info(f"Committing deletion...")
        db.session.commit()
        logger.info(f"Successfully deleted referral {referral.id}")
        
        message = f'Contact referral for {referral_info["name"]} has been rejected and deleted'
        if sub_referrals_count > 0:
            message += f' (including {sub_referrals_count} sub-referral(s))'
        
        return jsonify({
            'success': True,
            'message': message,
            'deleted_referral': referral_info,
            'sub_referrals_deleted': sub_referrals_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting contact referral: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': 'Failed to reject contact referral',
            'details': str(e)
        }), 500


@app.route('/api/contact-referrals/check-email', methods=['POST', 'OPTIONS'])
def check_email_exists():
    """
    Check if an email exists in contact referrals or users table.
    
    Request body:
    {
        "email": "<email>"
    }
    """
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        # Check in contact referrals
        contact_referral = ContactReferral.query.filter(
            db.func.lower(ContactReferral.email) == email
        ).first()
        
        # Check in users table
        user = User.query.filter(
            db.func.lower(User.email) == email
        ).first()
        
        if contact_referral:
            # Get referrer information if this contact was referred
            referrer_info = None
            if contact_referral.referred_by_id:
                referrer = ContactReferral.query.get(contact_referral.referred_by_id)
                if referrer:
                    referrer_info = {
                        'id': referrer.id,
                        'name': f"{referrer.first_name} {referrer.last_name}",
                        'email': referrer.email
                    }
            
            # Get all sub-referrals for this contact
            sub_referrals = ContactReferral.query.filter_by(
                referred_by_id=contact_referral.id,
                is_primary=False
            ).all()
            
            sub_referrals_data = []
            for sub_ref in sub_referrals:
                sub_referrals_data.append({
                    'id': sub_ref.id,
                    'firstName': sub_ref.first_name,
                    'lastName': sub_ref.last_name,
                    'email': sub_ref.email,
                    'fullPhone': sub_ref.full_phone,
                    'whatsapp': sub_ref.whatsapp,
                    'preferredContact': sub_ref.preferred_contact,
                    'typeOfInstitution': sub_ref.type_of_institution,
                    'institutionName': sub_ref.institution_name,
                    'title': sub_ref.title,
                    'physicalAddress': sub_ref.physical_address,
                    'country': sub_ref.country
                })
            
            return jsonify({
                'success': True,
                'exists': True,
                'source': 'contact_referral',
                'original_contact_id': contact_referral.id,
                'referrer': referrer_info,
                'data': {
                    'firstName': contact_referral.first_name,
                    'lastName': contact_referral.last_name,
                    'email': contact_referral.email,
                    'fullPhone': contact_referral.full_phone,
                    'whatsapp': contact_referral.whatsapp,
                    'preferredContact': contact_referral.preferred_contact,
                    'typeOfInstitution': contact_referral.type_of_institution,
                    'institutionName': contact_referral.institution_name,
                    'title': contact_referral.title,
                    'physicalAddress': contact_referral.physical_address,
                    'country': contact_referral.country
                },
                'subReferrals': sub_referrals_data
            }), 200
        elif user:
            return jsonify({
                'success': True,
                'exists': True,
                'source': 'user',
                'data': {
                    'firstName': user.firstname,
                    'lastName': user.lastname,
                    'email': user.email,
                    'fullPhone': user.phone,
                    'institutionName': user.organization.name if user.organization else '',
                    'country': user.geo_location.country if user.geo_location else ''
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'exists': False,
                'data': None
            }), 200
            
    except Exception as e:
        logger.error(f"Error checking email: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': 'Failed to check email'
        }), 500


@app.route('/api/organizations/search', methods=['GET'])
def search_organizations_fuzzy():
    """
    Search organizations with fuzzy matching.
    Returns organizations sorted by match confidence.
    
    Query params:
        q: search query (organization name to match)
        limit: max results (default 10)
    """
    try:
        query = request.args.get('q', '').strip()
        limit = min(int(request.args.get('limit', 10)), 50)
        
        if not query:
            # If no query, return all organizations (limited)
            organizations = Organization.query.limit(limit).all()
            return jsonify({
                'success': True,
                'organizations': [{
                    'id': org.id,
                    'name': org.name,
                    'type_id': org.type,
                    'type_name': org.organization_type.type if org.organization_type else None,
                    'match_score': 0,
                    'match_type': 'none'
                } for org in organizations]
            }), 200
        
        # Get all organizations for matching
        all_orgs = Organization.query.all()
        
        def calculate_similarity(query_str, target_str):
            """
            Calculate similarity score using multiple algorithms.
            Returns a tuple of (score, match_type).
            """
            if not target_str:
                return (0, 'none')
            
            query_lower = query_str.lower().strip()
            target_lower = target_str.lower().strip()
            
            # Exact match
            if query_lower == target_lower:
                return (100, 'exact')
            
            # Contains match
            if query_lower in target_lower or target_lower in query_lower:
                # Calculate how much of the string matches
                shorter = min(len(query_lower), len(target_lower))
                longer = max(len(query_lower), len(target_lower))
                score = int((shorter / longer) * 95)
                return (max(score, 75), 'contains')
            
            # Starts with match
            if target_lower.startswith(query_lower) or query_lower.startswith(target_lower):
                return (90, 'starts_with')
            
            # Token-based matching (word overlap)
            query_tokens = set(query_lower.split())
            target_tokens = set(target_lower.split())
            
            if query_tokens and target_tokens:
                # Calculate Jaccard similarity
                intersection = query_tokens & target_tokens
                union = query_tokens | target_tokens
                jaccard = len(intersection) / len(union)
                
                if jaccard > 0:
                    token_score = int(jaccard * 85)
                    return (max(token_score, 50), 'token_match')
            
            # Levenshtein-like simple similarity
            # Using a simple ratio calculation
            def simple_ratio(s1, s2):
                """Calculate simple similarity ratio"""
                if not s1 or not s2:
                    return 0
                
                # Count matching characters at same positions
                matches = sum(1 for a, b in zip(s1, s2) if a == b)
                max_len = max(len(s1), len(s2))
                return matches / max_len
            
            ratio = simple_ratio(query_lower, target_lower)
            
            # Also try removing common words
            common_words = {'the', 'of', 'and', 'church', 'organization', 'org', 'inc', 'ltd', 'ministry', 'ministries'}
            
            def clean_name(name):
                words = name.lower().split()
                return ' '.join(w for w in words if w not in common_words)
            
            clean_query = clean_name(query_str)
            clean_target = clean_name(target_str)
            
            if clean_query and clean_target:
                clean_ratio = simple_ratio(clean_query, clean_target)
                ratio = max(ratio, clean_ratio)
            
            # Trigram matching
            def get_trigrams(s):
                s = s.lower().strip()
                if len(s) < 3:
                    return set()
                return set(s[i:i+3] for i in range(len(s) - 2))
            
            q_trigrams = get_trigrams(query_str)
            t_trigrams = get_trigrams(target_str)
            
            if q_trigrams and t_trigrams:
                trigram_intersection = len(q_trigrams & t_trigrams)
                trigram_union = len(q_trigrams | t_trigrams)
                trigram_score = (trigram_intersection / trigram_union) if trigram_union > 0 else 0
                ratio = max(ratio, trigram_score)
            
            if ratio > 0.3:
                return (int(ratio * 80), 'fuzzy')
            
            return (0, 'none')
        
        # Calculate scores for all organizations
        scored_orgs = []
        for org in all_orgs:
            score, match_type = calculate_similarity(query, org.name)
            if score > 20:  # Only include organizations with some similarity
                scored_orgs.append({
                    'id': org.id,
                    'name': org.name,
                    'type_id': org.type,
                    'type_name': org.organization_type.type if org.organization_type else None,
                    'match_score': score,
                    'match_type': match_type
                })
        
        # Sort by score descending
        scored_orgs.sort(key=lambda x: x['match_score'], reverse=True)
        
        # Limit results
        results = scored_orgs[:limit]
        
        # Check for exact match
        exact_match = None
        for org in results:
            if org['match_type'] == 'exact':
                exact_match = org
                break
        
        return jsonify({
            'success': True,
            'query': query,
            'exact_match': exact_match,
            'organizations': results,
            'total_matches': len(scored_orgs)
        }), 200
        
    except Exception as e:
        logger.error(f"Error searching organizations: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': 'Failed to search organizations'
        }), 500


@app.route('/api/contact-referrals/check-organization', methods=['POST'])
def check_organization_exists():
    """
    Check if an organization exists by name.
    
    Request body:
    {
        "organization_name": "<name>"
    }
    """
    try:
        data = request.get_json()
        org_name = data.get('organization_name', '').strip()
        
        if not org_name:
            return jsonify({
                'success': False,
                'error': 'Organization name is required'
            }), 400
        
        # Search for organization (case-insensitive)
        organization = Organization.query.filter(
            db.func.lower(Organization.name) == org_name.lower()
        ).first()
        
        if organization:
            return jsonify({
                'success': True,
                'exists': True,
                'organization': {
                    'id': organization.id,
                    'name': organization.name,
                    'type_id': organization.type
                }
            }), 200
        else:
            return jsonify({
                'success': True,
                'exists': False,
                'organization': None
            }), 200
            
    except Exception as e:
        logger.error(f"Error checking organization: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to check organization'
        }), 500



# ==========================================
# Report Storage Logic (Added)
# ==========================================

class SavedReport(db.Model):
    __tablename__ = 'saved_reports'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)  # Made nullable
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(JSON, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('saved_reports', lazy=True))
    organization = db.relationship('Organization', backref=db.backref('saved_reports', lazy=True))

@app.route('/api/init-reports-table', methods=['POST'])
def init_reports_table():
    try:
        db.create_all()
        return jsonify({'message': 'Database tables initialized'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports', methods=['GET'])
def get_user_reports():
    user_id = request.args.get('user_id')
    if not user_id:
        # If no user_id param, try to get from query string or default to 1 for testing
        user_id = request.args.get('user_id', 1)
    
    try:
        reports = SavedReport.query.filter_by(user_id=user_id).order_by(SavedReport.updated_at.desc()).all()
        return jsonify([{
            "id": r.id,
            "title": r.title,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            # Return rudimentary content structure for preview if needed
            "content_preview": "Document" 
        } for r in reports]), 200
    except Exception as e:
        logger.error(f"Error fetching reports: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<int:report_id>', methods=['GET'])
def get_report(report_id):
    try:
        report = SavedReport.query.get_or_404(report_id)
        return jsonify({
            "id": report.id,
            "title": report.title,
            "content": report.content,
            "user_id": report.user_id,
            "organization_id": report.organization_id,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "updated_at": report.updated_at.isoformat() if report.updated_at else None
        }), 200
    except Exception as e:
        logger.error(f"Error fetching report {report_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports', methods=['POST'])
def save_report():
    try:
        data = request.get_json() or {}
        
        user_id = data.get('user_id')
        org_id = data.get('organization_id')
        title = data.get('title')
        content = data.get('content')
        report_id = data.get('id')

        # Basic validation
        if not title:
             return jsonify({'error': 'Title is required'}), 400
        
        # Require user_id
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400
        
        # If org_id not provided or invalid, try to get from user's organization
        if not org_id or org_id == 1:
            user = User.query.get(user_id)
            if user and user.organization_id:
                org_id = user.organization_id
            else:
                org_id = None  # Allow null organization

        if report_id:
            report = SavedReport.query.get(report_id)
            if report:
                report.title = title
                report.content = content
                report.updated_at = datetime.utcnow()
                db.session.commit()
                return jsonify({'id': report.id, 'message': 'Report updated successfully'}), 200
        
        # Create new
        new_report = SavedReport(
            user_id=user_id, 
            organization_id=org_id, 
            title=title, 
            content=content
        )
        db.session.add(new_report)
        db.session.commit()
        
        return jsonify({'id': new_report.id, 'message': 'Report created successfully'}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    try:
        report = SavedReport.query.get_or_404(report_id)
        db.session.delete(report)
        db.session.commit()
        return jsonify({'message': 'Report deleted successfully'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================================================
# RAG (Retrieval-Augmented Generation) Endpoint
# ============================================================================

# Import RAG service
try:
    from rag_service import SurveyRAGService
    rag_service = SurveyRAGService(db)
    logger.info("✅ RAG Service initialized successfully")
except Exception as e:
    logger.error(f"⚠️ Failed to initialize RAG Service: {e}")
    rag_service = None

@app.route('/api/rag/ask', methods=['POST'])
def rag_ask_question():
    """
    RAG endpoint for answering questions about survey data
    Uses Gemini 2.0 Flash Lite with database retrieval and grounding
    
    Request body:
    {
        "question": "What surveys do we have from churches in Kenya?",
        "limit": 10  // optional, default 10
    }
    
    Response:
    {
        "success": true,
        "response": "AI-generated answer",
        "grounding": [
            {
                "type": "survey_response",
                "organization": "Example Church",
                "organization_type": "church",
                "user": "John Doe",
                "location": "Nairobi, Kenya",
                "date": "2026-01-09",
                "status": "completed",
                "survey_code": "ABC123"
            }
        ],
        "metadata": {
            "total_responses": 5,
            "organizations": ["Example Church", ...],
            "countries": ["Kenya"],
            ...
        },
        "query_type": "organization_specific",
        "model": "gemini-2.0-flash-lite"
    }
    """
    try:
        if not rag_service:
            return jsonify({
                'success': False,
                'error': 'RAG service not available',
                'response': 'The RAG service is not properly configured. Please check server logs.'
            }), 503
        
        data = request.get_json() or {}
        question = data.get('question', '').strip()
        limit = data.get('limit', 10)
        
        # Validate input
        if not question:
            return jsonify({
                'success': False,
                'error': 'Question is required',
                'response': 'Please provide a question to answer.'
            }), 400
        
        # Validate limit
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            limit = 10
        
        logger.info(f"📝 RAG Question received: {question}")
        
        # Process question using RAG service
        result = rag_service.answer_question(question, limit=limit)
        
        if result.get('success'):
            logger.info(f"✅ RAG response generated successfully")
            return jsonify(result), 200
        else:
            logger.error(f"❌ RAG processing failed: {result.get('error')}")
            return jsonify(result), 500
            
    except Exception as e:
        logger.error(f"❌ Error in RAG endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'response': 'An error occurred while processing your question. Please try again.'
        }), 500

@app.route('/api/document/parse', methods=['POST'])
def parse_document():
    """Parse uploaded document and return structured questions"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
            
        parser = DocumentParserService()
        
        # 1. Extract Text
        try:
            text = parser.extract_text_from_file(file)
            if not text:
                return jsonify({'error': 'No text extracted from document'}), 400
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
            
        # 2. Parse Questions with LLM
        questions = parser.parse_questions_from_text(text)
        
        return jsonify({
            'success': True,
            'questions': questions,
            'count': len(questions)
        })
        
    except Exception as e:
        logger.error(f"Error parsing document: {str(e)}")
        return jsonify({'error': 'Internal server error processing document'}), 500

if __name__ == '__main__':
    app.run(debug=False)

