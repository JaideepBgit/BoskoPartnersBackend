"""
Flask Application Factory
This is the main entry point for the modularized Flask application.
"""
from flask import Flask
from flask_cors import CORS
import logging

from .config.settings import Config, get_database_url
from .config.database import db, init_database, create_tables
from .routes import register_blueprints
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    """
    Application factory function.
    
    Args:
        config_class: Configuration class to use
    
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ECHO'] = True  # Log all SQL queries
    
    # Configure CORS
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": config_class.CORS_ORIGINS,
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
            }
        },
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"]
    )
    
    # Initialize database
    init_database(app)
    
    # Register blueprints (routes)
    register_blueprints(app)
    
    # Initialize RAG service after app context is available
    with app.app_context():
        try:
            from .routes.rag import initialize_rag_service
            initialize_rag_service(db)
        except Exception as e:
            logger.warning(f"Could not initialize RAG service: {e}")
    
    # Start background scheduler for reminders
    _start_reminder_scheduler(app)

    logger.info("✅ Flask application created successfully")

    return app


def _start_reminder_scheduler(app):
    """Start APScheduler to process due reminders every 5 minutes."""
    import os
    # Avoid duplicate schedulers when Flask reloader forks a child process
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        scheduler = BackgroundScheduler(daemon=True)

        def _tick():
            with app.app_context():
                from .routes.reminders import process_due_reminders
                with app.test_client() as client:
                    client.post('/api/process-due-reminders')

        scheduler.add_job(_tick, 'interval', minutes=5, id='reminder_tick')
        scheduler.start()
        logger.info("✅ Reminder scheduler started (every 5 min)")


def init_app():
    """
    Initialize the application and create tables.
    This should be called once when setting up the application.
    """
    app = create_app()
    
    with app.app_context():
        create_tables(app)
        logger.info("✅ Database tables created/verified")
    
    return app


# Create the application instance
app = create_app()


if __name__ == '__main__':
    app.run(debug=False)
