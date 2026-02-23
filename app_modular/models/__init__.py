# Database Models
# Note: Import order matters due to foreign key dependencies

from ..config.database import db

# Import base models first (no FK dependencies)
from .geo_location import GeoLocation
from .organization import OrganizationType, Organization
from .user import User, UserDetails, Role, UserOrganizationTitle, Title

# Survey-related models
from .survey import (
    SurveyTemplateVersion,
    SurveyTemplate,
    SurveyVersion,
    Survey,
    SurveyResponse
)

# Question models
from .question import Question, QuestionType, QuestionOption

# Surveys V2 models
from .survey_v2 import SurveyV2, SurveyOrganization

# Other models
from .email_template import EmailTemplate
from .report import ReportTemplate, SavedReport
from .contact import ContactReferral, ReferralLink
from .reminder import SurveyReminderSetting, SurveyReminderLog


__all__ = [
    # Database
    'db',
    # Organization
    'Organization',
    'OrganizationType',
    # User
    'User',
    'UserDetails',
    'Role',
    'UserOrganizationTitle',
    'Title',
    # Geo
    'GeoLocation',
    # Survey
    'SurveyTemplate',
    'SurveyTemplateVersion',
    'SurveyVersion',
    'Survey',
    'SurveyResponse',
    # Question
    'Question',
    'Question',
    'QuestionType',
    'QuestionOption',
    # Surveys V2
    'SurveyV2',
    'SurveyOrganization',
    # Email
    'EmailTemplate',
    # Report
    'ReportTemplate',
    'SavedReport',
    # Contact
    'ContactReferral',
    'ReferralLink',
    # Reminder
    'SurveyReminderSetting',
    'SurveyReminderLog',
]
