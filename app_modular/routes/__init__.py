# API Routes
from .auth import auth_bp
from .users import users_bp
from .organizations import organizations_bp
from .survey_templates import survey_templates_bp
from .survey_responses import survey_responses_bp
from .email import email_bp
from .analytics import analytics_bp
from .reports import reports_bp
from .contact_referrals import contact_referrals_bp
from .geo import geo_bp
from .rag import rag_bp
from .initialization import initialization_bp
from .reminders import reminders_bp
from .surveys_v2 import surveys_v2_bp
from .survey_responses_v2 import survey_responses_v2_bp
from .kpi_dashboard import kpi_dashboard_bp
from .onboarding import onboarding_bp

# List of all blueprints to register with their URL prefixes
all_blueprints = [
    (auth_bp, '/api'),
    (users_bp, '/api'),
    (organizations_bp, '/api'),
    (survey_templates_bp, '/api'),
    (survey_responses_bp, '/api'),
    (email_bp, '/api'),
    (analytics_bp, '/api'),
    (reports_bp, '/api'),
    (contact_referrals_bp, '/api'),
    (geo_bp, '/api'),
    (rag_bp, '/api'),
    (initialization_bp, '/api'),
    (reminders_bp, '/api'),
    (surveys_v2_bp, '/api'),
    (survey_responses_v2_bp, '/api'),
    (kpi_dashboard_bp, '/api'),
    (onboarding_bp, '/api'),
]


def register_blueprints(app):
    """
    Register all blueprints with the Flask app.
    
    Args:
        app: Flask application instance
    """
    for blueprint, url_prefix in all_blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)


__all__ = [
    'auth_bp',
    'users_bp',
    'organizations_bp',
    'survey_templates_bp',
    'survey_responses_bp',
    'email_bp',
    'analytics_bp',
    'reports_bp',
    'contact_referrals_bp',
    'geo_bp',
    'rag_bp',
    'initialization_bp',
    'reminders_bp',
    'surveys_v2_bp',
    'survey_responses_v2_bp',
    'kpi_dashboard_bp',
    'onboarding_bp',
    'register_blueprints',
    'all_blueprints',
]

