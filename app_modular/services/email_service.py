"""
Email service for sending various types of emails.
Supports both AWS SES API and SMTP fallback.
"""
import os
import logging
import csv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import boto3
from botocore.exceptions import ClientError

from ..config.settings import Config

logger = logging.getLogger(__name__)


class EmailService:
    """Service class for handling all email operations."""
    
    def __init__(self):
        self.config = Config()
        self._ses_client = None
    
    def load_ses_credentials(self):
        """Load SES credentials from CSV file."""
        try:
            credentials_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ses-email-user_credentials.csv')
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
    
    def get_ses_client(self):
        """Initialize and return SES client."""
        if self._ses_client:
            return self._ses_client
        
        try:
            aws_access_key_id = self.config.AWS_ACCESS_KEY_ID
            aws_secret_access_key = self.config.AWS_SECRET_ACCESS_KEY
            aws_region = self.config.AWS_DEFAULT_REGION
            
            logger.info(f"Initializing SES client with region: {aws_region}")
            
            if not aws_access_key_id or not aws_secret_access_key:
                logger.error("AWS credentials not found in environment variables")
                return None
            
            session = boto3.Session(
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=aws_region
            )
            self._ses_client = session.client('ses')
            return self._ses_client
        except Exception as e:
            logger.error(f"Error initializing SES client: {str(e)}")
            return None
    
    def send_email_smtp(self, to_email, subject, body_text, body_html):
        """Send email using SMTP."""
        try:
            smtp_username = self.config.SES_SMTP_USERNAME
            smtp_password = self.config.SES_SMTP_PASSWORD
            smtp_host = self.config.SES_SMTP_HOST
            smtp_port = self.config.SES_SMTP_PORT
            source_email = self.config.SES_VERIFIED_EMAIL
            
            if not smtp_username or not smtp_password:
                raise Exception("SMTP credentials not found in environment variables")
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = source_email
            msg['To'] = to_email
            
            # Create the plain-text and HTML version of your message
            text_part = MIMEText(body_text, 'plain')
            html_part = MIMEText(body_html, 'html')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send the email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(source_email, to_email, msg.as_string())
            
            logger.info(f"Email sent successfully via SMTP to {to_email}")
            return {
                'success': True,
                'method': 'SMTP',
                'message': 'Email sent successfully via SMTP'
            }
            
        except Exception as e:
            logger.error(f"Error sending email via SMTP: {str(e)}")
            return {
                'success': False,
                'error': f"SMTP email sending failed: {str(e)}"
            }
    
    def send_email_ses(self, to_email, subject, body_text, body_html):
        """Send email using AWS SES API."""
        try:
            ses_client = self.get_ses_client()
            if not ses_client:
                logger.warning("SES API client failed, trying SMTP method...")
                return self.send_email_smtp(to_email, subject, body_text, body_html)
            
            source_email = self.config.SES_VERIFIED_EMAIL
            
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
            
            logger.info(f"Email sent successfully via SES API to {to_email}. Message ID: {response['MessageId']}")
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
            return self.send_email_smtp(to_email, subject, body_text, body_html)
        except Exception as e:
            logger.error(f"Error sending email via SES API: {str(e)}")
            logger.warning("SES API failed, trying SMTP method as fallback...")
            return self.send_email_smtp(to_email, subject, body_text, body_html)
    
    def send_welcome_email(self, to_email, username, password, firstname=None, survey_code=None, template_data=None):
        """
        Send welcome email to new user.
        
        Args:
            to_email: Recipient email address
            username: User's username
            password: User's password
            firstname: User's first name (optional)
            survey_code: Survey code (optional)
            template_data: Email template data dict with 'subject', 'html_body', 'text_body' (optional)
        """
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        if template_data:
            subject = template_data.get('subject', 'Welcome to Saurara Platform')
            body_text = template_data.get('text_body', '').format(
                greeting=greeting, username=username, email=to_email,
                password=password, survey_code=survey_code or 'Not assigned'
            )
            body_html = template_data.get('html_body', '').format(
                greeting=greeting, username=username, email=to_email,
                password=password, survey_code=survey_code or 'Not assigned'
            )
        else:
            subject = "Welcome to Saurara Platform"
            body_text = self._get_default_welcome_text(greeting, username, to_email, password, survey_code)
            body_html = self._get_default_welcome_html(greeting, username, to_email, password, survey_code)
        
        return self.send_email_ses(to_email, subject, body_text, body_html)
    
    def send_reminder_email(self, to_email, username, survey_code, firstname=None, 
                           organization_name=None, days_remaining=None, password=None, template_data=None):
        """Send reminder email to user about their pending survey."""
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        if template_data:
            subject = template_data.get('subject', 'Survey Reminder - Saurara Platform')
            body_text = template_data.get('text_body', '')
            body_html = template_data.get('html_body', '')
        else:
            subject = "📢 Reminder: Please Complete Your Survey"
            body_text = self._get_default_reminder_text(greeting, username, survey_code, 
                                                        organization_name, days_remaining, password)
            body_html = self._get_default_reminder_html(greeting, username, survey_code,
                                                        organization_name, days_remaining, password)
        
        return self.send_email_ses(to_email, subject, body_text, body_html)
    
    def send_password_reset_email(self, to_email, username, reset_token, firstname=None):
        """Send password reset email with reset link."""
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        # Build reset URL
        frontend_url = os.getenv('FRONTEND_URL', 'https://saurara.org')
        reset_link = f"{frontend_url}/reset-password?token={reset_token}"
        
        subject = "🔐 Password Reset Request - Saurara Platform"
        body_text = self._get_password_reset_text(greeting, username, reset_link)
        body_html = self._get_password_reset_html(greeting, username, reset_link)
        
        return self.send_email_ses(to_email, subject, body_text, body_html)
    
    def _get_default_welcome_text(self, greeting, username, to_email, password, survey_code):
        """Get default welcome email plain text."""
        return f"""{greeting},

Welcome to the Saurara Platform! Your account has been successfully created.

Your Account Credentials:
• Username: {username}
• Email Address: {to_email}
• Password: {password}
• Survey Code: {survey_code if survey_code else 'Not assigned'}
• Platform Access: www.saurara.org

Getting Started:
1. Visit www.saurara.org
2. Click on "Login" or "Survey Access"
3. Enter your username and password
4. Complete your profile when ready

Best regards,
The Saurara Research Team
"""
    
    def _get_default_welcome_html(self, greeting, username, to_email, password, survey_code):
        """Get default welcome email HTML."""
        return f"""<html><body>
<h1>Welcome to Saurara!</h1>
<p>{greeting},</p>
<p>Welcome to the Saurara Platform! Your account has been successfully created.</p>
<p><strong>Your Account Credentials:</strong></p>
<ul>
<li>Username: {username}</li>
<li>Email: {to_email}</li>
<li>Password: {password}</li>
<li>Survey Code: {survey_code if survey_code else 'Not assigned'}</li>
</ul>
<p><a href="https://www.saurara.org">Access Platform</a></p>
<p>Best regards,<br>The Saurara Research Team</p>
</body></html>"""
    
    def _get_default_reminder_text(self, greeting, username, survey_code, organization_name, days_remaining, password):
        """Get default reminder email plain text."""
        org_text = f" from {organization_name}" if organization_name else ""
        days_text = f" ({days_remaining} days remaining)" if days_remaining else ""
        
        return f"""{greeting},

This is a friendly reminder that you have a pending survey{org_text}{days_text} on the Saurara Platform.

Your Survey Access:
• Username: {username}
• Password: {password if password else '[Use your existing password]'}
• Survey Code: {survey_code}
• Platform: www.saurara.org

Please log in to complete your survey.

Best regards,
The Saurara Research Team
"""
    
    def _get_default_reminder_html(self, greeting, username, survey_code, organization_name, days_remaining, password):
        """Get default reminder email HTML."""
        org_text = f" from {organization_name}" if organization_name else ""
        days_text = f" ({days_remaining} days remaining)" if days_remaining else ""
        
        return f"""<html><body>
<h1>Survey Reminder</h1>
<p>{greeting},</p>
<p>This is a friendly reminder that you have a pending survey{org_text}{days_text}.</p>
<p><strong>Your Survey Access:</strong></p>
<ul>
<li>Username: {username}</li>
<li>Password: {password if password else '[Use your existing password]'}</li>
<li>Survey Code: {survey_code}</li>
</ul>
<p><a href="https://www.saurara.org">Complete Survey</a></p>
<p>Best regards,<br>The Saurara Research Team</p>
</body></html>"""
    
    def _get_password_reset_text(self, greeting, username, reset_link):
        """Get password reset email plain text."""
        return f"""{greeting},

We received a request to reset your password for your Saurara Platform account.

Username: {username}

Click the link below to reset your password:
{reset_link}

This link will expire in 1 hour for security purposes.

If you did not request a password reset, please ignore this email.

Best regards,
The Saurara Research Team
"""
    
    def _get_password_reset_html(self, greeting, username, reset_link):
        """Get password reset email HTML."""
        return f"""<html><body>
<h1>Password Reset Request</h1>
<p>{greeting},</p>
<p>We received a request to reset your password for your Saurara Platform account.</p>
<p><strong>Username:</strong> {username}</p>
<p><a href="{reset_link}" style="background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Reset Password</a></p>
<p>This link will expire in 1 hour for security purposes.</p>
<p>If you did not request a password reset, please ignore this email.</p>
<p>Best regards,<br>The Saurara Research Team</p>
</body></html>"""
    
    def send_survey_assignment_email(self, to_email, username, password, survey_code, 
                                      firstname=None, survey_name=None, template_data=None):
        """Send email notifying user of a new survey assignment."""
        greeting = f"Dear {firstname}" if firstname else f"Dear {username}"
        
        if template_data:
            subject = template_data.get('subject', 'New Survey Assignment - Saurara Platform')
            body_text = template_data.get('text_body', '')
            body_html = template_data.get('html_body', '')
        else:
            subject = f"📋 New Survey Assignment: {survey_name}" if survey_name else "📋 New Survey Assignment"
            body_text = self._get_assignment_text(greeting, username, password, survey_code, survey_name)
            body_html = self._get_assignment_html(greeting, username, password, survey_code, survey_name)
        
        return self.send_email_ses(to_email, subject, body_text, body_html)
    
    def _get_assignment_text(self, greeting, username, password, survey_code, survey_name):
        """Get survey assignment email plain text."""
        survey_text = f": {survey_name}" if survey_name else ""
        
        return f"""{greeting},

You have been assigned a new survey{survey_text} on the Saurara Platform.

Your Survey Access:
• Username: {username}
• Password: {password if password else '[Use your existing password]'}
• Survey Code: {survey_code}
• Platform: www.saurara.org

Please log in to complete your survey at your earliest convenience.

Best regards,
The Saurara Research Team
"""
    
    def _get_assignment_html(self, greeting, username, password, survey_code, survey_name):
        """Get survey assignment email HTML."""
        survey_text = f": {survey_name}" if survey_name else ""
        
        return f"""<html><body>
<h1>New Survey Assignment</h1>
<p>{greeting},</p>
<p>You have been assigned a new survey{survey_text} on the Saurara Platform.</p>
<p><strong>Your Survey Access:</strong></p>
<ul>
<li>Username: {username}</li>
<li>Password: {password if password else '[Use your existing password]'}</li>
<li>Survey Code: {survey_code}</li>
</ul>
<p><a href="https://www.saurara.org" style="background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Complete Survey</a></p>
<p>Best regards,<br>The Saurara Research Team</p>
</body></html>"""


# Create a singleton instance
email_service = EmailService()
