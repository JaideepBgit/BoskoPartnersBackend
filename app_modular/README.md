# Modularized Flask Backend Application
# =====================================
#
# This directory contains the modularized version of the original app.py
# (~12,000 lines) broken down into organized modules.
#
# Directory Structure:
# --------------------
# app_modular/
# ├── __init__.py          # Package initialization
# ├── app.py               # Application factory (main entry point)
# ├── config/              # Configuration settings
# │   ├── __init__.py
# │   ├── settings.py      # Environment and app settings
# │   └── database.py      # Database initialization
# ├── models/              # SQLAlchemy database models
# │   ├── __init__.py
# │   ├── organization.py  # Organization, OrganizationType
# │   ├── user.py          # User, UserDetails, Role, Title, UserOrganizationTitle
# │   ├── geo_location.py  # GeoLocation
# │   ├── survey.py        # SurveyTemplate, SurveyResponse, etc.
# │   ├── question.py      # Question, QuestionType, QuestionOption
# │   ├── email_template.py# EmailTemplate
# │   ├── report.py        # ReportTemplate, SavedReport
# │   └── contact.py       # ContactReferral
# ├── routes/              # API route blueprints
# │   ├── __init__.py      # Blueprint registration
# │   ├── auth.py          # Login, register, password reset
# │   ├── users.py         # User CRUD operations
# │   ├── organizations.py # Organization management
# │   ├── survey_templates.py  # Survey template management + legacy endpoints
# │   ├── survey_responses.py  # Survey response handling
# │   ├── email.py         # Email sending and templates
# │   ├── analytics.py     # Dashboard statistics + text analytics
# │   ├── reports.py       # Report management
# │   ├── contact_referrals.py # Contact referral system
# │   ├── geo.py           # Geocoding endpoints
# │   ├── rag.py           # AI/RAG endpoints
# │   └── initialization.py # Setup and test data endpoints
# ├── services/            # Business logic services
# │   ├── __init__.py
# │   ├── email_service.py # Email sending (SES/SMTP)
# │   └── geocoding_service.py # Address geocoding
# └── utils/               # Utility functions
#     ├── __init__.py
#     └── helpers.py       # Common helper functions
#
# Usage:
# ------
# 1. To run the modular app directly:
#    python run_modular.py
#
# 2. To import and use in another file:
#    from app_modular.app import create_app
#    app = create_app()
#
# 3. The original app.py is preserved and can still be used
#    until you are ready to fully switch to the modular version.
#
# Migration Notes:
# ----------------
# - All functionality from the original app.py has been preserved
# - Routes are organized by domain (auth, users, organizations, etc.)
# - Models are separated into individual files
# - Configuration is centralized in config/settings.py
# - Services contain reusable business logic
# - The original app.py can be gradually deprecated
#
# Added Endpoints (Complete Feature Parity):
# ------------------------------------------
# - survey_templates.py:
#   * Conditional question types (/api/question-types/conditional)
#   * Question classification (/api/question-types/classify)
#   * Initialize question types (/api/question-types/initialize)
#   * Legacy inventory endpoints (for backward compatibility)
# 
# - analytics.py:
#   * Text analytics (/api/reports/analytics/text)
#   * Sentiment analysis, topic modeling, clustering
# 
# - initialization.py:
#   * Test database connection (/api/test-database)
#   * Initialize test data (/api/initialize-test-data)
#   * Initialize organization types (/api/organization-types/initialize)
#   * Initialize email templates (/api/initialize-default-email-templates)
#   * Debug endpoints for development

