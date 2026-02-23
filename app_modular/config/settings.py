"""
Configuration settings for the Flask application.
Handles environment variables and database connection settings.
"""
import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

# Ensure .env values override any existing environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'), override=True)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Config:
    """Base configuration class."""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database settings from environment
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = os.getenv('DB_PORT', '3306')
    DB_NAME = os.getenv('DB_NAME')
    
    # Local fallback settings
    LOCAL_DB_USER = 'root'
    LOCAL_DB_PASSWORD = 'jaideep'
    LOCAL_DB_HOST = 'localhost'
    LOCAL_DB_PORT = '3306'
    LOCAL_DB_NAME = 'boskopartnersdb'
    
    # SQLAlchemy settings
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = True  # Log all SQL queries
    
    # CORS settings
    CORS_ORIGINS = [
        "http://localhost:3000",    # for local dev
        "http://3.142.171.30",       # EC2-served frontend
        "http://18.222.89.189",
        "https://saurara.org",       # production domain
        "http://saurara.org"         # production domain (http fallback)
    ]
    
    # AWS SES settings
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    
    # SES SMTP settings
    SES_SMTP_USERNAME = os.getenv('SES_SMTP_USERNAME')
    SES_SMTP_PASSWORD = os.getenv('SES_SMTP_PASSWORD')
    SES_SMTP_HOST = os.getenv('SES_SMTP_HOST', 'email-smtp.us-east-1.amazonaws.com')
    SES_SMTP_PORT = int(os.getenv('SES_SMTP_PORT', '587'))
    SES_VERIFIED_EMAIL = os.getenv('SES_VERIFIED_EMAIL', 'noreply@saurara.org')
    
    # Google Maps API
    GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')


def get_database_url():
    """
    Determine the database URL to use.
    Tries environment variables first, falls back to local settings.
    
    Returns:
        str: The database URL to use for SQLAlchemy
    """
    config = Config()
    
    # Try environment-based URL first
    if all([config.DB_USER, config.DB_PASSWORD, config.DB_HOST, config.DB_NAME]):
        db_url_candidate = (
            f"mysql+pymysql://{config.DB_USER}:{config.DB_PASSWORD}"
            f"@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
        )
        
        # Test the connection
        try:
            engine = create_engine(db_url_candidate)
            conn = engine.connect()
            conn.close()
            logger.info("✅ Connected using .env settings")
            return db_url_candidate
        except OperationalError as e:
            logger.warning(f"⚠️  .env DB connection failed: {e}")
    
    # Fallback to local settings
    fallback_url = (
        f"mysql+pymysql://{config.LOCAL_DB_USER}:{config.LOCAL_DB_PASSWORD}"
        f"@{config.LOCAL_DB_HOST}:{config.LOCAL_DB_PORT}/{config.LOCAL_DB_NAME}"
    )
    logger.info("✅ Using local database settings")
    return fallback_url
