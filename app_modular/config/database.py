"""
Database initialization and configuration.
"""
from flask_sqlalchemy import SQLAlchemy

# Create the SQLAlchemy instance (will be initialized with app later)
db = SQLAlchemy()


def init_database(app):
    """
    Initialize the database with the Flask app.
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)


def create_tables(app):
    """
    Create all database tables if they don't exist.
    
    Args:
        app: Flask application instance
    """
    with app.app_context():
        db.create_all()
        print("Tables created or already exist.")
