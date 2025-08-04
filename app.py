from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy import text
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import joinedload
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

🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

🔐 Your Account Credentials:
• Username: {username}
• Email Address: {to_email}
• Temporary Password: {password}
• Survey Code: {survey_code if survey_code else 'Not assigned'}
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

🎯 What Awaits You:
As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. Every response makes a difference!

📚 Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

💡 Getting the Most Out of Saurara:
- Complete your profile for better survey matching
- Respond to surveys thoughtfully and thoroughly
- Stay engaged with platform updates and announcements
- Reach out for support whenever needed

🆘 Need Assistance?
Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard! 🌟

Best regards,
The Saurara Research Team

---
🌐 Platform: www.saurara.org
📧 Support: support@saurara.org
📱 Stay Connected: Follow us for updates and insights"""

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
                        🌐 <a href="http://www.saurara.org" style="color: #667eea; text-decoration: none; font-weight: 500;">www.saurara.org</a> | 
                        📧 <a href="mailto:support@saurara.org" style="color: #667eea; text-decoration: none; font-weight: 500;">support@saurara.org</a><br>
                        📱 <strong>Stay Connected:</strong> Follow us for updates and insights
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

def send_welcome_email(to_email, username, password, firstname=None, survey_code=None):
    """Send welcome email to new user (tries SES API first, falls back to SMTP)"""
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)
        
        # Email content
        subject = "Welcome to Saurara Platform"
        
        # Create personalized greeting
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        # Debug the password being used in email template
        logger.info(f"Email template variables - Username: '{username}', Email: '{to_email}', Password: '{password}', Survey Code: '{survey_code}', Greeting: '{greeting}'")
        
        body_text = f"""{greeting},

🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

🔐 Your Account Credentials:
• Username: {username}
• Email Address: {to_email}
• Temporary Password: {password}
• Survey Code: {survey_code if survey_code else 'Not assigned'}
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

🎯 What Awaits You:
As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. Every response makes a difference!

📚 Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

💡 Getting the Most Out of Saurara:
- Complete your profile for better survey matching
- Respond to surveys thoughtfully and thoroughly
- Stay engaged with platform updates and announcements
- Reach out for support whenever needed

🆘 Need Assistance?
Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard! 🌟

Best regards,
The Saurara Research Team

---
🌐 Platform: www.saurara.org
📧 Support: support@saurara.org
📱 Stay Connected: Follow us for updates and insights"""

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
                    <p style="font-size: 19px; margin-bottom: 25px; color: #374151;">{greeting},</p>
                    
                    <div class="welcome-banner">
                        <h2 style="margin: 0 0 10px 0; font-size: 24px;">🌟 Welcome to Our Community!</h2>
                        <p style="margin: 0; font-size: 16px; opacity: 0.95;">We are thrilled to have you join our growing community of researchers, educators, and community leaders. Your account has been successfully created and you're ready to embark on your journey with us!</p>
                    </div>
                    
                    <div class="credentials-box">
                        <h3 style="color: #065f46; margin-top: 0; font-size: 20px;">🔐 Your Account Credentials</h3>
                        <div class="credential-item">
                            <strong>👤 Username:</strong> <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #374151; font-weight: bold;">{username}</code>
                        </div>
                        <div class="credential-item">
                            <strong>📧 Email Address:</strong> <span style="color: #3b82f6; font-weight: 500;">{to_email}</span>
                        </div>
                        <div class="credential-item">
                            <strong>🔑 Temporary Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #92400e; font-weight: bold; border: 1px solid #f59e0b;">{password}</code>
                        </div>
                        <div class="credential-item">
                            <strong>🆔 Survey Code:</strong> <code style="background: #f0f9ff; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #1e40af; font-weight: bold; border: 1px solid #3b82f6;">{survey_code if survey_code else 'Not assigned'}</code>
                        </div>
                        <div class="credential-item">
                            <strong>🌐 Platform Access:</strong> <a href="http://www.saurara.org" style="color: #667eea; font-weight: 600; text-decoration: none;">www.saurara.org</a>
                        </div>
                    </div>
                    
                    <div style="text-align: center; margin: 35px 0;">
                        <a href="http://www.saurara.org" class="button" style="font-size: 16px;">🚀 Access Platform Now</a>
                    </div>
                    
                    <div class="quick-start">
                        <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">📋 Quick Start Guide</h3>
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
                        <h3 style="color: #c2410c; margin-top: 0; font-size: 18px;">🔒 Important Security Information</h3>
                        <p style="margin-bottom: 0; color: #374151;"><strong>For your account security:</strong> Please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals. Your data privacy and security are our top priorities.</p>
                    </div>
                    
                    <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #0ea5e9;">
                        <h3 style="color: #0c4a6e; margin-top: 0; font-size: 18px;">🎯 What Awaits You</h3>
                        <p style="color: #374151; margin-bottom: 0;">As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. <strong>Every response makes a difference!</strong></p>
                    </div>
                    
                    <div class="features-grid">
                        <h3 style="color: #5b21b6; margin-top: 0; font-size: 18px;">📚 Platform Features</h3>
                        <div class="feature-item">• <strong>Personalized survey dashboard</strong> - Tailored to your profile</div>
                        <div class="feature-item">• <strong>Progress tracking</strong> - Monitor your completion status</div>
                        <div class="feature-item">• <strong>Secure data handling</strong> - Privacy protection guaranteed</div>
                        <div class="feature-item">• <strong>Community insights</strong> - Access research updates</div>
                        <div class="feature-item">• <strong>Professional networking</strong> - Connect with peers</div>
                    </div>
                    
                    <div class="tips-section">
                        <h3 style="color: #065f46; margin-top: 0; font-size: 18px;">💡 Getting the Most Out of Saurara</h3>
                        <div class="tip-item">📝 Complete your profile for better survey matching</div>
                        <div class="tip-item">🎯 Respond to surveys thoughtfully and thoroughly</div>
                        <div class="tip-item">📢 Stay engaged with platform updates and announcements</div>
                        <div class="tip-item">🤝 Reach out for support whenever needed</div>
                    </div>
                    
                    <div class="support-box">
                        <h3 style="color: #1d4ed8; margin-top: 0; font-size: 18px;">🆘 Need Assistance?</h3>
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
                        🌐 Platform: <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                        📧 Support: <a href="mailto:support@saurara.org" style="color: #667eea;">support@saurara.org</a><br>
                        📱 Stay Connected: Follow us for updates and insights
                    </p>
                </div>
            </div>
        </body>
        </html>"""
        
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
        return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)
    except Exception as e:
        logger.error(f"Error sending welcome email via SES API: {str(e)}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_welcome_email_smtp(to_email, username, password, firstname, survey_code)

def send_survey_assignment_email(to_email, username, survey_code, firstname=None, organization_name=None, survey_name=None, assigned_by=None):
    """Send survey assignment email to user (tries SES API first, falls back to SMTP)"""
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_survey_assignment_email_smtp(to_email, username, survey_code, firstname, organization_name, survey_name, assigned_by)
        
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
Survey Platform: www.saurara.org | Support: support@saurara.org"""

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
                        <strong>📧 Support:</strong> <a href="mailto:support@saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">support@saurara.org</a>
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
        return send_survey_assignment_email_smtp(to_email, username, survey_code, firstname, organization_name, survey_name, assigned_by)

def send_survey_assignment_email_smtp(to_email, username, survey_code, firstname=None, organization_name=None, survey_name=None, assigned_by=None):
    """Send survey assignment email using SMTP"""
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
Survey Platform: www.saurara.org | Support: support@saurara.org"""

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
                        <strong>📧 Support:</strong> <a href="mailto:support@saurara.org" style="color: #28a745; font-weight: 600; text-decoration: none;">support@saurara.org</a>
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

def send_reminder_email_smtp(to_email, username, survey_code, firstname=None, organization_name=None, days_remaining=None):
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
        
        body_text = f"""{greeting},

We hope this message finds you well!

This is a friendly reminder that you have a pending survey{org_text} on the Saurara Platform that requires your attention.{deadline_text}

Your Survey Details:
• Username: {username}
• Survey Code: {survey_code}
• Survey Link: www.saurara.org

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
Visit: www.saurara.org | Email: support@saurara.org"""

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
                            <li><strong>🔑 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                        </ul>
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
                        <a href="mailto:support@saurara.org" style="color: #667eea;">support@saurara.org</a>
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

def send_reminder_email(to_email, username, survey_code, firstname=None, organization_name=None, days_remaining=None):
    """Send reminder email to user (tries SES API first, falls back to SMTP)"""
    try:
        ses_client = get_ses_client()
        if not ses_client:
            logger.warning("SES API client failed, trying SMTP method...")
            return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining)
        
        # Email content
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
Visit: www.saurara.org | Email: support@saurara.org"""

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
                            <li><strong>🔑 Survey Code:</strong> <code style="background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">{survey_code}</code></li>
                            <li><strong>🌐 Platform:</strong> <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a></li>
                        </ul>
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
                        <a href="mailto:support@saurara.org" style="color: #667eea;">support@saurara.org</a>
                    </p>
                </div>
            </div>
        </body>
        </html>"""
        
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
        logger.error(f"SES API ClientError: {error_code} - {error_message}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining)
    except Exception as e:
        logger.error(f"Error sending reminder email via SES API: {str(e)}")
        logger.warning("SES API failed, trying SMTP method as fallback...")
        return send_reminder_email_smtp(to_email, username, survey_code, firstname, organization_name, days_remaining)

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
    local_db_password = 'rootroot'
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
        
        # Generate unique survey code if not provided
        if not new_survey_code:
            new_survey_code = f"{source_template.survey_code}_copy_to_{target_organization.name.lower().replace(' ', '_')}"
        
        # Ensure the survey code is unique
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
        db.session.commit()
        
        logger.info(f"Template {template_id} copied to organization {target_organization_id} as template {copied_template.id}")
        
        return jsonify({
            'success': True,
            'copied_template': {
                'id': copied_template.id,
                'survey_code': copied_template.survey_code,
                'version_id': copied_template.version_id,
                'version_name': target_version.name,
                'organization_id': target_organization_id,
                'organization_name': target_organization.name
            },
            'message': f'Template successfully copied to {target_organization.name}'
        }), 201
        
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
            'umbrella_association_membership': org.details.get('umbrella_association_membership') if org.details else None
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
        
        # Get all templates in the source version
        source_templates = SurveyTemplate.query.filter_by(version_id=version_id).all()
        
        copied_templates = []
        for source_template in source_templates:
            # Generate unique survey code for each template
            new_survey_code = f"{source_template.survey_code}_copy_to_{target_organization.name.lower().replace(' ', '_')}"
            
            # Ensure the survey code is unique
            template_counter = 1
            original_survey_code = new_survey_code
            while True:
                existing_template = SurveyTemplate.query.filter_by(survey_code=new_survey_code).first()
                if not existing_template:
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
            copied_templates.append({
                'original_id': source_template.id,
                'original_survey_code': source_template.survey_code,
                'new_survey_code': new_survey_code
            })
        
        db.session.commit()
        
        logger.info(f"Template version {version_id} copied to organization {target_organization_id} as version {copied_version.id} with {len(copied_templates)} templates")
        
        return jsonify({
            'success': True,
            'copied_version': {
                'id': copied_version.id,
                'name': copied_version.name,
                'description': copied_version.description,
                'organization_id': target_organization_id,
                'organization_name': target_organization.name,
                'template_count': len(copied_templates)
            },
            'copied_templates': copied_templates,
            'message': f'Template version successfully copied to {target_organization.name} with {len(copied_templates)} templates'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error copying template version {version_id}: {str(e)}")
        return jsonify({'error': f'Failed to copy template version: {str(e)}'}), 500

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
        
        # Include organization info if available
        if user.organization:
            user_data['organization_name'] = user.organization.name
        
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
    
    # Create survey response record automatically
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
    
    db.session.commit()
    
    # Send welcome email automatically
    try:
        email_result = send_welcome_email(
            to_email=new_user.email,
            username=new_user.username,
            password=user_password,
            firstname=new_user.firstname,
            survey_code=survey_code
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
        
        # Log the password being sent (for debugging - remove in production)
        logger.info(f"Password being sent in welcome email: '{data['password']}'")
        
        # Send the email
        result = send_welcome_email(
            to_email=data['to_email'],
            username=data['username'],
            password=data['password'],
            firstname=data.get('firstname'),
            survey_code=data.get('survey_code')
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
            days_remaining=data.get('days_remaining')
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
                    days_remaining=user_data.get('days_remaining')
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
            days_remaining=suggested_deadline
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

🎉 Welcome to the Saurara Platform! We are thrilled to have you join our growing community of researchers, educators, and community leaders.

We're excited to welcome you aboard! Your account has been successfully created and you're ready to embark on your journey with us.

🔐 Your Account Credentials:
• Username: {username}
• Email Address: {email}
• Temporary Password: {password}
• Survey Code: {survey_code}
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

🎯 What Awaits You:
As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. Every response makes a difference!

📚 Platform Features:
• Personalized survey dashboard
• Progress tracking and completion status
• Secure data handling and privacy protection
• Community insights and research updates
• Professional networking opportunities

💡 Getting the Most Out of Saurara:
- Complete your profile for better survey matching
- Respond to surveys thoughtfully and thoroughly
- Stay engaged with platform updates and announcements
- Reach out for support whenever needed

🆘 Need Assistance?
Our dedicated support team is here to help you succeed. Whether you have technical questions, need guidance on surveys, or want to learn more about our research initiatives, we're just a message away!

We're honored to have you as part of the Saurara family. Together, we're building a better understanding of education and community development globally.

Welcome aboard! 🌟

Best regards,
The Saurara Research Team

---
🌐 Platform: www.saurara.org
📧 Support: support@saurara.org
📱 Stay Connected: Follow us for updates and insights"""

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
                <h2 style="margin: 0 0 10px 0; font-size: 24px;">🌟 Welcome to Our Community!</h2>
                <p style="margin: 0; font-size: 16px; opacity: 0.95;">We are thrilled to have you join our growing community of researchers, educators, and community leaders. Your account has been successfully created and you're ready to embark on your journey with us!</p>
            </div>
            
            <div class="credentials-box">
                <h3 style="color: #065f46; margin-top: 0; font-size: 20px;">🔐 Your Account Credentials</h3>
                <div class="credential-item">
                    <strong>👤 Username:</strong> <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #374151; font-weight: bold;">{username}</code>
                </div>
                <div class="credential-item">
                    <strong>📧 Email Address:</strong> <span style="color: #3b82f6; font-weight: 500;">{email}</span>
                </div>
                <div class="credential-item">
                    <strong>🔑 Temporary Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #92400e; font-weight: bold; border: 1px solid #f59e0b;">{password}</code>
                </div>
                <div class="credential-item">
                    <strong>🆔 Survey Code:</strong> <code style="background: #f0f9ff; padding: 4px 8px; border-radius: 6px; font-family: 'Courier New', monospace; color: #1e40af; font-weight: bold; border: 1px solid #3b82f6;">{survey_code}</code>
                </div>
                <div class="credential-item">
                    <strong>🌐 Platform Access:</strong> <a href="http://www.saurara.org" style="color: #667eea; font-weight: 600; text-decoration: none;">www.saurara.org</a>
                </div>
            </div>
            
            <div style="text-align: center; margin: 35px 0;">
                <a href="http://www.saurara.org" class="button" style="font-size: 16px;">🚀 Access Platform Now</a>
            </div>
            
            <div class="quick-start">
                <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">📋 Quick Start Guide</h3>
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
                <h3 style="color: #c2410c; margin-top: 0; font-size: 18px;">🔒 Important Security Information</h3>
                <p style="margin-bottom: 0; color: #374151;"><strong>For your account security:</strong> Please change your password during your first login. Keep your credentials safe and never share them with unauthorized individuals. Your data privacy and security are our top priorities.</p>
            </div>
            
            <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); padding: 25px; border-radius: 12px; margin: 25px 0; border-left: 5px solid #0ea5e9;">
                <h3 style="color: #0c4a6e; margin-top: 0; font-size: 18px;">🎯 What Awaits You</h3>
                <p style="color: #374151; margin-bottom: 0;">As a member of the Saurara community, you'll receive invitations to participate in meaningful research initiatives. Your insights will contribute to understanding and improving educational and community programs worldwide. <strong>Every response makes a difference!</strong></p>
            </div>
            
            <div class="features-grid">
                <h3 style="color: #5b21b6; margin-top: 0; font-size: 18px;">📚 Platform Features</h3>
                <div class="feature-item">• <strong>Personalized survey dashboard</strong> - Tailored to your profile</div>
                <div class="feature-item">• <strong>Progress tracking</strong> - Monitor your completion status</div>
                <div class="feature-item">• <strong>Secure data handling</strong> - Privacy protection guaranteed</div>
                <div class="feature-item">• <strong>Community insights</strong> - Access research updates</div>
                <div class="feature-item">• <strong>Professional networking</strong> - Connect with peers</div>
            </div>
            
            <div class="tips-section">
                <h3 style="color: #065f46; margin-top: 0; font-size: 18px;">💡 Getting the Most Out of Saurara</h3>
                <div class="tip-item">📝 Complete your profile for better survey matching</div>
                <div class="tip-item">🎯 Respond to surveys thoughtfully and thoroughly</div>
                <div class="tip-item">📢 Stay engaged with platform updates and announcements</div>
                <div class="tip-item">🤝 Reach out for support whenever needed</div>
            </div>
            
            <div class="support-box">
                <h3 style="color: #1d4ed8; margin-top: 0; font-size: 18px;">🆘 Need Assistance?</h3>
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
                🌐 Platform: <a href="http://www.saurara.org" style="color: #667eea;">www.saurara.org</a> | 
                📧 Support: <a href="mailto:support@saurara.org" style="color: #667eea;">support@saurara.org</a><br>
                📱 Stay Connected: Follow us for updates and insights
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
                
                # Generate unique survey code for this assignment
                survey_code = str(uuid.uuid4())
                
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
        # Verify user exists
        user = User.query.get_or_404(user_id)
        
        # Get all survey responses for this user with eager loading of relationships
        assignments = db.session.query(SurveyResponse)\
            .options(db.joinedload(SurveyResponse.template)\
                      .joinedload(SurveyTemplate.version))\
            .filter_by(user_id=user_id).all()
        
        logger.info(f"Found {len(assignments)} assignments for user {user_id}")
        
        result = []
        for assignment in assignments:
            try:
                template_name = "Survey"  # Default name
                if assignment.template:
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
                    'survey_code': assignment.survey_code,
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
            'total_assignments': len(result),
            'assignments': result
        }
        
        logger.info(f"Returning {len(result)} assignments for user {user_id}")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error getting user survey assignments: {str(e)}")
        return jsonify({'error': f'Failed to get user survey assignments: {str(e)}'}), 500

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

if __name__ == '__main__':
    app.run(debug=True)
